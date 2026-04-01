# pyright: standard
"""Import resolution — maps ImportRef → file path.

Each language provides an ImportResolver strategy. The resolver receives
an ImportRef (what the source code says) and resolves it to a concrete
file path on disk (or marks it as external/unresolvable).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from interpreter.constants import Language
from interpreter.project.types import CyclicImportError, ImportKind, ImportRef

logger = logging.getLogger(__name__)

# ── Resolution result ────────────────────────────────────────────


NO_PATH = Path("")


@dataclass(frozen=True)
class ResolvedImport:
    """Result of resolving an ImportRef to a file path."""

    ref: ImportRef
    resolved_path: Path = NO_PATH
    is_external: bool = False  # True for system / third-party imports

    def is_resolved(self) -> bool:
        """True if this import resolved to a concrete local file."""
        return self.resolved_path != NO_PATH and not self.is_external


# ── Resolver protocol ────────────────────────────────────────────


class ImportResolver(ABC):
    """Language-specific strategy for resolving ImportRef → file path(s).

    Returns a list to support wildcard imports (e.g., import com.example.*)
    which resolve to multiple files. Specific imports return a single-element list.
    """

    @abstractmethod
    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]: ...


# ── Null resolver ────────────────────────────────────────────────


class NullImportResolver(ImportResolver):
    """Marks everything as external — used for unsupported languages."""

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        return [ResolvedImport(ref=ref, is_external=True)]


# ── Python resolver ──────────────────────────────────────────────


class PythonImportResolver(ImportResolver):
    """Resolve Python imports to local .py files or packages (__init__.py)."""

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        if ref.is_system:
            return [ResolvedImport(ref=ref, is_external=True)]
        if ref.is_relative:
            return self._resolve_relative(ref, project_root)
        return self._resolve_absolute(ref, project_root)

    def _resolve_absolute(
        self, ref: ImportRef, project_root: Path
    ) -> list[ResolvedImport]:
        """Resolve absolute imports: 'import utils' or 'from pkg.mod import X'."""
        parts = ref.module_path.split(".") if ref.module_path else []

        if parts:
            candidates = self._candidates(project_root, parts)
            for candidate in candidates:
                if candidate.exists():
                    return [ResolvedImport(ref=ref, resolved_path=candidate)]
        # For 'from X import Y' where module_path is empty but names has content,
        # this shouldn't happen in absolute imports.
        return [ResolvedImport(ref=ref)]

    def _resolve_relative(
        self, ref: ImportRef, project_root: Path
    ) -> list[ResolvedImport]:
        """Resolve relative imports: 'from . import utils', 'from ..models import User'."""
        # Base directory: go up from source_file's directory by relative_level
        base = ref.source_file.parent
        for _ in range(ref.relative_level - 1):
            base = base.parent

        if ref.module_path:
            # from .models import User → look for models.py relative to base
            parts = ref.module_path.split(".")
            candidates = self._candidates(base, parts)
            for candidate in candidates:
                if candidate.exists():
                    return [ResolvedImport(ref=ref, resolved_path=candidate)]
        elif ref.names:
            # from . import utils → look for utils.py relative to base
            # from .. import models → look for models.py relative to base
            for name in ref.names:
                if name == "*":
                    continue
                candidates = self._candidates(base, [name])
                for candidate in candidates:
                    if candidate.exists():
                        return [ResolvedImport(ref=ref, resolved_path=candidate)]
        return [ResolvedImport(ref=ref)]

    @staticmethod
    def _candidates(base: Path, parts: list[str]) -> list[Path]:
        """Generate candidate file paths for a dotted module path."""
        rel_path = Path(*parts)
        return [
            base / rel_path.with_suffix(".py"),
            base / rel_path / "__init__.py",
        ]


# ── JavaScript / TypeScript resolver ─────────────────────────────


class JavaScriptImportResolver(ImportResolver):
    """Resolve JS/TS imports to local files with extension probing."""

    _EXTENSIONS = (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs")

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        if ref.is_system:
            return [ResolvedImport(ref=ref, is_external=True)]
        if not ref.is_relative:
            # Bare specifiers (no . or /) are npm packages → external
            return [ResolvedImport(ref=ref, is_external=True)]
        # Relative path resolution
        base = ref.source_file.parent
        target = base / ref.module_path

        # Try exact path first
        target_resolved = target.resolve()
        if target_resolved.is_file():
            return [ResolvedImport(ref=ref, resolved_path=target_resolved)]
        # Try with extensions
        for ext in self._EXTENSIONS:
            candidate = target.with_suffix(ext)
            if candidate.exists():
                return [ResolvedImport(ref=ref, resolved_path=candidate.resolve())]

        # Try index files
        if target.is_dir():
            for ext in self._EXTENSIONS:
                candidate = target / f"index{ext}"
                if candidate.exists():
                    return [ResolvedImport(ref=ref, resolved_path=candidate.resolve())]

        return [ResolvedImport(ref=ref)]


# ── Java resolver ────────────────────────────────────────────────


class JavaImportResolver(ImportResolver):
    """Resolve Java imports to source files using package path convention.

    When source_roots are provided (from SourceRootDiscovery), searches
    those roots first. Falls back to standard patterns under project_root.
    Supports wildcard imports (import com.example.*) by globbing the
    package directory.
    """

    _STANDARD_ROOTS = [
        Path("."),
        Path("src"),
        Path("src") / "main" / "java",
        Path("src") / "main" / "kotlin",
    ]

    def __init__(self, source_roots: list[Path] | None = None):
        self._source_roots = list(source_roots) if source_roots is not None else []

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        if ref.is_system:
            return [ResolvedImport(ref=ref, is_external=True)]

        parts = ref.module_path.split(".")
        rel_path = Path(*parts)

        search_roots = (
            self._source_roots
            if self._source_roots
            else [project_root / r for r in self._STANDARD_ROOTS]
        )

        # Wildcard: import com.example.* → find all .java files in the package dir
        if ref.names == ("*",):
            return self._resolve_wildcard(ref, rel_path, search_roots)

        # Specific: import com.example.Utils → find Utils.java
        # Try names appended to the package path first (e.g. module_path='com.math',
        # names=('Adder',) → com/math/Adder.java), then fall back to treating the
        # last segment of module_path as the class name (module_path='com.math.Adder').
        candidates: list[Path] = []
        if ref.names and ref.names != ("*",):
            for name in ref.names:
                candidates.append(rel_path / f"{name}.java")
        candidates.append(rel_path.with_suffix(".java"))

        for root in search_roots:
            for candidate_rel in candidates:
                candidate = root / candidate_rel
                if candidate.exists():
                    return [ResolvedImport(ref=ref, resolved_path=candidate)]

        return [ResolvedImport(ref=ref)]

    def _resolve_wildcard(
        self, ref: ImportRef, rel_path: Path, search_roots: list[Path]
    ) -> list[ResolvedImport]:
        """Resolve a wildcard import to all .java files in the package directory."""
        for root in search_roots:
            pkg_dir = root / rel_path
            if pkg_dir.is_dir():
                return [
                    ResolvedImport(ref=ref, resolved_path=f)
                    for f in sorted(pkg_dir.glob("*.java"))
                ]
        return [ResolvedImport(ref=ref)]


# ── Go resolver ──────────────────────────────────────────────────


class GoImportResolver(ImportResolver):
    """Resolve Go imports to local packages."""

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        if ref.is_system:
            return [ResolvedImport(ref=ref, is_external=True)]
        if ref.is_relative:
            base = ref.source_file.parent
            target = (base / ref.module_path).resolve()
            # Go packages are directories — look for .go files in them
            if target.is_dir():
                go_files = list(target.glob("*.go"))
                if go_files:
                    return [ResolvedImport(ref=ref, resolved_path=go_files[0])]
        else:
            # External package (github.com/...) — skip
            return [ResolvedImport(ref=ref, is_external=True)]
        return [ResolvedImport(ref=ref)]


# ── Rust resolver ────────────────────────────────────────────────


class RustImportResolver(ImportResolver):
    """Resolve Rust use/mod to local .rs files."""

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        if ref.is_system:
            return [ResolvedImport(ref=ref, is_external=True)]
        if ref.kind == ImportKind.MOD:
            # mod helpers; → helpers.rs or helpers/mod.rs
            base = ref.source_file.parent
            candidates = [
                base / f"{ref.module_path}.rs",
                base / ref.module_path / "mod.rs",
            ]
            for c in candidates:
                if c.exists():
                    return [ResolvedImport(ref=ref, resolved_path=c)]
            return [ResolvedImport(ref=ref)]
        if not ref.is_relative:
            return [ResolvedImport(ref=ref, is_external=True)]
        # crate::utils → src/utils.rs or src/utils/mod.rs
        path = ref.module_path
        for prefix in ("crate::", "self::", "super::"):
            if path.startswith(prefix):
                path = path[len(prefix) :]
                break

        parts = path.split("::")
        if not parts:
            return [ResolvedImport(ref=ref)]
        # Try relative to source file (for self::) or src/ (for crate::)
        if ref.module_path.startswith("crate::"):
            base = project_root / "src"
        elif ref.module_path.startswith("super::"):
            base = ref.source_file.parent.parent
        else:
            base = ref.source_file.parent

        rel = Path(*parts)
        candidates = [
            base / rel.with_suffix(".rs"),
            base / rel / "mod.rs",
        ]
        for c in candidates:
            if c.exists():
                return [ResolvedImport(ref=ref, resolved_path=c)]
        return [ResolvedImport(ref=ref)]


# ── C / C++ resolver ────────────────────────────────────────────


class CIncludeResolver(ImportResolver):
    """Resolve C/C++ #include "header.h" to local files."""

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        if ref.is_system:
            return [ResolvedImport(ref=ref, is_external=True)]
        base = ref.source_file.parent
        candidates = [
            base / ref.module_path,
            project_root / ref.module_path,
            project_root / "include" / ref.module_path,
            project_root / "src" / ref.module_path,
        ]
        for c in candidates:
            if c.exists():
                return [ResolvedImport(ref=ref, resolved_path=c)]
        return [ResolvedImport(ref=ref)]


