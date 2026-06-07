"""Integration: COMMAREA carries real field bytes on EXEC CICS RETURN / XCTL.

Task F1 of the CICS field-ref wiring plan.

The JAR-gated test drives a tiny COBOL program through the REAL run_cics path:
the program MOVEs a known value into a WORKING-STORAGE COMMAREA field, then
``EXEC CICS RETURN TRANSID('CC01') COMMAREA(WS-CA)`` — and asserts the returned
DispatchResult.commarea carries those bytes (NOT the old Const(b"") placeholder).

The non-JAR IR-level tests assert lowering wires a LoadRegion for a data-name
COMMAREA, and still falls back to Const for a literal / no COMMAREA.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from interpreter.cics.bootstrap import compile_cics_program
from interpreter.cics.preprocessor import apply_cics_prepass
from interpreter.cics.strategy import CicsLoweringStrategy
from interpreter.cics.types import CicsContext, DispatchKind
from interpreter.cics.dispatcher import run_cics
from interpreter.instructions import Const, LoadRegion
from interpreter.ir import Opcode
from interpreter.func_name import FuncName
from tests.covers import covers, NotLanguageFeature
from tests.integration.cobol_helpers import JAR_AVAILABLE, JAR_PATH, bridge_jar_env

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)

_CICS_COPYBOOKS = Path(__file__).parents[3] / "interpreter" / "cics" / "copybooks"


@pytest.fixture(autouse=True)
def _bridge_jar_env(bridge_jar_env):
    """Auto-apply the shared PROLEAP_BRIDGE_JAR env fixture to every test here."""
    yield


@pytest.fixture
def cobol_parser():
    runner = RealSubprocessRunner()
    return ProLeapCobolParser(runner, JAR_PATH, copybook_dirs=[_CICS_COPYBOOKS])


COBOL_COMMAREA = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTCA.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-CA.
          05 WS-CA-MSG PIC X(8).
       PROCEDURE DIVISION.
           MOVE 'HELLO123' TO WS-CA-MSG.
           EXEC CICS RETURN TRANSID('CC01') COMMAREA(WS-CA) END-EXEC.
           STOP RUN.
"""

COBOL_RETURN_LIT = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTLIT.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-DUMMY PIC X.
       PROCEDURE DIVISION.
           EXEC CICS RETURN TRANSID('CC01') END-EXEC.
           STOP RUN.
"""


@covers(CobolFeature.EXEC_CICS)
def test_commarea_carries_bytes(cobol_parser):
    """RETURN TRANSID COMMAREA(WS-CA) round-trips the program-written bytes."""
    import queue

    context_holder = [CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")]
    result_holder: list = [None]
    strategy = CicsLoweringStrategy(
        context_holder=context_holder, result_holder=result_holder
    )
    source = apply_cics_prepass(COBOL_COMMAREA).encode()
    program = compile_cics_program(source, cobol_parser, strategy)

    result = run_cics(
        program,
        context_holder[0],
        queue.Queue(),
        queue.Queue(),
        context_holder=context_holder,
        result_holder=result_holder,
    )

    assert result.kind == DispatchKind.RETURN_TRANSID
    assert result.transid == "CC01"
    # cp037 EBCDIC encoding of "HELLO123" must appear in the carried commarea.
    expected = "HELLO123".encode("cp037")
    assert result.commarea == expected, (
        f"COMMAREA did not carry program-written bytes: {result.commarea!r} "
        f"(expected {expected!r})"
    )


# ── IR-level tests (always run; not JAR-gated for the assertion itself) ──


@covers(CobolFeature.EXEC_CICS)
def test_return_commarea_field_lowers_to_loadregion(cobol_parser):
    """RETURN COMMAREA(WS-CA) emits a LoadRegion feeding set_return_context."""
    context_holder = [CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")]
    result_holder: list = [None]
    strategy = CicsLoweringStrategy(
        context_holder=context_holder, result_holder=result_holder
    )
    source = apply_cics_prepass(COBOL_COMMAREA).encode()
    frontend = CobolFrontend(cobol_parser=cobol_parser, exec_cics_strategy=strategy)
    instructions = frontend.lower(source)

    # A LoadRegion must be emitted (the COMMAREA field copy-in).
    load_regions = [i for i in instructions if isinstance(i, LoadRegion)]
    assert load_regions, "no LoadRegion emitted for COMMAREA(WS-CA)"

    # And set_return_context must be called with two args (transid, commarea),
    # the second of which is the LoadRegion result (NOT a Const b"").
    call = next(
        i
        for i in instructions
        if i.opcode == Opcode.CALL_FUNCTION
        and i.func_name == FuncName("__cics_set_return_context")  # type: ignore[attr-defined]
    )
    assert len(call.args) == 2, f"expected (transid, commarea) args, got {call.args}"
    commarea_reg = call.args[1]
    lr_result_regs = {lr.result_reg for lr in load_regions}
    assert (
        commarea_reg in lr_result_regs
    ), "COMMAREA arg is not fed by a LoadRegion (still the Const placeholder)"


@covers(CobolFeature.EXEC_CICS)
def test_return_commarea_literal_falls_back_to_const(cobol_parser):
    """RETURN TRANSID without a data-name COMMAREA keeps the Const fallback."""
    context_holder = [CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")]
    result_holder: list = [None]
    strategy = CicsLoweringStrategy(
        context_holder=context_holder, result_holder=result_holder
    )
    source = apply_cics_prepass(COBOL_RETURN_LIT).encode()
    frontend = CobolFrontend(cobol_parser=cobol_parser, exec_cics_strategy=strategy)
    instructions = frontend.lower(source)

    call = next(
        i
        for i in instructions
        if i.opcode == Opcode.CALL_FUNCTION
        and i.func_name == FuncName("__cics_set_return_context")  # type: ignore[attr-defined]
    )
    # Arg ordering preserved: (transid, commarea).
    assert len(call.args) == 2, f"expected (transid, commarea), got {call.args}"
    # No LoadRegion was emitted — there is no COMMAREA data-name to copy in.
    assert not any(isinstance(i, LoadRegion) for i in instructions)
    # The COMMAREA arg falls back to a Const(b"") placeholder.
    commarea_reg = call.args[1]
    const_b_regs = {
        i.result_reg for i in instructions if isinstance(i, Const) and i.value == b""
    }
    assert (
        commarea_reg in const_b_regs
    ), "literal/no-COMMAREA path should feed a Const(b'') fallback"
