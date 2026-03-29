"""Per-module compiler and full project compilation orchestrator.

compile_module(): file → ModuleUnit
compile_project(): entry_file → LinkedProgram (discover → compile → link)
build_export_table(): IR + symbol tables → ExportTable
"""

from __future__ import annotations

from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.func_name import FuncName
from interpreter.frontend import get_frontend
from interpreter.ir import CodeLabel
from interpreter.instructions import InstructionBase, DeclVar, StoreVar, Label_
from interpreter.project.types import ExportTable, ImportRef, ModuleUnit, LinkedProgram
from interpreter.project.imports import extract_imports
from interpreter.project.resolver import (
    get_resolver,
    infer_project_root,
    topological_sort,
    ResolvedImport,
)
from interpreter.project.linker import link_modules
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter import constants


def build_export_table(
    ir: list[InstructionBase] | tuple[...],
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
    variables: dict[str, str] = {}
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
            var_name = str(typed.name)
            # Don't duplicate names already in functions or classes
            if (
                FuncName(var_name) not in functions
                and ClassName(var_name) not in classes
            ):
                variables[var_name] = str(typed.value_reg)

    return ExportTable(functions=functions, classes=classes, variables=variables)


def compile_module(
    file_path: Path,
    language: Language,
    source: bytes | None = None,
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
    frontend = get_frontend(language, frontend_type=resolved_frontend_type)
    ir = frontend.lower(source)

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
    )


def compile_project(
    entry_file: Path,
    language: Language,
    project_root: Path | None = None,
) -> LinkedProgram:
    """Compile a multi-file project: discover → compile → link.

    Args:
        entry_file: Path to the entry point file (e.g. main.py).
        language: Source language for all files in the project.
        project_root: Root directory. Inferred from entry_file if not given.

    Returns:
        A LinkedProgram ready for execution or analysis.
    """
    entry_file = entry_file.resolve()

    if project_root is None:
        project_root = infer_project_root(entry_file)
    else:
        project_root = project_root.resolve()

    resolver = get_resolver(language)

    # Phase 1: BFS import discovery
    discovered: dict[Path, list[ImportRef]] = {}
    import_graph: dict[Path, list[Path]] = {}
    queue: list[Path] = [entry_file]

    while queue:
        file_path = queue.pop(0)
        if file_path in discovered:
            continue

        source = file_path.read_bytes()
        refs = extract_imports(source, file_path, language)
        discovered[file_path] = refs
        import_graph[file_path] = []

        for ref in refs:
            resolved = resolver.resolve(ref, project_root)
            if resolved.resolved_path is not None:
                target = resolved.resolved_path.resolve()
                if target not in import_graph.get(file_path, []):
                    import_graph[file_path].append(target)
                if target not in discovered:
                    queue.append(target)

    # Phase 2: Topological sort
    topo_order = topological_sort(import_graph)

    # Phase 3: Compile each module
    modules: dict[Path, ModuleUnit] = {}
    for file_path in topo_order:
        if file_path not in modules:
            modules[file_path] = compile_module(file_path, language)

    # Phase 4: Link
    linked = link_modules(
        modules=modules,
        import_graph=import_graph,
        entry_module=entry_file,
        project_root=project_root,
        topo_order=topo_order,
    )

    return linked


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


def compile_directory(
    directory: Path,
    language: Language,
    entry_file: Path,
) -> LinkedProgram:
    """Compile all source files in a directory tree.

    Unlike compile_project (which discovers files via import BFS), this
    compiles every file matching the language's extensions. Catches
    orphaned modules, test files, and files not reachable via imports.

    Args:
        directory: Root directory to scan recursively.
        language: Source language — determines which file extensions to include.
        entry_file: Entry point file — its code runs first.

    Returns:
        A LinkedProgram with all files compiled and linked.
    """
    directory = directory.resolve()
    entry_file = entry_file.resolve()

    extensions = _LANGUAGE_EXTENSIONS.get(language, ())
    source_files = sorted(
        f.resolve()
        for ext in extensions
        for f in directory.rglob(f"*{ext}")
        if f.is_file()
    )

    modules = {path: compile_module(path, language) for path in source_files}

    # Build a flat import graph — no import-based edges, just all files listed
    import_graph = {path: [] for path in source_files}

    # Topo order: entry file last, everything else in sorted order
    topo_order = [p for p in source_files if p != entry_file] + [entry_file]

    return link_modules(
        modules=modules,
        import_graph=import_graph,
        entry_module=entry_file,
        project_root=directory,
        topo_order=topo_order,
    )