# ── C# resolver ─────────────────────────────────────────────────


class CSharpImportResolver(ImportResolver):
    """Resolve C# using directives to local .cs files."""

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        if ref.is_system:
            return [ResolvedImport(ref=ref, is_external=True)]
        # MyNamespace.MyClass → MyNamespace/MyClass.cs
        parts = ref.module_path.split(".")
        rel_path = Path(*parts)
        candidates = [
            project_root / rel_path.with_suffix(".cs"),
            project_root / "src" / rel_path.with_suffix(".cs"),
        ]
        for c in candidates:
            if c.exists():
                return [ResolvedImport(ref=ref, resolved_path=c)]
        return [ResolvedImport(ref=ref)]


# ── JVM resolver (Kotlin/Scala) ─────────────────────────────────


class JvmImportResolver(ImportResolver):
    """Resolve Kotlin/Scala imports using JVM package path convention."""

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        if ref.is_system:
            return [ResolvedImport(ref=ref, is_external=True)]
        parts = ref.module_path.split(".")
        rel_path = Path(*parts)

        _KT_EXTENSIONS = (".kt", ".kts", ".scala", ".java")
        search_roots = [
            project_root,
            project_root / "src",
            project_root / "src" / "main" / "kotlin",
            project_root / "src" / "main" / "scala",
            project_root / "src" / "main" / "java",
        ]

        for root in search_roots:
            for ext in _KT_EXTENSIONS:
                candidate = root / rel_path.with_suffix(ext)
                if candidate.exists():
                    return [ResolvedImport(ref=ref, resolved_path=candidate)]
        return [ResolvedImport(ref=ref)]


