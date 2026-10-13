# pyright: standard
"""Shared single-module COBOL compile core.

compile_cobol_module(): bytes → (CobolFrontend, ModuleUnit)
compile_cobol(): bytes → (CobolFrontend, LinkedProgram)

This is the canonical entry point for compiling COBOL source.
It knows about COBOL-specific injection points (parser, extension_strategies,
dialect_parsers) abstractly — no CICS/SQL specifics live here.
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from cobol_asg.addressing_mode import AddressingMode
from cobol_asg.ast_store import AstStore, _digest
from cobol_asg.frontend_extension import DialectParser
from cobol_asg.lp import LP
from cobol_asg.lp32 import LP32_MODE
from cobol_asg.resolve_addressing_mode import addressing_mode
from interpreter.constants import Language
from interpreter.frontend_extension_lowering import RedDragonExtensionLoweringStrategy
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.frontends import get_cobol_frontend
from interpreter.ir import CodeLabel
from interpreter.project.cobol_discovery import discover_callee_programs
from interpreter.project.compiler import build_export_table
from interpreter.project.imports import extract_imports
from interpreter.project.linker import link_modules
from interpreter.project.resolver import topological_sort
from interpreter.project.start_up import with_start_up
from interpreter.project.types import LinkedProgram, ModuleUnit

logger = logging.getLogger(__name__)


def parallel_parse_to_cache(
    sources: dict[Path, bytes],
    parser: Any,
    cache_dir: Path,
    *,
    max_workers: int = 4,
) -> dict[Path, Path]:
    """Parse all sources in parallel, writing raw bridge JSON to cache_dir.

    Each worker calls parser.parse_to_file(), which writes to disk and frees
    the JSON string immediately — ASTs never accumulate in memory across workers.
    Returns {source_path: ast_json_path}. cache_dir is created if absent.
    """
    store = AstStore(cache_dir, max_workers=max_workers)
    store.parse_all(sources, parser)
    return {src: cache_dir / f"{src.stem}-{_digest(src)}.ast.json" for src in sources}


def compile_cobol_module(
    source: bytes,
    *,
    parser: Any,
    copybook_dirs: list[Path] = [],
    extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
    dialect_parsers: Sequence[DialectParser] = (),
    observer: FrontendObserver = NullFrontendObserver(),
    path: Path = Path("__main__.cbl"),
    ast_path: Path,
    tolerant: bool = False,
    addressing_mode: AddressingMode = LP32_MODE,
) -> tuple[Any, ModuleUnit]:
    """Lower one COBOL source into a (frontend, ModuleUnit). The shared core."""
    frontend = get_cobol_frontend(
        observer=observer,
        copybook_dirs=copybook_dirs,
        extension_strategies=extension_strategies,
        dialect_parsers=dialect_parsers,
        tolerant=tolerant,
        addressing_mode=addressing_mode,
    )
    ir = frontend.lower_from_ast_dict(json.loads(ast_path.read_text("utf-8")))
    exports = build_export_table(
        ir, frontend.func_symbol_table, frontend.class_symbol_table
    )
    imports = tuple(extract_imports(source, path, Language.COBOL))
    module = ModuleUnit(
        path=path,
        language=Language.COBOL,
        ir=tuple(ir),
        exports=exports,
        imports=imports,
        symbol_table=frontend.symbol_table,
    )
    return frontend, module


def compile_cobol(
    source: bytes,
    *,
    parser: Any,
    copybook_dirs: list[Path] = [],
    extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
    dialect_parsers: Sequence[DialectParser] = (),
    observer: FrontendObserver = NullFrontendObserver(),
    source_search_dirs: Sequence[Path] = (),
    extra_subprogram_sources: dict[str, bytes] = {},
    source_transform: Callable[[str], str] = lambda s: s,
    ast_cache_dir: Path | None = None,
    tolerant: bool = False,
    lp: LP = LP.LP32,
) -> tuple[Any, LinkedProgram]:
    """Compile a COBOL program (single or multi-module) into a LinkedProgram.

    Always uses the two-phase AST cache: Phase 1 parses all sources to
    ast_cache_dir in parallel; Phase 2 loads each JSON and lowers sequentially
    (at most one ASG live at a time). When ast_cache_dir is None a TemporaryDirectory
    is created and cleaned up before returning.

    Returns (main_frontend, linked).
    """
    mode = addressing_mode(lp)
    mode_parser = parser.with_addressing_mode(mode)
    _owned_tmp: tempfile.TemporaryDirectory[str] | None = None
    if ast_cache_dir is None:
        _owned_tmp = tempfile.TemporaryDirectory()
        cache_dir: Path = Path(_owned_tmp.name)
    else:
        cache_dir = ast_cache_dir

    try:
        # Note: source_search_dirs disk resolution is intentionally excluded from
        # the ast-cache path — only extra_subprogram_sources are cached. This is a
        # known scope limitation: callers using source_search_dirs + ast_cache_dir
        # together will get a LinkedProgram without disk-resolved callees.
        main_path = Path("__main__.cbl")
        base = source_search_dirs[0] if source_search_dirs else Path(".")

        sub_sources: dict[str, bytes] = dict(extra_subprogram_sources)

        disk_sources: dict[Path, bytes] = {
            found.path: found.source
            for found in discover_callee_programs(
                source, source_search_dirs, source_transform
            )
        }

        all_sources: dict[Path, bytes] = {main_path: source}
        for prog_name, prog_src in sub_sources.items():
            all_sources[(base / f"{prog_name}.cbl").resolve()] = prog_src
        all_sources.update(disk_sources)

        parallel_parse_to_cache(all_sources, mode_parser, cache_dir)

        def _ast_path(src_path: Path) -> Path:
            return cache_dir / f"{src_path.stem}-{_digest(src_path)}.ast.json"

        main_frontend, main_module = compile_cobol_module(
            source,
            parser=mode_parser,
            copybook_dirs=copybook_dirs,
            extension_strategies=extension_strategies,
            dialect_parsers=dialect_parsers,
            observer=observer,
            path=main_path,
            tolerant=tolerant,
            addressing_mode=mode,
            ast_path=_ast_path(main_path),
        )
        modules: dict[Path, ModuleUnit] = {main_path: main_module}

        for prog_name, prog_src in sub_sources.items():
            sub_path = (base / f"{prog_name}.cbl").resolve()
            try:
                _, sub_module = compile_cobol_module(
                    prog_src,
                    parser=mode_parser,
                    copybook_dirs=copybook_dirs,
                    extension_strategies=extension_strategies,
                    dialect_parsers=dialect_parsers,
                    observer=observer,
                    tolerant=tolerant,
                    addressing_mode=mode,
                    path=sub_path,
                    ast_path=_ast_path(sub_path),
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "compile_cobol ast-cache: subprogram %s failed — skipping",
                    prog_name,
                    exc_info=True,
                )
                continue
            modules[sub_path] = sub_module

        for disk_path, disk_src in disk_sources.items():
            if disk_path in modules:
                continue
            try:
                _, disk_module = compile_cobol_module(
                    disk_src,
                    parser=mode_parser,
                    copybook_dirs=copybook_dirs,
                    extension_strategies=extension_strategies,
                    dialect_parsers=dialect_parsers,
                    observer=observer,
                    tolerant=tolerant,
                    addressing_mode=mode,
                    path=disk_path,
                    ast_path=_ast_path(disk_path),
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "compile_cobol ast-cache: disk callee %s failed — skipping",
                    disk_path.stem,
                    exc_info=True,
                )
                continue
            modules[disk_path] = disk_module

        import_graph: dict[Path, list[Path]] = {p: [] for p in modules}
        import_graph[main_path] = [p for p in modules if p != main_path]
        linked_modules, linked_graph = with_start_up(
            main_frontend.start_up_ir(), Language.COBOL, modules, import_graph
        )
        topo_order = topological_sort(linked_graph)
        linked = link_modules(
            modules=linked_modules,
            import_graph=linked_graph,
            project_root=Path("/"),
            topo_order=topo_order,
            language=Language.COBOL,
            type_env_builder=main_frontend.type_env_builder,
            data_layout=main_frontend.data_layout,
        )
        main_program_id: str = main_frontend.program_id
        linked.entry_func_label = CodeLabel(
            f"__main__.func_{main_program_id.lower()}_0"
        )
        return main_frontend, linked
    finally:
        if _owned_tmp is not None:
            _owned_tmp.cleanup()
