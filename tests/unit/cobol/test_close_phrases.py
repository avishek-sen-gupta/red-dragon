"""CLOSE's REEL/UNIT and NO REWIND phrases on a non-reel/unit file, as IR
(red-dragon-sl30.94): REEL or UNIT reports 07 and never reaches the close
primitive; NO REWIND closes the file, then reports 07."""

from collections.abc import Sequence

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.features import CobolFeature
from interpreter.instructions import CallFunction, Const, InstructionBase, Label_
from interpreter.ir import CodeLabel
from tests.covers import covers

_SOURCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CLOSEPH.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT F1 ASSIGN TO DD1.
       DATA DIVISION.
       FILE SECTION.
       FD  F1.
       01  R1 PIC X(4).
       PROCEDURE DIVISION.
           CLOSE F1{phrase}.
           GOBACK.
"""


def _procedure(phrase: str) -> Sequence[InstructionBase]:
    ir = CobolFrontend(make_cobol_parser()).lower(
        _SOURCE.format(phrase=phrase).encode()
    )
    start, end = (
        next(
            n
            for n, i in enumerate(ir)
            if isinstance(i, Label_) and i.label == CodeLabel(label)
        )
        for label in ("func_closeph_0", "func_cancel_closeph_0")
    )
    return ir[start:end]


def _shape(phrase: str) -> tuple[int, bool]:
    procedure = _procedure(phrase)
    closes = sum(
        1
        for i in procedure
        if isinstance(i, CallFunction) and str(i.func_name) == "__cobol_close_file"
    )
    return closes, any(isinstance(i, Const) and i.value == "07" for i in procedure)


@covers(CobolFeature.CLOSE)
def test_reel_unit_skips_the_close_and_no_rewind_closes_then_reports_07():
    assert [
        _shape(phrase)
        for phrase in ("", " REEL", " UNIT FOR REMOVAL", " WITH NO REWIND")
    ] == [(1, False), (0, True), (0, True), (1, True)]