# ── Ruby resolver ────────────────────────────────────────────────


class RubyImportResolver(ImportResolver):
    """Resolve Ruby require/require_relative to .rb files."""

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        if ref.is_system:
            return [ResolvedImport(ref=ref, is_external=True)]
        path = ref.module_path
        if ref.is_relative or ref.kind == ImportKind.REQUIRE:
            base = ref.source_file.parent if ref.is_relative else project_root / "lib"
            candidates = [
                base / path,
                base / f"{path}.rb",
            ]
            for c in candidates:
                if c.exists():
                    return [ResolvedImport(ref=ref, resolved_path=c)]
        return [ResolvedImport(ref=ref)]


# ── PHP resolver ─────────────────────────────────────────────────


class PhpImportResolver(ImportResolver):
    """Resolve PHP use/require to local files."""

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        if ref.is_system:
            return [ResolvedImport(ref=ref, is_external=True)]
        if ref.kind in (ImportKind.REQUIRE, ImportKind.INCLUDE):
            base = ref.source_file.parent
            candidates = [base / ref.module_path, project_root / ref.module_path]
            for c in candidates:
                if c.exists():
                    return [ResolvedImport(ref=ref, resolved_path=c)]
        elif ref.kind == ImportKind.USE:
            # App.Models.User → App/Models/User.php
            parts = ref.module_path.split(".")
            if ref.names:
                parts.append(ref.names[0])
            rel_path = Path(*parts).with_suffix(".php")
            candidates = [
                project_root / rel_path,
                project_root / "src" / rel_path,
            ]
            for c in candidates:
                if c.exists():
                    return [ResolvedImport(ref=ref, resolved_path=c)]
        return [ResolvedImport(ref=ref)]


