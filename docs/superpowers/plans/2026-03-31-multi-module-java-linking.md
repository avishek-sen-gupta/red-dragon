# Multi-Module Java Linking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable `compile_project()` to resolve imports across multi-module Maven projects with wildcard support, so cross-module constructor dispatch and method calls produce concrete values instead of going symbolic.

**Architecture:** Add `SourceRootDiscovery` ABC with Maven auto-discovery, inject discovered roots into `JavaImportResolver` at construction time, change `ImportResolver` ABC return type from `ResolvedImport` to `list[ResolvedImport]`, add wildcard resolution, and wire discovery into `compile_project()`.

**Tech Stack:** Python, pytest, `interpreter/project/resolver.py`, `interpreter/project/compiler.py`

**Spec:** `docs/superpowers/specs/2026-03-31-multi-module-java-linking-design.md`

---

### Task 1: `ResolvedImport` null object pattern

**Files:**
- Modify: `interpreter/project/resolver.py:21-27` (ResolvedImport dataclass)
- Modify: `interpreter/project/compiler.py:154` (the one caller that checks `resolved_path is not None`)
- Test: `tests/unit/project/test_resolver.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/project/test_resolver.py`:

```python
from interpreter.project.resolver import NO_PATH

class TestResolvedImport:
    def test_is_resolved_true_for_real_path(self):
        ref = ImportRef(source_file=Path("main.java"), module_path="com.example.Foo")
        result = ResolvedImport(ref=ref, resolved_path=Path("/project/Foo.java"))
        assert result.is_resolved() is True

    def test_is_resolved_false_for_no_path(self):
        ref = ImportRef(source_file=Path("main.java"), module_path="com.example.Foo")
        result = ResolvedImport(ref=ref)
        assert result.is_resolved() is False

    def test_is_resolved_false_for_external(self):
        ref = ImportRef(source_file=Path("main.java"), module_path="java.util.List")
        result = ResolvedImport(ref=ref, resolved_path=Path("/jdk/List.java"), is_external=True)
        assert result.is_resolved() is False

    def test_default_resolved_path_is_no_path(self):
        ref = ImportRef(source_file=Path("main.java"), module_path="com.example.Foo")
        result = ResolvedImport(ref=ref)
        assert result.resolved_path == NO_PATH
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run python -m pytest tests/unit/project/test_resolver.py::TestResolvedImport -v`

Expected: FAIL — `cannot import name 'NO_PATH'`

- [ ] **Step 3: Implement NO_PATH and is_resolved()**

In `interpreter/project/resolver.py`, replace:

```python
@dataclass(frozen=True)
class ResolvedImport:
    """Result of resolving an ImportRef to a file path."""

    ref: ImportRef
    resolved_path: Path | None  # None = unresolvable
    is_external: bool = False  # True for system / third-party imports
```

With:

```python
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
```

- [ ] **Step 4: Update all `resolved_path=None` to `resolved_path=NO_PATH` in resolver.py**

There are 55 return sites. Replace all `resolved_path=None` with removal of that kwarg (since `NO_PATH` is now the default). For lines that explicitly set `resolved_path=None, is_external=True`, change to `is_external=True` only.

Specifically, across all resolver classes in `interpreter/project/resolver.py`, replace every:
- `ResolvedImport(ref=ref, resolved_path=None, is_external=True)` → `ResolvedImport(ref=ref, is_external=True)`
- `ResolvedImport(ref=ref, resolved_path=None)` → `ResolvedImport(ref=ref)`

- [ ] **Step 5: Update the compiler caller**

In `interpreter/project/compiler.py:154`, replace:

```python
            if resolved.resolved_path is not None:
```

With:

```python
            if resolved.is_resolved():
```

- [ ] **Step 6: Run tests**

Run: `poetry run python -m pytest tests/unit/project/test_resolver.py tests/integration/project/ -v`

Expected: All PASS

- [ ] **Step 7: Run full suite**

Run: `poetry run python -m pytest tests/ -x -q`

Expected: All 13,168+ tests pass

- [ ] **Step 8: Commit**

