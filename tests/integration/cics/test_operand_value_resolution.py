"""Integration: RETURN TRANSID / XCTL PROGRAM data-name operands resolve to runtime VALUE.

The bug: ``EXEC CICS RETURN TRANSID(WS-TRANID)`` lowered the operand as a literal,
emitting Const(value="WS-TRANID") (the field NAME) instead of decoding the data item
to its runtime value (e.g. "CC01"). The dispatcher then could not route the transid.

These JAR-gated tests drive tiny COBOL programs through the REAL run_cics path and
assert the DispatchResult carries the decoded field value (not the field name).
A literal operand keeps the Const fast-path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from interpreter.cics.bootstrap import compile_cics_program
from interpreter.cics.preprocessor import apply_cics_prepass
from interpreter.cics.strategy import CicsLoweringStrategy
from interpreter.cics.types import CicsContext, DispatchKind
from interpreter.cics.dispatcher import run_cics
from tests.covers import covers
from tests.integration.cobol_helpers import JAR_AVAILABLE, JAR_PATH, bridge_jar_env

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)

_CICS_COPYBOOKS = Path(__file__).parents[3] / "interpreter" / "cics" / "copybooks"


@pytest.fixture(autouse=True)
def _bridge_jar_env(bridge_jar_env):
    yield


@pytest.fixture
def cobol_parser():
    runner = RealSubprocessRunner()
    return ProLeapCobolParser(runner, JAR_PATH, copybook_dirs=[_CICS_COPYBOOKS])


COBOL_RETURN_TRANSID_FIELD = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTRTF.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-TRANID PIC X(4) VALUE 'CC01'.
       PROCEDURE DIVISION.
           EXEC CICS RETURN TRANSID(WS-TRANID) END-EXEC.
           STOP RUN.
"""

COBOL_RETURN_TRANSID_LIT = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTRTL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-DUMMY PIC X.
       PROCEDURE DIVISION.
           EXEC CICS RETURN TRANSID('CC02') END-EXEC.
           STOP RUN.
"""

COBOL_XCTL_FIELD = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTXCF.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-PGM PIC X(8) VALUE 'COMEN01C'.
       PROCEDURE DIVISION.
           EXEC CICS XCTL PROGRAM(WS-PGM) END-EXEC.
           STOP RUN.
"""


def _run(source: str, parser) -> "object":
    import queue

    context_holder = [CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")]
    result_holder: list = [None]
    strategy = CicsLoweringStrategy(
        context_holder=context_holder, result_holder=result_holder
    )
    program = compile_cics_program(
        apply_cics_prepass(source).encode(), parser, strategy
    )
    return run_cics(
        program,
        context_holder[0],
        queue.Queue(),
        queue.Queue(),
        context_holder=context_holder,
        result_holder=result_holder,
    )


@covers(CobolFeature.EXEC_CICS)
def test_return_transid_field_resolves_to_runtime_value(cobol_parser):
    """RETURN TRANSID(WS-TRANID) routes the field VALUE 'CC01', not the name."""
    result = _run(COBOL_RETURN_TRANSID_FIELD, cobol_parser)
    assert result.kind == DispatchKind.RETURN_TRANSID
    assert (
        result.transid == "CC01"
    ), f"transid should be the decoded field value, got {result.transid!r}"


@covers(CobolFeature.EXEC_CICS)
def test_return_transid_literal_still_works(cobol_parser):
    """RETURN TRANSID('CC02') keeps the literal Const fast-path."""
    result = _run(COBOL_RETURN_TRANSID_LIT, cobol_parser)
    assert result.kind == DispatchKind.RETURN_TRANSID
    assert result.transid == "CC02"


@covers(CobolFeature.EXEC_CICS)
def test_xctl_program_field_resolves_to_runtime_value(cobol_parser):
    """XCTL PROGRAM(WS-PGM) routes the field VALUE 'COMEN01C', not the name."""
    result = _run(COBOL_XCTL_FIELD, cobol_parser)
    assert result.kind == DispatchKind.XCTL
    assert result.program is not None
    assert (
        result.program.strip() == "COMEN01C"
    ), f"program should be the decoded field value, got {result.program!r}"


COBOL_XCTL_SUBSCRIPTED = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTXSB.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-PGMS.
          05 WS-PGM OCCURS 3 TIMES PIC X(8).
       01 WS-IDX PIC 9(4) VALUE 2.
       PROCEDURE DIVISION.
           MOVE 'PROG0001' TO WS-PGM(1).
           MOVE 'COADM01C' TO WS-PGM(2).
           MOVE 'PROG0003' TO WS-PGM(3).
           EXEC CICS XCTL PROGRAM(WS-PGM(WS-IDX)) END-EXEC.
           STOP RUN.
"""


@covers(CobolFeature.EXEC_CICS)
def test_xctl_program_subscripted_operand_resolves_indexed_element(cobol_parser):
    """XCTL PROGRAM(WS-PGM(WS-IDX)) resolves the INDEXED element (element 2)."""
    result = _run(COBOL_XCTL_SUBSCRIPTED, cobol_parser)
    assert result.kind == DispatchKind.XCTL
    assert result.program is not None
    assert result.program.strip() == "COADM01C", (
        f"subscripted operand should resolve element 2 ('COADM01C'), "
        f"got {result.program!r} (element 1 means the subscript offset was dropped)"
    )