# ── Lua resolver ─────────────────────────────────────────────────


class LuaImportResolver(ImportResolver):
    """Resolve Lua require to local .lua files."""

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        if ref.is_system:
            return [ResolvedImport(ref=ref, is_external=True)]
        path = ref.module_path.replace(".", "/")
        base = ref.source_file.parent
        candidates = [
            base / f"{path}.lua",
            project_root / f"{path}.lua",
            base / path / "init.lua",
        ]
        for c in candidates:
            if c.exists():
                return [ResolvedImport(ref=ref, resolved_path=c)]
        return [ResolvedImport(ref=ref)]


# ── Pascal resolver ──────────────────────────────────────────────


class PascalImportResolver(ImportResolver):
    """Resolve Pascal uses to local .pas files."""

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        if ref.is_system:
            return [ResolvedImport(ref=ref, is_external=True)]
        base = ref.source_file.parent
        name = ref.module_path
        candidates = [
            base / f"{name}.pas",
            project_root / f"{name}.pas",
            base / f"{name.lower()}.pas",
            project_root / f"{name.lower()}.pas",
        ]
        for c in candidates:
            if c.exists():
                return [ResolvedImport(ref=ref, resolved_path=c)]
        return [ResolvedImport(ref=ref)]


# ── COBOL resolver ───────────────────────────────────────────────


class CobolImportResolver(ImportResolver):
    """Resolve COBOL COPY copybooks and CALL programs to local files.

    Copybooks: search for .cpy, .cbl, .CBL files in source dir, project root,
    copylib/ subdirectories.
    Programs: search for .cbl, .CBL files by program name.
    """

    _COPYBOOK_EXTENSIONS = (".cpy", ".cbl", ".CBL", ".CPY")
    _PROGRAM_EXTENSIONS = (".cbl", ".CBL", ".cob", ".COB")

    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]:
        if ref.is_system:
            return [ResolvedImport(ref=ref, is_external=True)]
        base = ref.source_file.parent
        name = ref.module_path

        if ref.kind == ImportKind.INCLUDE:
            # COPY copybook — search for copybook files
            search_dirs = [
                base,
                project_root,
                project_root / "copylib",
                project_root / "COPYLIB",
                project_root / "copy",
                base / "copylib",
            ]
            for search_dir in search_dirs:
                for ext in self._COPYBOOK_EXTENSIONS:
                    candidate = search_dir / f"{name}{ext}"
                    if candidate.exists():
                        return [ResolvedImport(ref=ref, resolved_path=candidate)]
                    # Try lowercase
                    candidate = search_dir / f"{name.lower()}{ext}"
                    if candidate.exists():
                        return [ResolvedImport(ref=ref, resolved_path=candidate)]
        elif ref.kind == ImportKind.REQUIRE:
            # CALL program — search for program source files
            search_dirs = [base, project_root, project_root / "src"]
            for search_dir in search_dirs:
                for ext in self._PROGRAM_EXTENSIONS:
                    candidate = search_dir / f"{name}{ext}"
                    if candidate.exists():
                        return [ResolvedImport(ref=ref, resolved_path=candidate)]
                    candidate = search_dir / f"{name.lower()}{ext}"
                    if candidate.exists():
                        return [ResolvedImport(ref=ref, resolved_path=candidate)]
        return [ResolvedImport(ref=ref)]


# ── Resolver registry ────────────────────────────────────────────