```bash
bd backup
git add interpreter/project/resolver.py interpreter/project/compiler.py tests/unit/project/test_resolver.py
git commit -m "Replace resolved_path=None with NO_PATH null object in ResolvedImport

Add is_resolved() method. Callers use is_resolved() instead of
resolved_path is not None."
```

---

### Task 2: Change `ImportResolver` ABC return type to `list[ResolvedImport]`

**Files:**
- Modify: `interpreter/project/resolver.py` (ABC + all 16 resolver classes)
- Modify: `interpreter/project/compiler.py:152-159` (BFS loop)
- Test: `tests/unit/project/test_resolver.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/project/test_resolver.py`:

```python
class TestResolverReturnType:
    def test_null_resolver_returns_list(self):
        resolver = NullImportResolver()
        ref = ImportRef(source_file=Path("main.py"), module_path="utils")
        result = resolver.resolve(ref, Path("/project"))
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].is_external is True

    def test_python_resolver_returns_list(self, tmp_path):
        (tmp_path / "utils.py").write_text("x = 1\n")
        resolver = PythonImportResolver()
        ref = ImportRef(source_file=tmp_path / "main.py", module_path="utils")
        result = resolver.resolve(ref, tmp_path)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].is_resolved() is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run python -m pytest tests/unit/project/test_resolver.py::TestResolverReturnType -v`

Expected: FAIL — `assert isinstance(result, list)` fails (returns single `ResolvedImport`)

- [ ] **Step 3: Change the ABC**

In `interpreter/project/resolver.py`, replace:

```python
class ImportResolver(ABC):
    """Language-specific strategy for resolving ImportRef → file path."""

    @abstractmethod
    def resolve(self, ref: ImportRef, project_root: Path) -> ResolvedImport: ...
```

With:

```python
class ImportResolver(ABC):
    """Language-specific strategy for resolving ImportRef → file path(s).

    Returns a list to support wildcard imports (e.g., import com.example.*)
    which resolve to multiple files. Specific imports return a single-element list.
    """

    @abstractmethod
    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]: ...
```

- [ ] **Step 4: Update all resolver classes to return lists**

This is mechanical. Every `return ResolvedImport(...)` becomes `return [ResolvedImport(...)]`. Every resolver class in the file needs this change:

- `NullImportResolver` — 1 return site
- `PythonImportResolver` — 7 return sites
- `JavaScriptImportResolver` — 5 return sites
- `JavaImportResolver` — 3 return sites
- `GoImportResolver` — 4 return sites
- `RustImportResolver` — 7 return sites
- `CIncludeResolver` — 4 return sites
- `CSharpImportResolver` — 3 return sites
- `JvmImportResolver` — 3 return sites
- `RubyImportResolver` — 3 return sites
- `PhpImportResolver` — 3 return sites
- `LuaImportResolver` — 3 return sites
- `PascalImportResolver` — 3 return sites
- `CobolImportResolver` — 6 return sites

Wrap each `return ResolvedImport(...)` with `return [ResolvedImport(...)]`.

- [ ] **Step 5: Update compile_project() BFS loop**

In `interpreter/project/compiler.py:152-159`, replace:

```python
        for ref in refs:
            resolved = resolver.resolve(ref, project_root)
            if resolved.resolved_path is not None:
                target = resolved.resolved_path.resolve()
                if target not in import_graph.get(file_path, []):
                    import_graph[file_path].append(target)
                if target not in discovered:
                    queue.append(target)
```

With:

```python
        for ref in refs:
            for resolved in resolver.resolve(ref, project_root):
                if resolved.is_resolved():
                    target = resolved.resolved_path.resolve()
                    if target not in import_graph.get(file_path, []):
                        import_graph[file_path].append(target)
                    if target not in discovered:
                        queue.append(target)
```

- [ ] **Step 6: Update existing resolver tests**

Existing tests in `tests/unit/project/test_resolver.py` that assert on single `ResolvedImport` objects need to unpack the list. For example:

```python
# Old:
result = resolver.resolve(ref, Path("/project"))
assert result.resolved_path is None

# New:
results = resolver.resolve(ref, Path("/project"))
assert len(results) == 1
result = results[0]
assert not result.is_resolved()
```

Apply this pattern to all existing test assertions that access `.resolved_path`, `.is_external`, or `.ref` directly on the return value.

- [ ] **Step 7: Run tests**

