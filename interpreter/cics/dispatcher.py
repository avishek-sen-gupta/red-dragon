"""CICS transaction dispatcher — run_cics() and dispatcher loop."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from lark import Lark, Transformer

from interpreter.cics.terminal import InputChannel, ScreenChannel
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
    screen_queue: ScreenChannel,
    input_queue: InputChannel,
    *,
    context_holder: list[CicsContext],
    result_holder: list,
    max_steps: int = 50_000,
) -> DispatchResult:
    """Execute one CICS program with the given context. Returns DispatchResult."""
    from interpreter.run import run_linked, EntryPoint
    from interpreter.vm.vm_types import VMState, StackFrame
    from interpreter.address import Address

    _prog_label = getattr(program, "entry_func_label", None)
    logger.info(
        "run_cics: program=%s transid=%s commarea=%d B",
        _prog_label or "?",
        context.transid,
        len(context.commarea),
    )

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

    # When the program links subprograms (CALL targets), several namespaced
    # func_* labels exist; the bootstrap records the main program's entry label
    # so dispatch is unambiguous. A standalone program leaves it None and falls
    # back to the bare func_* predicate (exactly one match).
    entry_label = getattr(program, "entry_func_label", None)
    if entry_label is not None:
        entry_label_str = str(entry_label)
        entry_point = EntryPoint.function(
            lambda ref, _lbl=entry_label_str: str(ref.label) == _lbl
        )
    else:
        entry_point = EntryPoint.function(
            lambda ref: str(ref.label).startswith("func_")
            and not str(ref.label).startswith("func_init_params_")
        )

    run_linked(
        program,
        entry_point,
        max_steps=max_steps,
        initial_vm=initial_vm,
    )

    result = (
        result_holder[0]
        if result_holder[0] is not None
        else DispatchResult(kind=DispatchKind.RETURN)
    )
    logger.info("run_cics done: %s", result.kind.name)
    return result


RunCicsFn = Callable[
    [Any, CicsContext, ScreenChannel, InputChannel],
    DispatchResult,
]


def _advance_routing(
    result: DispatchResult,
    current_transid: str,
    program_cache: dict[str, Any],
    transid_to_program: dict[str, str],
) -> "tuple[str, Any, bytes] | DispatchResult":
    """The single copy of the "which program/transid runs next" rule.

    Given a program's DispatchResult and the current transid, decide how routing
    proceeds. Returns either a ``(next_transid, next_program, next_commarea)``
    tuple (continue) or a terminal ``DispatchResult`` (RETURN / ABEND — stop).

      * RETURN_TRANSID: resolve the next program via ``transid_to_program``; the
        transid becomes the (stripped) returned transid. Unknown transid -> ABEND
        TRNI.
      * XCTL: switch to the named program; the transid CARRIES (same task).
        Unknown program -> ABEND PGMI.
      * anything else (RETURN / ABEND): terminal — returned unchanged.
    """
    if result.kind == DispatchKind.RETURN_TRANSID:
        next_transid = (result.transid or "").strip()
        next_prog_name = transid_to_program.get(next_transid)
        if not next_prog_name:
            logger.error("Unknown transid %r from RETURN TRANSID", result.transid)
            return DispatchResult(kind=DispatchKind.ABEND, abcode="TRNI")
        return (next_transid, program_cache[next_prog_name], result.commarea or b"")

    if result.kind == DispatchKind.XCTL:
        prog_name = (result.program or "").strip()
        if prog_name not in program_cache:
            logger.error("XCTL to unknown program %r", prog_name)
            return DispatchResult(kind=DispatchKind.ABEND, abcode="PGMI")
        return (current_transid, program_cache[prog_name], result.commarea or b"")

    return result


def _run_dispatcher_with_runner(
    run_fn: RunCicsFn,
    program_cache: dict[str, Any],
    transid_to_program: dict[str, str],
    initial_context: CicsContext,
    screen_queue: ScreenChannel,
    input_queue: InputChannel,
) -> DispatchResult:
    """Core dispatcher loop — separated for testability."""
    context = initial_context
    program = program_cache[transid_to_program[context.transid]]

    while True:
        result = run_fn(program, context, screen_queue, input_queue)

        # On a pseudo-conversational RETURN TRANSID, the next turn's terminal
        # input arrives here (blocks). Its attention key seeds the next EIBAID.
        # (This input_queue.get() is the loop's own quirk; CicsRegion does not
        # replicate it — see CicsRegion.dispatch.)
        eibaid = context.eibaid
        if result.kind == DispatchKind.RETURN_TRANSID:
            event = input_queue.get()  # blocks
            eibaid = event.eibaid

        routing = _advance_routing(
            result, context.transid, program_cache, transid_to_program
        )
        if isinstance(routing, DispatchResult):
            return routing

        next_transid, program, next_commarea = routing
        context = CicsContext(
            transid=next_transid, commarea=next_commarea, eibaid=eibaid
        )


class CicsRegion:
    """Turn-by-turn CICS dispatch API.

    Models a running CICS region as an explicit state machine over the same
    routing rule the dispatcher loop uses (`_advance_routing`). Instead of an
    unbounded blocking loop, the caller drives one turn at a time:

      * ``start(entry_transid, ...)`` — begin a task on ``entry_transid`` and run
        its first program.
      * ``step(...)`` — run the CURRENT (program, transid, commarea) again.

    The caller supplies an ``input_event`` on the entry turn and on each turn
    that follows a RETURN_TRANSID (a fresh terminal input), and OMITS it after an
    XCTL (same task, no new terminal input — the XCTL'd program runs immediately).
    This mirrors CICS pseudo-conversational reality.

    Unlike ``_run_dispatcher_with_runner``, this does NOT do a separate
    ``input_queue.get()`` for the EIBAID: the supplied ``input_event`` is both put
    on the queue (for RECEIVE MAP) AND used directly to seed the context's eibaid.
    """

    def __init__(
        self,
        program_cache: dict[str, Any],
        transid_to_program: dict[str, str],
        screen_queue: ScreenChannel,
        input_queue: InputChannel,
        *,
        context_holder: list,
        result_holder: list,
        max_steps: int = 50_000,
        min_commarea_len: int = 0,
    ) -> None:
        self._program_cache = program_cache
        self._transid_to_program = transid_to_program
        self._screen_queue = screen_queue
        self._input_queue = input_queue
        self._context_holder = context_holder
        self._result_holder = result_holder
        self._max_steps = max_steps
        # Optional minimum commarea length applied to the commarea handed to each
        # FOLLOW-ON turn (after start). A program that XCTLs/RETURNs with a short
        # commarea but whose successor indexes a larger CARDDEMO-COMMAREA needs
        # EIBCALEN to cover those fields; pad to this length so the successor's
        # field reads land in-bounds. The entry commarea passed to start() is
        # used as-is (the entry program's own EIBCALEN is authoritative).
        self._min_commarea_len = min_commarea_len

        self._transid: str = ""
        self._program: Any = None
        self._commarea: bytes = b""
        self._last_eibaid: str = _DFHENTER
        self._done: bool = False

    @property
    def transid(self) -> str:
        """The current transid (for assertions if wanted)."""
        return self._transid

    @property
    def done(self) -> bool:
        """True once a terminal (RETURN / ABEND) result has been produced."""
        return self._done

    def start(
        self,
        entry_transid: str,
        *,
        commarea: bytes = b"",
        input_event: "InputEvent | None" = None,
        max_steps: int | None = None,
    ) -> DispatchResult:
        """Begin a task on ``entry_transid`` and dispatch its first program."""
        logger.info(
            "region.start: transid=%s commarea=%d B", entry_transid, len(commarea)
        )
        self._transid = entry_transid
        self._commarea = commarea
        self._program = self._program_cache[self._transid_to_program[entry_transid]]
        self._done = False
        return self._dispatch(input_event=input_event, max_steps=max_steps)

    def step(
        self,
        *,
        input_event: "InputEvent | None" = None,
        max_steps: int | None = None,
    ) -> DispatchResult:
        """Dispatch the CURRENT (program, transid, commarea). Requires not done."""
        if self._done:
            raise RuntimeError("step() called on a region that has terminated")
        _nfields = len(input_event.fields) if input_event is not None else 0
        _eibaid = repr(input_event.eibaid) if input_event is not None else "(none)"
        logger.info(
            "region.step: transid=%s eibaid=%s fields=%d",
            self._transid,
            _eibaid,
            _nfields,
        )
        return self._dispatch(input_event=input_event, max_steps=max_steps)

    def _dispatch(
        self,
        *,
        input_event: "InputEvent | None",
        max_steps: int | None,
    ) -> DispatchResult:
        eibaid = input_event.eibaid if input_event is not None else self._last_eibaid
        ctx = CicsContext(transid=self._transid, commarea=self._commarea, eibaid=eibaid)
        if input_event is not None:
            # The program's RECEIVE MAP consumes this (fields + eibaid). We do NOT
            # do a separate get() for eibaid — the context already carries it.
            self._input_queue.put(input_event)
        self._last_eibaid = eibaid

        result = run_cics(
            self._program,
            ctx,
            self._screen_queue,
            self._input_queue,
            context_holder=self._context_holder,
            result_holder=self._result_holder,
            max_steps=self._max_steps if max_steps is None else max_steps,
        )

        routing = _advance_routing(
            result, self._transid, self._program_cache, self._transid_to_program
        )
        if isinstance(routing, DispatchResult):
            logger.info("dispatch → terminal %s", routing.kind.name)
            self._done = True
        else:
            self._transid, self._program, next_commarea = routing
            if len(next_commarea) < self._min_commarea_len:
                next_commarea = next_commarea.ljust(self._min_commarea_len, b"\x00")
            self._commarea = next_commarea
            logger.info(
                "dispatch → transid=%s commarea=%d B",
                self._transid,
                len(self._commarea),
            )
        return result


# CSD grammar: a file is a sequence of DEFINE statements, each a kind followed by
# attribute(value) pairs (TRANSACTION(CC00) PROGRAM(COSGN00C) GROUP(CARDDEMO) ...).
# Attributes are order-independent and may span continuation lines (whitespace is
# ignored), so TRANSACTION and PROGRAM need not be adjacent — unlike the old regex.
# An attribute value is anything up to the closing paren (it may contain spaces,
# slashes, dots — e.g. DSNAME(AWS.M2...) or DEFINETIME(22/05/13 12:56:44)).
_CSD_GRAMMAR = r"""
    start: define*
    define: DEFINE_KW attr+
    attr: NAME "(" VALUE? ")"

    DEFINE_KW.2: "DEFINE"i
    NAME: /[A-Za-z][A-Za-z0-9-]*/
    VALUE: /[^()]+/

    %ignore /\s+/
"""

_csd_parser = Lark(_CSD_GRAMMAR, parser="lalr")


class _CsdTransformer(Transformer):
    """Turn the CSD parse tree into a list of {ATTR_NAME: value} dicts, one per DEFINE."""

    def attr(self, items: list) -> tuple[str, str]:
        name = str(items[0]).upper()
        value = str(items[1]).strip() if len(items) > 1 else ""
        return (name, value)

    def define(self, items: list) -> dict[str, str]:
        # items[0] is the DEFINE keyword token; the rest are (name, value) pairs.
        return dict(items[1:])

    def start(self, items: list) -> list[dict[str, str]]:
        return list(items)


def parse_csd(csd_path: Path) -> dict[str, str]:
    """Parse a CSD file to produce a {transid: program_name} mapping.

    Each ``DEFINE`` is parsed structurally into its attribute(value) pairs; a
    ``DEFINE TRANSACTION(t) ... PROGRAM(p)`` (attributes in any order) contributes
    ``{t: p}``. DEFINEs without both TRANSACTION and PROGRAM (e.g. FILE/PROGRAM
    definitions, or a TRANSACTION whose program is defined elsewhere) are skipped.
    """
    content = csd_path.read_text(encoding="utf-8", errors="replace")
    defines = _CsdTransformer().transform(_csd_parser.parse(content))
    result = {}
    for attrs in defines:
        if "TRANSACTION" in attrs and "PROGRAM" in attrs:
            result[attrs["TRANSACTION"].upper()] = attrs["PROGRAM"].upper()
    logger.info("CSD parsed: %d transid→program mappings", len(result))
    return result