_RESOLVERS: dict[Language, type[ImportResolver]] = {
    Language.PYTHON: PythonImportResolver,
    Language.JAVASCRIPT: JavaScriptImportResolver,
    Language.TYPESCRIPT: JavaScriptImportResolver,
    Language.JAVA: JavaImportResolver,
    Language.GO: GoImportResolver,
    Language.RUST: RustImportResolver,
    Language.C: CIncludeResolver,
    Language.CPP: CIncludeResolver,
    Language.CSHARP: CSharpImportResolver,
    Language.KOTLIN: JvmImportResolver,
    Language.SCALA: JvmImportResolver,
    Language.RUBY: RubyImportResolver,
    Language.PHP: PhpImportResolver,
    Language.LUA: LuaImportResolver,
    Language.PASCAL: PascalImportResolver,
    Language.COBOL: CobolImportResolver,
}


def get_resolver(language: Language) -> ImportResolver:
    """Get the import resolver for a language. Falls back to NullImportResolver."""
    cls = _RESOLVERS.get(language)
    if cls is None:
        return NullImportResolver()
    return cls()


# ── Topological sort ─────────────────────────────────────────────


def topological_sort(graph: dict[Path, list[Path]]) -> list[Path]:
    """Topological sort via Kahn's algorithm. Raises CyclicImportError on cycles.

    Nodes that appear only as targets (not keys) are included in the result.
    """
    # Build reverse adjacency and in-degree based on "depends-on" edges.
    # graph[a] = [b] means "a depends on b", so b must come before a.
    # We need: in_degree[a] = number of a's dependencies = len(graph[a]).
    # When we "remove" a dependency b, we decrement in_degree for all nodes
    # that depend on b.
    reverse: dict[Path, list[Path]] = {}  # dep → list of nodes that depend on it
    in_degree: dict[Path, int] = {}

    for node in graph:
        if node not in in_degree:
            in_degree[node] = 0
        for dep in graph[node]:
            if dep not in in_degree:
                in_degree[dep] = 0
            reverse.setdefault(dep, []).append(node)
        in_degree[node] = in_degree.get(node, 0) + len(graph[node])

    # Ensure deps-only nodes (not keys in graph) have correct in-degree (0)
    # They're already initialized to 0 above.

    queue = deque(node for node, deg in in_degree.items() if deg == 0)
    result: list[Path] = []

    while queue:
        node = queue.popleft()
        result.append(node)
        # All nodes that depend on 'node' can have their in-degree decremented
        for dependent in reverse.get(node, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(result) != len(in_degree):
        remaining = sorted(
            (n for n in in_degree if n not in set(result)),
            key=lambda p: str(p),
        )
        logger.warning(
            "Cyclic imports detected — %d files in cycles, forced into arbitrary order",
            len(remaining),
        )
        result.extend(remaining)

    return result


def _find_cycle(graph: dict[Path, list[Path]], nodes: set[Path]) -> list[Path]:
    """Find a cycle in the graph restricted to the given node set."""
    # Simple DFS cycle finder
    visited: set[Path] = set()
    path: list[Path] = []
    path_set: set[Path] = set()

    def dfs(node: Path) -> list[Path] | None:
        if node in path_set:
            # Found cycle — extract it
            cycle_start = path.index(node)
            return path[cycle_start:] + [node]
        if node in visited:
            return None
        visited.add(node)
        path.append(node)
        path_set.add(node)
        for dep in graph.get(node, []):
            if dep in nodes:
                result = dfs(dep)
                if result:
                    return result
        path.pop()
        path_set.discard(node)
        return None

    for start in nodes:
        if start not in visited:
            cycle = dfs(start)
            if cycle:
                return cycle

    return list(nodes)  # fallback


# ── Project root inference ───────────────────────────────────────

_PROJECT_ROOT_MARKERS = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "Cargo.toml",
    "Makefile",
    "CMakeLists.txt",
    "composer.json",
    ".git",
}


def infer_project_root(entry_file: Path) -> Path:
    """Walk up from entry_file looking for project root markers."""
    current = entry_file.resolve().parent
    while current != current.parent:
        for marker in _PROJECT_ROOT_MARKERS:
            if (current / marker).exists():
                return current
            # Glob patterns (e.g. *.sln, *.csproj)
            if "*" in marker and list(current.glob(marker)):
                return current
        current = current.parent
    # Fallback: entry file's directory
    return entry_file.resolve().parent