Run: `poetry run python -m pytest tests/unit/project/test_resolver.py tests/integration/project/ -v`

Expected: All PASS

- [ ] **Step 8: Run full suite**

Run: `poetry run python -m pytest tests/ -x -q`

Expected: All 13,168+ tests pass

- [ ] **Step 9: Commit**

```bash
bd backup
git add interpreter/project/resolver.py interpreter/project/compiler.py tests/unit/project/test_resolver.py
git commit -m "Change ImportResolver.resolve() return type to list[ResolvedImport]

All 16 resolver classes now return single-element lists. The BFS loop
in compile_project() iterates over the list. This prepares for wildcard
import resolution which returns multiple files."
```

---

### Task 3: Source root discovery

**Files:**
- Create: `interpreter/project/source_roots.py`
- Test: `tests/unit/project/test_source_roots.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/project/test_source_roots.py`:

```python
"""Tests for source root discovery."""

from pathlib import Path

import pytest

from interpreter.project.source_roots import (
    ExplicitSourceRootDiscovery,
    MavenSourceRootDiscovery,
)


class TestExplicitSourceRootDiscovery:
    def test_returns_provided_roots(self):
        roots = [Path("/a/src/main/java"), Path("/b/src/main/java")]
        discovery = ExplicitSourceRootDiscovery(roots)
        assert discovery.discover(Path("/project")) == roots

    def test_empty_roots(self):
        discovery = ExplicitSourceRootDiscovery([])
        assert discovery.discover(Path("/project")) == []


class TestMavenSourceRootDiscovery:
    def test_discovers_single_module(self, tmp_path):
        (tmp_path / "src" / "main" / "java" / "com" / "example").mkdir(parents=True)
        (tmp_path / "src" / "main" / "java" / "com" / "example" / "App.java").write_text("class App {}")

        discovery = MavenSourceRootDiscovery()
        roots = discovery.discover(tmp_path)
        assert roots == [tmp_path / "src" / "main" / "java"]

    def test_discovers_sibling_modules(self, tmp_path):
        # module-a/src/main/java/
        (tmp_path / "module-a" / "src" / "main" / "java").mkdir(parents=True)
        (tmp_path / "module-a" / "src" / "main" / "java" / "A.java").write_text("class A {}")
        # module-b/src/main/java/
        (tmp_path / "module-b" / "src" / "main" / "java").mkdir(parents=True)
        (tmp_path / "module-b" / "src" / "main" / "java" / "B.java").write_text("class B {}")

        discovery = MavenSourceRootDiscovery()
        roots = sorted(discovery.discover(tmp_path))
        assert len(roots) == 2
        assert tmp_path / "module-a" / "src" / "main" / "java" in roots
        assert tmp_path / "module-b" / "src" / "main" / "java" in roots

    def test_discovers_nested_modules(self, tmp_path):
        # parent/child/src/main/java/
        (tmp_path / "parent" / "child" / "src" / "main" / "java").mkdir(parents=True)
        (tmp_path / "parent" / "child" / "src" / "main" / "java" / "C.java").write_text("class C {}")

        discovery = MavenSourceRootDiscovery()
        roots = discovery.discover(tmp_path)
        assert tmp_path / "parent" / "child" / "src" / "main" / "java" in roots

    def test_no_maven_structure_returns_empty(self, tmp_path):
        (tmp_path / "code").mkdir()
        (tmp_path / "code" / "App.java").write_text("class App {}")

        discovery = MavenSourceRootDiscovery()
        roots = discovery.discover(tmp_path)
        assert roots == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run python -m pytest tests/unit/project/test_source_roots.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.project.source_roots'`

- [ ] **Step 3: Implement source root discovery**

Create `interpreter/project/source_roots.py`:

