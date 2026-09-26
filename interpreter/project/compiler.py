# pyright: standard
"""Per-module compiler and directory compilation orchestrator.

compile_module(): file → ModuleUnit
compile_directory(): directory → LinkedProgram (scan → compile → link)
build_export_table(): IR + symbol tables → ExportTable
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from interpreter import constants
from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.func_name import FuncName
from interpreter.instructions import (
    DeclVar,
    ImportModule,
    InstructionBase,
    Label_,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.namespace import NamespaceResolver
from interpreter.path_name import NO_PATH_NAME, PathName
from interpreter.project.imports import extract_imports
from interpreter.project.linker import link_modules
from interpreter.project.resolver import (
    ImportResolver,
    JavaImportResolver,
    get_resolver,
    topological_sort,
)
from interpreter.project.source_roots import MavenSourceRootDiscovery
from interpreter.project.types import ExportTable, LinkedProgram, ModuleUnit
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter.register import Register
from interpreter.var_name import VarName

# ── Resolved imports mapping ─────────────────────────────────────


def _build_resolved_imports_map(
    modules: dict[Path, ModuleUnit],
    import_graph: dict[Path, list[Path]],
    resolver: ImportResolver,
    directory: Path,
) -> dict[Path, dict[str, PathName]]:
    """Build a mapping from each module to resolved import paths.

    For each module, creates a dict mapping the original import strings (as they
    appear in IMPORT_MODULE instructions) to PathName objects representing the
    resolved file paths. This is used during Pass 2 (IMPORT_MODULE patching)
    to fill in resolved_path fields.

    Args:
        modules: Dict of file path -> ModuleUnit
        import_graph: Dict of file path -> list of dependency file paths
        resolver: ImportResolver for resolving module names to paths
        directory: Project root directory

    Returns:
        {module_path: {import_module_path: PathName(resolved_file), ...}, ...}
    """
    resolved_imports_map: dict[Path, dict[str, PathName]] = {}
    # Build a normalized lookup table: resolved paths → module paths
    # (handles symlinks and /private/ prefix on macOS)
    normalized_modules: dict[Path, Path] = {p.resolve(): p for p in modules.keys()}

    for module_path, module in modules.items():
        resolved_imports_map[module_path] = {}
        # For each ImportRef in the module's imports list, resolve it and store
        # the mapping from the original module_path (as written in source) to the resolved file path
        for import_ref in module.imports:
            # Resolve this import to get all possible targets
            for resolved in resolver.resolve(import_ref, directory):
                if resolved.is_resolved():
                    target = resolved.resolved_path.resolve()
                    if target in normalized_modules:
                        # Map the module_path string (as it appears in IMPORT_MODULE) to the resolved file path
                        resolved_imports_map[module_path][import_ref.module_path] = (
                            PathName(str(target))
                        )

    return resolved_imports_map


def _patch_import_module_instructions(
    module: ModuleUnit, resolved_map: dict[str, PathName]
) -> tuple[InstructionBase, ...]:
    """Patch IMPORT_MODULE instructions in a module's IR with resolved paths.

    During Pass 1 (frontend lowering), IMPORT_MODULE instructions have
    resolved_path=NO_PATH_NAME. This function patches them with actual PathName
    objects from the resolved_map (built from the import_graph).

    Args:
        module: The ModuleUnit with potentially-unpatched IMPORT_MODULE instructions.
        resolved_map: Mapping from module_path strings to PathName objects.

    Returns:
        A new IR tuple with IMPORT_MODULE instructions patched.
    """
    result: list[InstructionBase] = []

    for inst in module.ir:
        if isinstance(inst, ImportModule):
            # Found an IMPORT_MODULE instruction. Try to patch its resolved_path.
            resolved_path = resolved_map.get(inst.module_path, NO_PATH_NAME)
            patched = dataclasses.replace(inst, resolved_path=resolved_path)
            result.append(patched)
        else:
            result.append(inst)

    return tuple(result)


def build_export_table(
    ir: list[InstructionBase] | tuple[InstructionBase, ...],
    func_symbol_table: dict[CodeLabel, FuncRef],
    class_symbol_table: dict[CodeLabel, ClassRef],
) -> ExportTable:
    """Build an export table from IR instructions and symbol tables.

    Functions and classes come from the symbol tables (populated during lowering).
    Top-level variables come from DECL_VAR instructions at module scope — i.e.
    outside any function or class body.
    """
    functions = {ref.name: ref.label for ref in func_symbol_table.values()}
    classes = {ref.name: ref.label for ref in class_symbol_table.values()}

    # Scan for top-level DECL_VARs (those outside func/class scopes).
    variables: dict[VarName, Register] = {}
    in_scope = True  # True while at module top-level
    for inst in ir:
        typed = inst
        if isinstance(typed, Label_) and typed.label.is_present():
            is_func_start = typed.label.is_function()
            is_class_start = typed.label.is_class()
            is_end = typed.label.is_end_label()

            if is_func_start or is_class_start:
                in_scope = False
            elif is_end:
                in_scope = True

        if in_scope and isinstance(typed, (DeclVar, StoreVar)):
            # Don't duplicate names already in functions or classes
            if (
                FuncName(str(typed.name)) not in functions
                and ClassName(str(typed.name)) not in classes
            ):
                variables[typed.name] = typed.value_reg

    return ExportTable(functions=functions, classes=classes, variables=variables)


def _collect_copybook_dirs(directory: Path) -> list[Path]:
    """Project root plus every subdirectory, for copybook resolution."""
    directory = directory.resolve()
    subdirs = [p for p in directory.rglob("*") if p.is_dir()]
    return [directory, *subdirs]


def compile_module(
    file_path: Path,
    language: Language,
    source: bytes | None = None,
    namespace_resolver: NamespaceResolver = NamespaceResolver(),
    copybook_dirs: list[Path] = [],
) -> ModuleUnit:
    """Compile a single file into a ModuleUnit.

    This is the existing single-file pipeline (lower → IR) plus export
    extraction. No CFG or registry is built here — that happens once
    after linking on the merged IR.
    """
    if source is None:
        source = file_path.read_bytes()

    resolved_frontend_type = (
        constants.FRONTEND_COBOL
        if language == Language.COBOL
        else constants.FRONTEND_DETERMINISTIC
    )
    frontend = get_frontend(
        language,
        frontend_type=resolved_frontend_type,
        copybook_dirs=copybook_dirs,
    )
    ir = frontend.lower(source, namespace_resolver=namespace_resolver)

    exports = build_export_table(
        ir,
        frontend.func_symbol_table,
        frontend.class_symbol_table,
    )

    imports = tuple(extract_imports(source, file_path, language))

    return ModuleUnit(
        path=file_path,
        language=language,
        ir=tuple(ir),
        exports=exports,
        imports=imports,
        symbol_table=frontend.symbol_table,
    )


# ── File extension mapping ───────────────────────────────────────

_LANGUAGE_EXTENSIONS: dict[Language, tuple[str, ...]] = {
    Language.PYTHON: (".py",),
    Language.JAVASCRIPT: (".js", ".mjs", ".cjs"),
    Language.TYPESCRIPT: (".ts", ".tsx"),
    Language.JAVA: (".java",),
    Language.GO: (".go",),
    Language.RUST: (".rs",),
    Language.C: (".c", ".h"),
    Language.CPP: (".cpp", ".cc", ".cxx", ".hpp", ".h"),
    Language.CSHARP: (".cs",),
    Language.KOTLIN: (".kt", ".kts"),
    Language.SCALA: (".scala",),
    Language.RUBY: (".rb",),
    Language.PHP: (".php",),
    Language.LUA: (".lua",),
    Language.PASCAL: (".pas", ".pp"),
    Language.COBOL: (".cbl", ".cob", ".cpy"),
}

# Extensions that are copybook *fragments*, not standalone compilation units.
# They are resolved into the programs that COPY them (via copybook_dirs) and
# must never be compiled on their own — they have no IDENTIFICATION DIVISION.
_COPYBOOK_EXTENSIONS: dict[Language, frozenset[str]] = {
    Language.COBOL: frozenset({".cpy"}),
}


def compile_directory(
    directory: Path,
    language: Language,
) -> LinkedProgram:
    """Compile all source files in a directory tree.

    Compiles every file matching the language's extensions — catches
    orphaned modules, test files, and files not reachable via imports.

    Args:
        directory: Root directory to scan recursively.
        language: Source language — determines which file extensions to include.

    Returns:
        A LinkedProgram with all files compiled and linked.

    Raises:
        FileNotFoundError: If the directory does not exist.
    """
    directory = directory.resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    copybook_dirs = _collect_copybook_dirs(directory)

    extensions = _LANGUAGE_EXTENSIONS.get(language, ())
    copybook_exts = _COPYBOOK_EXTENSIONS.get(language, frozenset())
    source_files = sorted(
        f.resolve()
        for ext in extensions
        if ext not in copybook_exts
        for f in directory.rglob(f"*{ext}")
        if f.is_file()
    )

    # --- Java namespace resolution: pre-scan + build tree ---
    namespace_resolver: NamespaceResolver = NamespaceResolver()
    if language == Language.JAVA:
        from experiments.java_stdlib.registry import STDLIB_REGISTRY
        from interpreter.frontends.java.namespace import (
            JavaNamespaceResolver,
            build_java_namespace_tree,
            java_pre_scan,
        )

        scan_results = {path: java_pre_scan(path.read_bytes()) for path in source_files}
        tree = build_java_namespace_tree(scan_results, STDLIB_REGISTRY)
        namespace_resolver = JavaNamespaceResolver(tree)

    # --- PASS 1: Compile each module (with namespace resolver if available) ---
    modules = {
        path: compile_module(
            path,
            language,
            namespace_resolver=namespace_resolver,
            copybook_dirs=copybook_dirs,
        )
        for path in source_files
    }

    # --- Java stdlib: inject pre-built IR modules for system imports ---
    stdlib_edges: dict[Path, list[Path]] = {}  # user_path → [stdlib_path, ...]
    if language == Language.JAVA:
        stdlib_needed: dict[Path, ModuleUnit] = {}
        for user_path, module in list(modules.items()):
            for ref in module.imports:
                if not ref.is_system:
                    continue
                for name in ref.names:
                    stub_key = Path(ref.module_path.replace(".", "/")) / f"{name}.java"
                    if stub_key in STDLIB_REGISTRY:
                        if stub_key not in stdlib_needed:
                            stdlib_needed[stub_key] = STDLIB_REGISTRY[stub_key]
                        stdlib_edges.setdefault(user_path, [])
                        if stub_key not in stdlib_edges[user_path]:
                            stdlib_edges[user_path].append(stub_key)
        for stub_key, stub_module in stdlib_needed.items():
            modules[stub_key] = stub_module

    # --- Build import graph from modules' resolved imports ---
    if language == Language.JAVA:
        discovered_roots = MavenSourceRootDiscovery().discover(directory)
        resolver = (
            JavaImportResolver(source_roots=discovered_roots)
            if discovered_roots
            else get_resolver(language)
        )
    else:
        resolver = get_resolver(language)

    import_graph: dict[Path, list[Path]] = {path: [] for path in modules}
    for path, module in modules.items():
        for ref in module.imports:
            for resolved in resolver.resolve(ref, directory):
                if resolved.is_resolved():
                    target = resolved.resolved_path.resolve()
                    if target in import_graph and target not in import_graph[path]:
                        import_graph[path].append(target)
                    # For Python: if importing from a package (e.g., pkg.mod),
                    # add implicit dependency on pkg/__init__.py
                    if language == Language.PYTHON and target.name != "__init__.py":
                        init_file = target.parent / "__init__.py"
                        if (
                            init_file in import_graph
                            and init_file not in import_graph[path]
                        ):
                            import_graph[path].append(init_file)

    # Add stdlib dependency edges so stdlib modules link before user code
    for user_path, deps in stdlib_edges.items():
        for dep in deps:
            if dep not in import_graph[user_path]:
                import_graph[user_path].append(dep)

    # --- Java: add implicit edges for qualified-name references ---
    # A file may reference another project class via a fully-qualified name
    # (e.g. com.lib.Helper.method()) without an explicit import statement.
    # In that case the import graph has no edge, so we scan source text.
    if language == Language.JAVA:
        qualified_to_path: dict[str, Path] = {
            f"{scan.package}.{cls}": file_path
            for file_path, scan in scan_results.items()
            if scan.package
            for cls in scan.class_names
        }
        source_bytes_map = {f: f.read_bytes() for f in source_files}
        new_edges = {
            (file_path, dep_path)
            for file_path in source_files
            for dotted, dep_path in qualified_to_path.items()
            if dep_path != file_path
            and dotted.encode() in source_bytes_map[file_path]
            and dep_path in import_graph
            and dep_path not in import_graph[file_path]
        }
        import_graph = {
            path: deps + [dep for fp, dep in new_edges if fp == path]
            for path, deps in import_graph.items()
        }

    # --- PASS 2: Patch IMPORT_MODULE instructions with resolved paths ---
    resolved_imports_map = _build_resolved_imports_map(
        modules, import_graph, resolver, directory
    )
    for path, module in modules.items():
        resolved_map = resolved_imports_map.get(path, {})
        patched_ir = _patch_import_module_instructions(module, resolved_map)
        # Create a new ModuleUnit with the patched IR
        modules[path] = dataclasses.replace(module, ir=patched_ir)

    topo_order = topological_sort(import_graph)

    return link_modules(
        modules=modules,
        import_graph=import_graph,
        project_root=directory,
        topo_order=topo_order,
        language=language,
    )
