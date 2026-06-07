"""CICS transaction dispatcher — run_cics() and dispatcher loop."""

from __future__ import annotations

import logging
import queue
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from interpreter.cics.types import CicsContext, DispatchKind, DispatchResult
from interpreter.func_name import FuncName
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import UNKNOWN
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)

_DFHENTER = "\x7d"


@dataclass
class InputEvent:
    """Inbound terminal event — attention key + map field values."""

    eibaid: str = _DFHENTER
    fields: dict[str, str] = field(default_factory=dict)


def run_cics(
    program: Any,  # LinkedProgram — avoid circular import
    context: CicsContext,
    screen_queue: "queue.Queue[Any]",
    input_queue: "queue.Queue[InputEvent]",
    *,
    context_holder: list[CicsContext],
    result_holder: list,
    max_steps: int = 50_000,
) -> DispatchResult:
    """Execute one CICS program with the given context. Returns DispatchResult."""
    from interpreter.run import run_linked, EntryPoint
    from interpreter.vm.vm_types import VMState, StackFrame
    from interpreter.address import Address

    context_holder[0] = context
    result_holder[0] = None

    initial_vm = VMState()
    # The COMMAREA is bound to the LINKAGE SECTION (DFHCOMMAREA) via
    # __params_region. Field reads in the program resolve through this register
    # as a region handle, so the bytes must live in an addressable VM region
    # (not a raw-bytes local). Allocate one and point __params_region at it.
    commarea_addr = Address("rgn_commarea")
    initial_vm.region_set(commarea_addr, bytearray(context.commarea))
    initial_vm.call_stack.append(
        StackFrame(
            function_name=FuncName("main"),
            local_vars={
                VarName("__cics_transid"): typed(context.transid, UNKNOWN),
                VarName("__cics_eibcalen"): typed(len(context.commarea), UNKNOWN),
                VarName("__cics_eibaid"): typed(context.eibaid, UNKNOWN),
                VarName("__params_region"): typed(commarea_addr, UNKNOWN),
            },
        )
    )

    run_linked(
        program,
        EntryPoint.function(
            lambda ref: str(ref.label).startswith("func_")
            and not str(ref.label).startswith("func_init_params_")
        ),
        max_steps=max_steps,
        initial_vm=initial_vm,
    )

    if result_holder[0] is not None:
        return result_holder[0]
    return DispatchResult(kind=DispatchKind.RETURN)


RunCicsFn = Callable[
    [Any, CicsContext, "queue.Queue[Any]", "queue.Queue[InputEvent]"],
    DispatchResult,
]


def _run_dispatcher_with_runner(
    run_fn: RunCicsFn,
    program_cache: dict[str, Any],
    transid_to_program: dict[str, str],
    initial_context: CicsContext,
    screen_queue: "queue.Queue[Any]",
    input_queue: "queue.Queue[InputEvent]",
) -> DispatchResult:
    """Core dispatcher loop — separated for testability."""
    context = initial_context
    program = program_cache[transid_to_program[context.transid]]

    while True:
        result = run_fn(program, context, screen_queue, input_queue)

        if result.kind == DispatchKind.RETURN_TRANSID:
            event = input_queue.get()  # blocks
            next_prog_name = transid_to_program.get(result.transid or "")
            if not next_prog_name:
                logger.error("Unknown transid %r from RETURN TRANSID", result.transid)
                return DispatchResult(kind=DispatchKind.ABEND, abcode="TRNI")
            program = program_cache[next_prog_name]
            context = CicsContext(
                transid=result.transid or "",
                commarea=result.commarea or b"",
                eibaid=event.eibaid,
            )

        elif result.kind == DispatchKind.XCTL:
            prog_name = (result.program or "").strip()
            if prog_name not in program_cache:
                logger.error("XCTL to unknown program %r", prog_name)
                return DispatchResult(kind=DispatchKind.ABEND, abcode="PGMI")
            program = program_cache[prog_name]
            context = CicsContext(
                transid=context.transid,
                commarea=result.commarea or b"",
                eibaid=context.eibaid,
            )

        else:
            return result


_CSD_PATTERN = re.compile(
    r"DEFINE\s+TRANSACTION\((\w+)\)\s+PROGRAM\((\w+)\)", re.IGNORECASE
)


def parse_csd(csd_path: Path) -> dict[str, str]:
    """Parse a CSD file to produce {transid: program_name} mapping."""
    content = csd_path.read_text(encoding="utf-8", errors="replace")
    result = {}
    for m in _CSD_PATTERN.finditer(content):
        result[m.group(1).upper()] = m.group(2).upper()
    logger.info("CSD parsed: %d transid→program mappings", len(result))
    return result