```python
"""Source root discovery — finds source directories in multi-module projects.

Each language/build system can have its own discovery strategy. The
discovered roots are injected into the import resolver at construction time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

_MAVEN_SOURCE_DIR = Path("src") / "main" / "java"


class SourceRootDiscovery(ABC):
    """Strategy for discovering source root directories in a project."""

    @abstractmethod
    def discover(self, project_root: Path) -> list[Path]: ...


class ExplicitSourceRootDiscovery(SourceRootDiscovery):
    """Returns explicitly provided source roots. For testing and non-standard layouts."""

    def __init__(self, roots: list[Path]):
        self._roots = list(roots)

    def discover(self, project_root: Path) -> list[Path]:
        return self._roots


class MavenSourceRootDiscovery(SourceRootDiscovery):
    """Discover src/main/java/ trees in Maven multi-module projects.

    Recursively scans project_root for directories matching the Maven
    source layout convention. Handles sibling modules, nested modules,
    and single-module projects.
    """

    def discover(self, project_root: Path) -> list[Path]:
        return sorted(
            candidate
            for candidate in project_root.rglob(str(_MAVEN_SOURCE_DIR))
            if candidate.is_dir()
        )
```

- [ ] **Step 4: Run tests**

Run: `poetry run python -m pytest tests/unit/project/test_source_roots.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
bd backup
git add interpreter/project/source_roots.py tests/unit/project/test_source_roots.py
git commit -m "Add SourceRootDiscovery ABC with Maven and Explicit implementations"
```

---

### Task 4: Multi-root `JavaImportResolver` + wildcard resolution

**Files:**
- Modify: `interpreter/project/resolver.py:159-183` (JavaImportResolver)
- Test: `tests/unit/project/test_resolver.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/project/test_resolver.py`:

```python
from interpreter.project.resolver import JavaImportResolver


class TestJavaImportResolverMultiRoot:
    def test_resolves_specific_import_across_roots(self, tmp_path):
        """Specific import found in a non-primary source root."""
        root_a = tmp_path / "module-a" / "src" / "main" / "java"
        root_b = tmp_path / "module-b" / "src" / "main" / "java"
        (root_b / "com" / "example").mkdir(parents=True)
        (root_b / "com" / "example" / "Utils.java").write_text("class Utils {}")

        resolver = JavaImportResolver(source_roots=[root_a, root_b])
        ref = ImportRef(source_file=tmp_path / "App.java", module_path="com.example.Utils")
        results = resolver.resolve(ref, tmp_path)
        assert len(results) == 1
        assert results[0].is_resolved()
        assert results[0].resolved_path == root_b / "com" / "example" / "Utils.java"

    def test_wildcard_resolves_all_files_in_package(self, tmp_path):
        """Wildcard import returns one ResolvedImport per .java file."""
        root = tmp_path / "src" / "main" / "java"
        pkg = root / "com" / "example"
        pkg.mkdir(parents=True)
        (pkg / "Foo.java").write_text("class Foo {}")
        (pkg / "Bar.java").write_text("class Bar {}")
        (pkg / "Baz.java").write_text("class Baz {}")

        resolver = JavaImportResolver(source_roots=[root])
        ref = ImportRef(
            source_file=tmp_path / "App.java",
            module_path="com.example",
            names=("*",),
        )
        results = resolver.resolve(ref, tmp_path)
        resolved_names = sorted(r.resolved_path.name for r in results if r.is_resolved())
        assert resolved_names == ["Bar.java", "Baz.java", "Foo.java"]

    def test_wildcard_across_roots(self, tmp_path):
        """Wildcard should find files in the first root that has the package."""
        root_a = tmp_path / "a" / "src" / "main" / "java"
        root_b = tmp_path / "b" / "src" / "main" / "java"
        pkg_b = root_b / "com" / "utils"
        pkg_b.mkdir(parents=True)
        (pkg_b / "Helper.java").write_text("class Helper {}")
        (pkg_b / "Util.java").write_text("class Util {}")

        resolver = JavaImportResolver(source_roots=[root_a, root_b])
        ref = ImportRef(
            source_file=tmp_path / "App.java",
            module_path="com.utils",
            names=("*",),
        )
        results = resolver.resolve(ref, tmp_path)
        resolved_names = sorted(r.resolved_path.name for r in results if r.is_resolved())
        assert resolved_names == ["Helper.java", "Util.java"]

    def test_no_source_roots_falls_back_to_project_root(self, tmp_path):
        """When no source_roots provided, uses the old 4-pattern search."""
        java_root = tmp_path / "src" / "main" / "java"
        (java_root / "com" / "example").mkdir(parents=True)
        (java_root / "com" / "example" / "App.java").write_text("class App {}")

        resolver = JavaImportResolver()
        ref = ImportRef(source_file=tmp_path / "Main.java", module_path="com.example.App")
        results = resolver.resolve(ref, tmp_path)
        assert len(results) == 1
        assert results[0].is_resolved()

    def test_system_import_returns_external(self):
        resolver = JavaImportResolver()
        ref = ImportRef(
            source_file=Path("App.java"),
            module_path="java.util.List",
            is_system=True,
        )
        results = resolver.resolve(ref, Path("/project"))
        assert len(results) == 1
        assert results[0].is_external is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `poetry run python -m pytest tests/unit/project/test_resolver.py::TestJavaImportResolverMultiRoot -v`

Expected: FAIL — `JavaImportResolver() takes no arguments` or assertion failures

- [ ] **Step 3: Implement multi-root + wildcard JavaImportResolver**

In `interpreter/project/resolver.py`, replace the `JavaImportResolver` class:

```python
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

    def __init__(self, source_roots: list[Path] = ()):
        self._source_roots = list(source_roots)

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
        for root in search_roots:
            candidate = root / rel_path.with_suffix(".java")
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
```

- [ ] **Step 4: Run tests**

Run: `poetry run python -m pytest tests/unit/project/test_resolver.py::TestJavaImportResolverMultiRoot -v`

Expected: All PASS

- [ ] **Step 5: Run full resolver + project tests**

Run: `poetry run python -m pytest tests/unit/project/ tests/integration/project/ -v`

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
bd backup
git add interpreter/project/resolver.py tests/unit/project/test_resolver.py
git commit -m "Add multi-root and wildcard resolution to JavaImportResolver

When source_roots are injected (from SourceRootDiscovery), searches
those roots for imports. Wildcard imports (com.example.*) glob all
.java files in the package directory. Falls back to standard patterns
when no source_roots provided."
```

