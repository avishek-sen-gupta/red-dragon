# pyright: standard
"""Shared single-module COBOL compile core.

compile_cobol_module(): bytes → (CobolFrontend, ModuleUnit)
compile_cobol(): bytes → (CobolFrontend, LinkedProgram)

This is the canonical entry point for compiling COBOL source.
It knows about COBOL-specific injection points (parser, extension_strategies,
dialect_parsers) abstractly — no CICS/SQL specifics live here.
All frontend construction is routed through get_frontend (the factory).
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Sequence

from interpreter.cfg import build_cfg
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.ir import CodeLabel
from interpreter.project.compiler import build_export_table
from interpreter.project.imports import extract_imports
from interpreter.project.linker import link_modules
from interpreter.project.resolver import get_resolver, topological_sort
from interpreter.project.types import ImportKind, LinkedProgram, ModuleUnit
from interpreter.registry import build_registry
from interpreter import constants

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
    cache_dir.mkdir(parents=True, exist_ok=True)

    def _parse_one(item: tuple[Path, bytes]) -> tuple[Path, Path]:
        src_path, source = item
        path_hash = hashlib.md5(str(src_path).encode()).hexdigest()[:8]
        out_path = cache_dir / f"{src_path.stem}-{path_hash}.ast.json"
        parser.parse_to_file(source, out_path)
        return src_path, out_path

    result: dict[Path, Path] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_parse_one, item): item[0] for item in sources.items()
        }
        for future in as_completed(futures):
            src_path, ast_path = future.result()
            result[src_path] = ast_path
    return result


def compile_cobol_module(
    source: bytes,
    *,
    parser: Any,
    copybook_dirs: list[Path] = [],
    extension_strategies: Sequence[Any] = (),
    dialect_parsers: Sequence[Any] = (),
    observer: FrontendObserver = NullFrontendObserver(),
    path: Path = Path("__main__.cbl"),
    ast_path: Path,
) -> tuple[Any, ModuleUnit]:
    """Lower one COBOL source into a (frontend, ModuleUnit). The shared core."""
    frontend: Any = get_frontend(
        Language.COBOL,
        frontend_type=constants.FRONTEND_COBOL,
        observer=observer,
        copybook_dirs=copybook_dirs,
        cobol_parser=parser,
        extension_strategies=extension_strategies,
        dialect_parsers=dialect_parsers,
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
    extension_strategies: Sequence[Any] = (),
    dialect_parsers: Sequence[Any] = (),
    observer: FrontendObserver = NullFrontendObserver(),
    program_source_dir: Path = Path("."),
    extra_subprogram_sources: dict[str, bytes] = {},
    source_transform: Callable[[str], str] = lambda s: s,
    ast_cache_dir: Path | None = None,
) -> tuple[Any, LinkedProgram]:
    """Compile a COBOL program (single or multi-module) into a LinkedProgram.

    Always uses the two-phase AST cache: Phase 1 parses all sources to
    ast_cache_dir in parallel; Phase 2 loads each JSON and lowers sequentially
    (at most one ASG live at a time). When ast_cache_dir is None a TemporaryDirectory
    is created and cleaned up before returning.

    Returns (main_frontend, linked).
    """
    _owned_tmp: tempfile.TemporaryDirectory[str] | None = None
    if ast_cache_dir is None:
        _owned_tmp = tempfile.TemporaryDirectory()
        cache_dir: Path = Path(_owned_tmp.name)
    else:
        cache_dir = ast_cache_dir

    try:
        # Note: program_source_dir disk resolution is intentionally excluded from the
        # ast-cache path — only extra_subprogram_sources are cached. This is a known
        # scope limitation: callers using program_source_dir + ast_cache_dir together
        # will get a LinkedProgram without disk-resolved callees.
        main_path = Path("__main__.cbl")
        base = program_source_dir

        sub_sources: dict[str, bytes] = dict(extra_subprogram_sources)

        # Resolve on-disk callees via program_source_dir and source_transform.
        # program_source_dir's default (Path(".")) is the "no real directory given"
        # sentinel: disk resolution only runs when a caller opts in with a
        # different directory — comparing against the default (rather than the
        # old `is not None` check) preserves that opt-in behavior now that the
        # parameter itself is no longer Optional.
        disk_sources: dict[Path, bytes] = {}
        if program_source_dir != Path("."):
            disk_sources = _resolve_call_sources(
                source, main_path, program_source_dir.resolve(), source_transform
            )

        all_sources: dict[Path, bytes] = {main_path: source}
        for prog_name, prog_src in sub_sources.items():
            all_sources[(base / f"{prog_name}.cbl").resolve()] = prog_src
        all_sources.update(disk_sources)

        parallel_parse_to_cache(all_sources, parser, cache_dir)

        def _ast_path(src_path: Path) -> Path:
            path_hash = hashlib.md5(str(src_path).encode()).hexdigest()[:8]
            return cache_dir / f"{src_path.stem}-{path_hash}.ast.json"

        main_frontend, main_module = compile_cobol_module(
            source,
            parser=parser,
            copybook_dirs=copybook_dirs,
            extension_strategies=extension_strategies,
            dialect_parsers=dialect_parsers,
            observer=observer,
            path=main_path,
            ast_path=_ast_path(main_path),
        )
        modules: dict[Path, ModuleUnit] = {main_path: main_module}

        for prog_name, prog_src in sub_sources.items():
            sub_path = (base / f"{prog_name}.cbl").resolve()
            try:
                _, sub_module = compile_cobol_module(
                    prog_src,
                    parser=parser,
                    copybook_dirs=copybook_dirs,
                    extension_strategies=extension_strategies,
                    dialect_parsers=dialect_parsers,
                    observer=observer,
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
                    parser=parser,
                    copybook_dirs=copybook_dirs,
                    extension_strategies=extension_strategies,
                    dialect_parsers=dialect_parsers,
                    observer=observer,
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

        if len(modules) == 1:
            instructions = list(main_module.ir)
            cfg = build_cfg(instructions)
            registry = build_registry(
                instructions,
                cfg,
                func_symbol_table=main_frontend.func_symbol_table,
                class_symbol_table=main_frontend.class_symbol_table,
            )
            return main_frontend, LinkedProgram(
                modules={},
                merged_ir=instructions,
                merged_cfg=cfg,
                merged_registry=registry,
                language=Language.COBOL,
                import_graph={},
                type_env_builder=main_frontend.type_env_builder,
                symbol_table=main_frontend.symbol_table,
                data_layout=main_frontend.data_layout,
                func_symbol_table=main_frontend.func_symbol_table,
                class_symbol_table=main_frontend.class_symbol_table,
            )

        import_graph: dict[Path, list[Path]] = {p: [] for p in modules}
        import_graph[main_path] = [p for p in modules if p != main_path]
        topo_order = topological_sort(import_graph)
        linked = link_modules(
            modules=modules,
            import_graph=import_graph,
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


def _resolve_call_sources(
    main_source: bytes,
    main_path: Path,
    program_source_dir: Path,
    source_transform: Callable[[str], str],
) -> dict[Path, bytes]:
    """Transitively resolve CALL targets reachable from the main program on disk.

    Walks CALL edges via extract_imports + CobolImportResolver, reads each
    resolved program source from program_source_dir, applies source_transform,
    and returns {absolute_path: transformed_bytes} for every callee found.
    Unresolvable CALL targets (no matching .cbl on disk) are skipped.
    """
    resolver = get_resolver(Language.COBOL)
    resolved: dict[Path, bytes] = {}

    pending: list[tuple[bytes, Path]] = [(main_source, main_path)]
    seen_paths: set[Path] = {main_path.resolve()}

    while pending:
        src, path = pending.pop()
        for ref in extract_imports(src, path, Language.COBOL):
            if ref.kind != ImportKind.REQUIRE:
                continue  # COPY (INCLUDE) is handled by the parser's copybook dirs
            for hit in resolver.resolve(ref, program_source_dir):
                if not hit.is_resolved():
                    continue
                target = hit.resolved_path.resolve()
                if target in seen_paths:
                    continue
                seen_paths.add(target)
                callee_src = source_transform(target.read_text()).encode()
                resolved[target] = callee_src
                pending.append((callee_src, target))

    return resolved
