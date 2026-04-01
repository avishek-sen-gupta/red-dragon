# pyright: standard
"""Per-module compiler and directory compilation orchestrator.

compile_module(): file → ModuleUnit
compile_directory(): directory → LinkedProgram (scan → compile → link)
build_export_table(): IR + symbol tables → ExportTable
"""

from __future__ import annotations

from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.func_name import FuncName
from interpreter.register import Register
from interpreter.var_name import VarName
from interpreter.frontend import get_frontend
from interpreter.ir import CodeLabel
from interpreter.instructions import InstructionBase, DeclVar, StoreVar, Label_
from interpreter.project.types import ExportTable, ModuleUnit, LinkedProgram
from interpreter.project.imports import extract_imports
from interpreter.project.resolver import (
    get_resolver,
    topological_sort,
    JavaImportResolver,
)
from interpreter.project.source_roots import MavenSourceRootDiscovery
from interpreter.project.linker import link_modules
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter import constants


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

    extensions = _LANGUAGE_EXTENSIONS.get(language, ())
    source_files = sorted(
        f.resolve()
        for ext in extensions
        for f in directory.rglob(f"*{ext}")
        if f.is_file()
    )

    modules = {path: compile_module(path, language) for path in source_files}

    # Build import graph from modules' resolved imports
    if language == Language.JAVA:
        discovered_roots = MavenSourceRootDiscovery().discover(directory)
        resolver = (
            JavaImportResolver(source_roots=discovered_roots)
            if discovered_roots
            else get_resolver(language)
        )
    else:
        resolver = get_resolver(language)

    import_graph: dict[Path, list[Path]] = {path: [] for path in source_files}
    for path, module in modules.items():
        for ref in module.imports:
            for resolved in resolver.resolve(ref, directory):
                if resolved.is_resolved():
                    target = resolved.resolved_path.resolve()
                    if target in import_graph and target not in import_graph[path]:
                        import_graph[path].append(target)

    topo_order = topological_sort(import_graph)

    return link_modules(
        modules=modules,
        import_graph=import_graph,
        project_root=directory,
        topo_order=topo_order,
        language=language,
    )
