# pyright: standard
"""Shared single-module COBOL compile core.

compile_cobol_module(): bytes → (CobolFrontend, ModuleUnit)
compile_cobol(): bytes → (CobolFrontend, LinkedProgram)

This is the canonical entry point for compiling COBOL source.
It knows about COBOL-specific injection points (parser, extension_strategies,
cics_text_parser) abstractly — no CICS/SQL specifics live here.
All frontend construction is routed through get_frontend (the factory).
"""

from __future__ import annotations

import hashlib
import json
import logging
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
    parser: Any = None,
    copybook_dirs: list[Path] | None = None,
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    path: Path = Path("__main__.cbl"),
    ast_path: Path | None = None,
) -> tuple[Any, ModuleUnit]:
    """Lower one COBOL source into a (frontend, ModuleUnit). The shared core."""
    frontend: Any = get_frontend(
        Language.COBOL,
        frontend_type=constants.FRONTEND_COBOL,
        observer=observer,
        copybook_dirs=copybook_dirs,
        cobol_parser=parser,
        extension_strategies=extension_strategies,
        cics_text_parser=cics_text_parser,
    )
    if ast_path is not None:
        # Phase 2: load AST from disk, lower, free dict immediately.
        ir = frontend.lower_from_ast_dict(json.loads(ast_path.read_text("utf-8")))
    else:
        ir = frontend.lower(source)
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


def compile_cobol(
    source: bytes,
    *,
    parser: Any = None,
    copybook_dirs: list[Path] | None = None,
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    program_source_dir: Path | None = None,
    extra_subprogram_sources: dict[str, bytes] | None = None,
    source_transform: Callable[[str], str] = lambda s: s,
    ast_cache_dir: Path | None = None,
) -> tuple[Any, LinkedProgram]:
    """Compile a COBOL program (single or multi-module) into a LinkedProgram.

    With no subprograms (program_source_dir=None and extra_subprogram_sources=None),
    produces a single-module LinkedProgram identical in shape to run()'s output.

    With subprograms, resolves CALL targets transitively, compiles each callee via
    compile_cobol_module (same parser/strategies), and links them via link_modules.

    source_transform is applied ONLY to callee sources the API resolves from disk
    (program_source_dir). Caller-supplied `source` and `extra_subprogram_sources`
    must already be in final (e.g. pre-passed) form — they are compiled as-is.

    When ast_cache_dir is set and parser is not None: Phase 1 parses all sources
    to ast_cache_dir in parallel; Phase 2 calls compile_cobol_module for each
    module with its ast_path. Result is identical to the non-cache path.

    Returns (main_frontend, linked) where main_frontend is the CobolFrontend for
    the main program (carries data_layout, symbol_table, etc.).
    """
    if ast_cache_dir is not None and parser is not None:
        # Note: program_source_dir disk resolution is intentionally excluded from the
        # ast-cache path — only extra_subprogram_sources are cached. This is a known
        # scope limitation: callers using program_source_dir + ast_cache_dir together
        # will get a LinkedProgram without disk-resolved callees.
        main_path = Path("__main__.cbl")
        base = program_source_dir or Path(".")

        # Collect all sources that need parsing.
        sub_sources: dict[str, bytes] = dict(extra_subprogram_sources or {})
        all_sources: dict[Path, bytes] = {main_path: source}
        for prog_name, prog_src in sub_sources.items():
            all_sources[(base / f"{prog_name}.cbl").resolve()] = prog_src

        # Phase 1: parallel parse — each worker writes JSON to disk and frees it.
        parallel_parse_to_cache(all_sources, parser, ast_cache_dir)

        cache_dir = ast_cache_dir  # pin non-None value for closure

        def _ast_path(src_path: Path) -> Path:
            path_hash = hashlib.md5(str(src_path).encode()).hexdigest()[:8]
            return cache_dir / f"{src_path.stem}-{path_hash}.ast.json"

        # Phase 2: sequential lower — one AST in memory at a time.
        main_frontend, main_module = compile_cobol_module(
            source,
            parser=parser,
            copybook_dirs=copybook_dirs,
            extension_strategies=extension_strategies,
            cics_text_parser=cics_text_parser,
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
                    cics_text_parser=cics_text_parser,
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

    main_path = Path("__main__.cbl")
    main_frontend, main_module = compile_cobol_module(
        source,
        parser=parser,
        copybook_dirs=copybook_dirs,
        extension_strategies=extension_strategies,
        cics_text_parser=cics_text_parser,
        observer=observer,
        path=main_path,
    )

    # Gather subprogram sources: resolved-on-disk CALL targets + explicit extras.
    subprogram_sources: dict[Path, bytes] = {}
    if program_source_dir is not None:
        subprogram_sources.update(
            _resolve_call_sources(
                source, main_path, program_source_dir.resolve(), source_transform
            )
        )
    if extra_subprogram_sources:
        for prog_name, prog_src in extra_subprogram_sources.items():
            base = program_source_dir or Path(".")
            # extra_subprogram_sources arrive in final form — no transform applied.
            subprogram_sources.setdefault(
                (base / f"{prog_name}.cbl").resolve(), prog_src
            )

    if not subprogram_sources:
        # No CALLs to link — single-module LinkedProgram (mirrors run.py:1319-1332).
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

    # Compile every subprogram module with the shared parser/strategies.
    # A callee that fails to lower is skipped with a warning — its CALL then
    # falls back to symbolic resolution, keeping the main program runnable.
    modules: dict[Path, ModuleUnit] = {main_path: main_module}
    for path, src in subprogram_sources.items():
        try:
            _, sub_module = compile_cobol_module(
                src,
                parser=parser,
                copybook_dirs=copybook_dirs,
                extension_strategies=extension_strategies,
                cics_text_parser=cics_text_parser,
                observer=observer,
                path=path,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "compile_cobol link: subprogram %s failed to compile — skipping "
                "(its CALL will resolve symbolically)",
                path.stem,
                exc_info=True,
            )
            continue
        modules[path] = sub_module

    if len(modules) == 1:
        # Every callee failed — fall back to single-module compile.
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

    # Build the import graph: main depends on all callees so linker processes
    # callees first (their init blocks set up the __prog_<NAME> singletons).
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

    # Record the namespaced entry function label for unambiguous dispatch.
    # The linker prefixes labels relative to project_root="/", so __main__.cbl
    # → prefix "__main__" → entry label "__main__.func_<progid>_0".
    main_program_id: str = main_frontend.program_id
    linked.entry_func_label = CodeLabel(f"__main__.func_{main_program_id.lower()}_0")

    return main_frontend, linked
