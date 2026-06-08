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
from typing import Any

from interpreter.cics.dispatcher import _run_dispatcher_with_runner, parse_csd, run_cics
from interpreter.cics.strategy import CicsLoweringStrategy
from interpreter.cics.types import CicsContext, DispatchResult


def compile_cics_program(source: bytes, parser: Any, strategy: Any) -> Any:
    """Pre-passed CICS COBOL ``source`` -> ``LinkedProgram`` with ``strategy`` injected.

    ``source`` must already have been run through ``apply_cics_prepass`` (and
    encoded to bytes). Returns a :class:`LinkedProgram` ready for ``run_cics``.
    """
    from interpreter.cobol.cobol_frontend import CobolFrontend
    from interpreter.cfg import build_cfg
    from interpreter.registry import build_registry
    from interpreter.constants import Language
    from interpreter.project.types import LinkedProgram

    frontend = CobolFrontend(cobol_parser=parser, exec_cics_strategy=strategy)
    instructions = frontend.lower(source)
    cfg = build_cfg(instructions)
    registry = build_registry(
        instructions,
        cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    return LinkedProgram(
        modules={},
        merged_ir=list(instructions),
        merged_cfg=cfg,
        merged_registry=registry,
        language=Language.COBOL,
        import_graph={},
        type_env_builder=frontend.type_env_builder,
        symbol_table=frontend.symbol_table,
        data_layout=frontend.data_layout,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )


def run_carddemo_region(
    *,
    program_sources: dict[str, bytes],
    parser: Any,
    entry_transid: str,
    screen_queue: Any,
    input_queue: Any,
    transid_to_program: dict[str, str] | None = None,
    csd_path: Path | None = None,
    vsam_engine: Any = None,
    applid: str = "CARDDEMO",
    sysid: str = "SYS1",
    max_steps: int = 50_000,
) -> DispatchResult:
    """Assemble and run a CICS region; return the terminal :class:`DispatchResult`.

    Exactly one of ``transid_to_program`` or ``csd_path`` must be supplied:
    ``csd_path`` is parsed via :func:`parse_csd` into the transid→program mapping.

    ``program_sources`` maps each program name to its **pre-passed** COBOL source
    bytes. Every distinct program named in the mapping is compiled eagerly with a
    single shared :class:`CicsLoweringStrategy`; a missing source raises a clear
    error before the dispatcher loop starts (fail-fast).
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
        program_cache[prog_name] = compile_cics_program(source, parser, strategy)

    def run_fn(program: Any, context: CicsContext, sq: Any, iq: Any) -> DispatchResult:
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