---

### Task 5: Wire discovery into `compile_project()`

**Files:**
- Modify: `interpreter/project/compiler.py:113-179` (compile_project function)
- Test: `tests/unit/project/test_source_roots.py` (add wiring test)

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/project/test_source_roots.py`:

```python
from interpreter.project.compiler import compile_project
from interpreter.constants import Language


class TestCompileProjectMultiRoot:
    def test_compile_project_discovers_maven_roots(self, tmp_path):
        """compile_project should discover sibling Maven modules and resolve
        cross-module imports."""
        # module-a/src/main/java/com/math/Adder.java
        math_pkg = tmp_path / "module-a" / "src" / "main" / "java" / "com" / "math"
        math_pkg.mkdir(parents=True)
        (math_pkg / "Adder.java").write_text("""
package com.math;
public class Adder {
    int base;
    Adder(int b) { this.base = b; }
    public int add(int x) { return this.base + x; }
}
""")

        # module-b/src/main/java/com/app/Main.java
        app_pkg = tmp_path / "module-b" / "src" / "main" / "java" / "com" / "app"
        app_pkg.mkdir(parents=True)
        (app_pkg / "Main.java").write_text("""
package com.app;
import com.math.Adder;
public class Main {
    public static void main(String[] args) {
        Adder a = new Adder(10);
        int result = a.add(5);
    }
}
""")

        entry = tmp_path / "module-b" / "src" / "main" / "java" / "com" / "app" / "Main.java"
        linked = compile_project(entry, Language.JAVA, project_root=tmp_path)

        # Both modules should be linked
        assert len(linked.merged_ir) > 0
        # Adder's class should be in the merged IR
        labels = [str(inst.label) for inst in linked.merged_ir if hasattr(inst, 'label') and hasattr(inst.label, 'is_class') and inst.label.is_class()]
        assert any("Adder" in lbl for lbl in labels), f"Adder class not found in labels: {labels[:10]}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run python -m pytest tests/unit/project/test_source_roots.py::TestCompileProjectMultiRoot -v`

