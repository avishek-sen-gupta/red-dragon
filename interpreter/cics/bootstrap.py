"""Top-level CICS region bootstrap.

Assembles a running CICS region from a CSD transid→program mapping and a set of
COBOL program sources:

  1. (optionally) parse a CSD file into ``transid_to_program``,
  2. construct ONE shared :class:`CicsLoweringStrategy` over the region's runtime
     state (VSAM engine, BMS loader, screen/input queues, context/result holders),
  3. eagerly compile every distinct program named in the CSD into a
     ``program_cache`` keyed by program name (fail-fast on a missing source),
  4. run the dispatcher loop at the entry transid.

Source contract: ``program_sources`` values are **pre-passed** COBOL bytes — the
caller is responsible for running :func:`apply_cics_prepass` (and ``.encode()``)
before handing sources here. ``compile_cics_program`` likewise assumes its
``source`` argument is already pre-passed. This keeps a single, explicit prepass
step at the boundary and avoids double-prepassing.

Heavy frontend/CFG/project imports are kept lazy inside the functions so this
module stays cheap to import and side-steps any import-linter coupling concerns.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from interpreter.cics.dispatcher import _run_dispatcher_with_runner, parse_csd, run_cics
from interpreter.cics.strategy import CicsLoweringStrategy
from interpreter.cics.types import CicsContext, DispatchResult

if TYPE_CHECKING:
    from interpreter.cics.terminal import InputChannel, ScreenChannel


def _compile_cics_module(source: bytes, parser: Any, strategy: Any, path: Path) -> Any:
    """Lower one pre-passed CICS COBOL ``source`` into a :class:`ModuleUnit`.

    Mirrors :func:`interpreter.project.compiler.compile_module` but constructs a
    :class:`CobolFrontend` with the shared ``CicsLoweringStrategy`` injected, so
    that EXEC CICS in *any* linked module (main or CALLed subprogram) still
    lowers through the same strategy. Returns ``(module_unit, frontend)``; the
    frontend is returned so the caller can pull the main program's program_id /
    data_layout / type_env_builder.
    """
    from interpreter.cobol.cobol_frontend import CobolFrontend
    from interpreter.constants import Language
    from interpreter.project.compiler import build_export_table
    from interpreter.project.imports import extract_imports
    from interpreter.project.types import ModuleUnit

    frontend = CobolFrontend(cobol_parser=parser, exec_cics_strategy=strategy)
    instructions = frontend.lower(source)
    exports = build_export_table(
        instructions,
        frontend.func_symbol_table,
        frontend.class_symbol_table,
    )
    imports = tuple(extract_imports(source, path, Language.COBOL))
    module = ModuleUnit(
        path=path,
        language=Language.COBOL,
        ir=tuple(instructions),
        exports=exports,
        imports=imports,
        symbol_table=frontend.symbol_table,
    )
    return module, frontend


def _resolve_call_sources(
    main_source: bytes,
    main_path: Path,
    program_source_dir: Path,
) -> dict[Path, bytes]:
    """Transitively resolve the CALL targets reachable from the main program.

    Uses the existing COBOL import extractor + resolver to walk ``CALL 'X'``
    edges, reading each resolved program source from ``program_source_dir``.
    Returns a ``{path: pre-passed source bytes}`` map for every CALLed program
    (excluding the main program itself). Unresolvable CALL targets (e.g. the LE
    service CEEDAYS, which has no COBOL source) are skipped — they are provided
    separately as stubs.
    """
    from interpreter.constants import Language
    from interpreter.project.imports import extract_imports
    from interpreter.project.resolver import get_resolver
    from interpreter.project.types import ImportKind
    from interpreter.cics.preprocessor import apply_cics_prepass

    resolver = get_resolver(Language.COBOL)
    resolved: dict[Path, bytes] = {}

    # Work queue of (source bytes, path) to scan for CALL edges.
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
                callee_src = apply_cics_prepass(target.read_text()).encode()
                resolved[target] = callee_src
                pending.append((callee_src, target))

    return resolved


def compile_cics_program(
    source: bytes,
    parser: Any,
    strategy: Any,
    *,
    program_source_dir: Path | None = None,
    extra_subprogram_sources: dict[str, bytes] | None = None,
) -> Any:
    """Pre-passed CICS COBOL ``source`` -> ``LinkedProgram`` with ``strategy`` injected.

    ``source`` must already have been run through ``apply_cics_prepass`` (and
    encoded to bytes). Returns a :class:`LinkedProgram` ready for ``run_cics``.

    When ``program_source_dir`` is given, the main program's ``CALL 'X'`` targets
    are resolved (transitively) against that directory using the existing COBOL
    import resolver, each CALLed program is compiled with the SAME
    ``CicsLoweringStrategy``, and all modules are merged via the project linker
    (:func:`interpreter.project.linker.link_modules`) so the CALL resolves at
    runtime through ``CallWithMemory``'s singleton dispatch.

    ``extra_subprogram_sources`` maps a *program name* to pre-passed source bytes
    for callees that are not present on disk (e.g. a CEEDAYS stub standing in for
    an IBM Language Environment callable service). They are linked like any other
    subprogram. When there are no CALLs (and no extras), this reduces to the
    original single-module compile.
    """
    from interpreter.cfg import build_cfg
    from interpreter.registry import build_registry
    from interpreter.constants import Language
    from interpreter.ir import CodeLabel
    from interpreter.project.linker import link_modules
    from interpreter.project.resolver import topological_sort
    from interpreter.project.types import LinkedProgram

    # Compile the main program as a module (keep its frontend for data_layout etc.).
    main_path = Path("__main__.cbl")
    main_module, main_frontend = _compile_cics_module(
        source, parser, strategy, main_path
    )
    main_program_id = main_frontend.program_id

    # Gather subprogram sources: resolved-on-disk CALL targets + explicit extras.
    subprogram_sources: dict[Path, bytes] = {}
    if program_source_dir is not None:
        subprogram_sources.update(
            _resolve_call_sources(source, main_path, program_source_dir.resolve())
        )
    if extra_subprogram_sources:
        for prog_name, prog_src in extra_subprogram_sources.items():
            # Synthetic path; only used as the module's namespace key, never read.
            base = program_source_dir or Path(".")
            subprogram_sources.setdefault(
                (base / f"{prog_name}.cbl").resolve(), prog_src
            )

    if not subprogram_sources:
        # No CALLs to link — original single-module compile (unchanged behaviour).
        instructions = list(main_module.ir)
        cfg = build_cfg(instructions)
        registry = build_registry(
            instructions,
            cfg,
            func_symbol_table=main_frontend.func_symbol_table,
            class_symbol_table=main_frontend.class_symbol_table,
        )
        return LinkedProgram(
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

    # Compile every subprogram module with the shared strategy. A callee that
    # fails to lower (e.g. an as-yet-unsupported COBOL construct) is skipped with
    # a warning rather than failing the whole region compile: the corresponding
    # CALL then falls back to the symbolic path, exactly as if it were unlinked.
    # This keeps the main program and its other CALLs runnable.
    import logging

    logger = logging.getLogger(__name__)
    modules = {main_path: main_module}
    for path, src in subprogram_sources.items():
        try:
            module, _fe = _compile_cics_module(src, parser, strategy, path)
        except (
            Exception
        ):  # noqa: BLE001 — defensive: one bad callee must not abort the region
            logger.warning(
                "CICS region link: subprogram %s failed to compile — skipping "
                "(its CALL will resolve symbolically)",
                path.stem,
                exc_info=True,
            )
            continue
        modules[path] = module

    if len(modules) == 1:
        # Every callee failed to compile — fall back to the single-module compile
        # so the main program still runs (CALLs go symbolic).
        instructions = list(main_module.ir)
        cfg = build_cfg(instructions)
        registry = build_registry(
            instructions,
            cfg,
            func_symbol_table=main_frontend.func_symbol_table,
            class_symbol_table=main_frontend.class_symbol_table,
        )
        return LinkedProgram(
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

    # Build the import graph: make every callee a dependency of main so the
    # linker processes callees first (their program-init blocks set up the
    # __prog_<NAME> singletons) and the entry module last.
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

    # The linker namespaces labels with the module prefix derived from the file
    # path relative to project_root ("/"). For main_path "__main__.cbl" that
    # prefix is "__main__", so the entry function label is
    # "__main__.func_<progid>_0". Record it for unambiguous dispatch.
    linked.entry_func_label = CodeLabel(f"__main__.func_{main_program_id.lower()}_0")
    return linked


def run_carddemo_region(
    *,
    program_sources: dict[str, bytes],
    parser: Any,
    entry_transid: str,
    screen_queue: ScreenChannel,
    input_queue: InputChannel,
    transid_to_program: dict[str, str] | None = None,
    csd_path: Path | None = None,
    vsam_engine: Any = None,
    applid: str = "CARDDEMO",
    sysid: str = "SYS1",
    max_steps: int = 50_000,
    program_source_dir: Path | None = None,
    extra_subprogram_sources: dict[str, bytes] | None = None,
) -> DispatchResult:
    """Assemble and run a CICS region; return the terminal :class:`DispatchResult`.

    Exactly one of ``transid_to_program`` or ``csd_path`` must be supplied:
    ``csd_path`` is parsed via :func:`parse_csd` into the transid→program mapping.

    ``program_sources`` maps each program name to its **pre-passed** COBOL source
    bytes. Every distinct program named in the mapping is compiled eagerly with a
    single shared :class:`CicsLoweringStrategy`; a missing source raises a clear
    error before the dispatcher loop starts (fail-fast).

    ``program_source_dir`` (the CardDemo ``cbl/`` dir) and
    ``extra_subprogram_sources`` are threaded into :func:`compile_cics_program` so
    each region program links the subprograms it ``CALL``s.
    """
    if (transid_to_program is None) == (csd_path is None):
        raise ValueError(
            "run_carddemo_region requires exactly one of "
            "transid_to_program= or csd_path="
        )
    if csd_path is not None:
        transid_to_program = parse_csd(csd_path)
    assert transid_to_program is not None  # narrowed by the checks above

    context_holder: list[CicsContext] = [None]  # type: ignore[list-item]
    result_holder: list = [None]

    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=vsam_engine,
        screen_queue=screen_queue,
        input_queue=input_queue,
        applid=applid,
        sysid=sysid,
    )

    program_cache: dict[str, Any] = {}
    for prog_name in transid_to_program.values():
        if prog_name in program_cache:
            continue
        source = program_sources.get(prog_name)
        if source is None:
            raise ValueError(
                f"No source provided for CICS program {prog_name!r} "
                f"(named in the CSD/transid mapping)"
            )
        program_cache[prog_name] = compile_cics_program(
            source,
            parser,
            strategy,
            program_source_dir=program_source_dir,
            extra_subprogram_sources=extra_subprogram_sources,
        )

    def run_fn(
        program: Any,
        context: CicsContext,
        sq: ScreenChannel,
        iq: InputChannel,
    ) -> DispatchResult:
        return run_cics(
            program,
            context,
            sq,
            iq,
            context_holder=context_holder,
            result_holder=result_holder,
            max_steps=max_steps,
        )

    return _run_dispatcher_with_runner(
        run_fn,
        program_cache,
        transid_to_program,
        CicsContext(transid=entry_transid, commarea=b"", eibaid="\x7d"),
        screen_queue,
        input_queue,
    )