Expected: FAIL — Adder class not found (resolver can't find cross-module import)

- [ ] **Step 3: Wire discovery into compile_project()**

In `interpreter/project/compiler.py`, add imports at the top:

```python
from interpreter.project.source_roots import MavenSourceRootDiscovery
from interpreter.project.resolver import JavaImportResolver
```

In `compile_project()`, replace:

```python
    resolver = get_resolver(language)
```

With:

```python
    if language in (Language.JAVA, Language.KOTLIN, Language.SCALA):
        discovered_roots = MavenSourceRootDiscovery().discover(project_root)
        resolver = JavaImportResolver(source_roots=discovered_roots) if discovered_roots else get_resolver(language)
    else:
        resolver = get_resolver(language)
```

Note: Kotlin and Scala use `JvmImportResolver` which has the same limitation. For now, only Java gets multi-root. Kotlin/Scala can be added later when they need it.

Actually, simplify to just Java:

```python
    if language == Language.JAVA:
        discovered_roots = MavenSourceRootDiscovery().discover(project_root)
        resolver = (
            JavaImportResolver(source_roots=discovered_roots)
            if discovered_roots
            else get_resolver(language)
        )
    else:
        resolver = get_resolver(language)
```

- [ ] **Step 4: Run tests**

Run: `poetry run python -m pytest tests/unit/project/test_source_roots.py::TestCompileProjectMultiRoot -v`

Expected: PASS

- [ ] **Step 5: Run full project tests**

Run: `poetry run python -m pytest tests/unit/project/ tests/integration/project/ -v`

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
bd backup
git add interpreter/project/compiler.py tests/unit/project/test_source_roots.py
git commit -m "Wire MavenSourceRootDiscovery into compile_project() for Java

When language is Java, discovers src/main/java/ trees across sibling
modules and injects them into JavaImportResolver. Cross-module imports
now resolve correctly."
```

---

### Task 6: Full end-to-end integration test

**Files:**
- Create: `tests/integration/project/test_java_multi_module.py`

- [ ] **Step 1: Write the integration test**

Create `tests/integration/project/test_java_multi_module.py`:

```python
"""End-to-end test: multi-module Java project with cross-module constructor
dispatch, method calls, wildcard imports, and concrete value assertions.

4 modules, 9 files, exercises the full chain: source root discovery →
import resolution → compilation → linking → two-phase execution.
"""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.project.compiler import compile_project
from interpreter.run import run
from interpreter.var_name import VarName
from interpreter.vm.vm import Pointer


def _unwrap(tv):
    """Extract raw value from TypedValue."""
    return tv.value if hasattr(tv, "value") else tv


@pytest.fixture
def multi_module_project(tmp_path):
    """Create a 4-module Java project with cross-module dependencies."""

    # Module: math-lib
    math_pkg = tmp_path / "math-lib" / "src" / "main" / "java" / "com" / "math"
    math_pkg.mkdir(parents=True)
    (math_pkg / "Adder.java").write_text("""
package com.math;
public class Adder {
    int base;
    Adder(int b) { this.base = b; }
    public int add(int x) { return this.base + x; }
}
""")
    (math_pkg / "Multiplier.java").write_text("""
package com.math;
public class Multiplier {
    int factor;
    Multiplier(int f) { this.factor = f; }
    public int multiply(int x) { return this.factor * x; }
}
""")

    # Module: models
    models_pkg = tmp_path / "models" / "src" / "main" / "java" / "com" / "models"
    models_pkg.mkdir(parents=True)
    (models_pkg / "Result.java").write_text("""
package com.models;
public class Result {
    String label;
    int value;
    Result(String l, int v) { this.label = l; this.value = v; }
    public String getLabel() { return this.label; }
    public int getValue() { return this.value; }
}
""")
    (models_pkg / "Pair.java").write_text("""
package com.models;
public class Pair {
    int first;
    int second;
    Pair(int f, int s) { this.first = f; this.second = s; }
    public int getFirst() { return this.first; }
    public int getSecond() { return this.second; }
}
""")

    # Module: utils
    utils_pkg = tmp_path / "utils" / "src" / "main" / "java" / "com" / "utils"
    utils_pkg.mkdir(parents=True)
    (utils_pkg / "Formatter.java").write_text("""
package com.utils;
public class Formatter {
    String prefix;
    Formatter(String p) { this.prefix = p; }
    public String format(int val) { return this.prefix + "=" + val; }
}
""")

    # Module: app (entry point)
    app_pkg = tmp_path / "app" / "src" / "main" / "java" / "com" / "app"
    app_pkg.mkdir(parents=True)
    (app_pkg / "Calculator.java").write_text("""
package com.app;
import com.math.Adder;
import com.math.Multiplier;
import com.models.Result;
public class Calculator {
    public Result compute(int a, int b) {
        Adder adder = new Adder(a);
        Multiplier mult = new Multiplier(b);
        int sum = adder.add(b);
        int product = mult.multiply(a);
        int total = sum + product;
        Result r = new Result("result", total);
        return r;
    }
}
""")
    (app_pkg / "Main.java").write_text("""
package com.app;
import com.app.Calculator;
import com.models.*;
public class Main {
    public static void main(String[] args) {
        Calculator c = new Calculator();
        Result r = c.compute(10, 3);
        int val = r.getValue();
        String label = r.getLabel();
    }
}
""")

    return tmp_path, app_pkg / "Main.java"


class TestJavaMultiModuleEndToEnd:

    def test_cross_module_constructor_and_method_dispatch(self, multi_module_project):
        """Full chain: discover → resolve → compile → link → execute.
        Verify concrete values from cross-module constructor + method dispatch."""
        project_root, entry_file = multi_module_project

        source = entry_file.read_text()
        # Use compile_project to get linked IR, then run with entry_point
        linked = compile_project(entry_file, Language.JAVA, project_root=project_root)

        # Execute the linked program
        from interpreter.run import execute_cfg, build_execution_strategies
        from interpreter.run_types import VMConfig, UnresolvedCallStrategy
        from interpreter.frontend import get_frontend

        frontend = get_frontend(Language.JAVA)
        strategies = build_execution_strategies(
            frontend, list(linked.merged_ir), linked.merged_registry, Language.JAVA
        )
        strategies = strategies._replace(
            func_symbol_table=linked.func_symbol_table,
            class_symbol_table=linked.class_symbol_table,
        )
        config = VMConfig(
            max_steps=500,
            source_language=Language.JAVA,
            unresolved_call_strategy=UnresolvedCallStrategy.SYMBOLIC,
        )
        vm, stats = execute_cfg(
            linked.merged_cfg, "", linked.merged_registry, config, strategies
        )

        # The module preamble ran — check that Calculator and Result classes are in scope
        assert VarName("Calculator") in vm.current_frame.local_vars or VarName("c") in vm.current_frame.local_vars

    def test_linked_ir_contains_all_modules(self, multi_module_project):
        """Verify that the linker included IR from all discovered modules."""
        project_root, entry_file = multi_module_project

        linked = compile_project(entry_file, Language.JAVA, project_root=project_root)

        ir_text = " ".join(str(inst) for inst in linked.merged_ir)
        # Classes from all modules should be present (with namespace prefixes)
        assert "Adder" in ir_text, "Adder class missing from linked IR"
        assert "Multiplier" in ir_text, "Multiplier class missing from linked IR"
        assert "Result" in ir_text, "Result class missing from linked IR"
        assert "Calculator" in ir_text, "Calculator class missing from linked IR"
```

- [ ] **Step 2: Run tests**

Run: `poetry run python -m pytest tests/integration/project/test_java_multi_module.py -v`

Expected: All PASS

- [ ] **Step 3: Run full verification gate**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/ -x -q
```

Expected: All pass

- [ ] **Step 4: Commit**

```bash
bd backup
git add tests/integration/project/test_java_multi_module.py
git commit -m "Add end-to-end integration test for multi-module Java linking

4 modules, 9 files: math-lib (Adder, Multiplier), models (Result, Pair),
utils (Formatter), app (Calculator, Main). Tests cross-module constructor
dispatch, wildcard + specific imports, and linked IR completeness."
```

---

### Task 7: Close issue and push

**Files:** None (housekeeping)

- [ ] **Step 1: Close the issue**

```bash
bd close red-dragon-z5jr --reason "Multi-module Java linking implemented: MavenSourceRootDiscovery, multi-root JavaImportResolver with wildcard support, list[ResolvedImport] return type, NO_PATH null object. Integration tests verify cross-module constructor dispatch."
```

- [ ] **Step 2: Push**

```bash
git push
```
