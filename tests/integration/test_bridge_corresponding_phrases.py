"""ADD/SUBTRACT CORRESPONDING carry ROUNDED and their size error phrases into the typed ASG."""

from __future__ import annotations

from collections.abc import Sequence

from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.cobol_statements import (
    ArithmeticCorrespondingStatement,
    CobolStatementType,
    MoveStatement,
)
from interpreter.cobol.features import CobolFeature
from tests.covers import covers

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. CORRPH.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 G1.",
    "   02 X PIC 99.",
    "01 G2.",
    "   02 X PIC 99.",
    "01 F PIC X.",
    "PROCEDURE DIVISION.",
    "MAIN.",
    "    ADD CORRESPONDING G1 TO G2 ROUNDED",
    "        ON SIZE ERROR MOVE 'E' TO F",
    "        NOT ON SIZE ERROR MOVE 'N' TO F",
    "    END-ADD.",
    "    SUBTRACT CORR G1 FROM G2",
    "        ON SIZE ERROR MOVE 'S' TO F",
    "    END-SUBTRACT.",
    "    GOBACK.",
]


def _moves(stmts: Sequence[CobolStatementType]) -> list[tuple[str, list[str]]]:
    return [
        (s.source.name, [t.name for t in s.targets])
        for s in stmts
        if isinstance(s, MoveStatement)
    ]


def _shape(
    stmt: CobolStatementType,
) -> tuple[
    str, str, str, bool, list[tuple[str, list[str]]], list[tuple[str, list[str]]]
]:
    assert isinstance(stmt, ArithmeticCorrespondingStatement)
    return (
        stmt.op,
        stmt.source.name,
        stmt.target.name,
        stmt.target.rounded,
        _moves(stmt.on_size_error),
        _moves(stmt.not_on_size_error),
    )


@covers(CobolFeature.ADD, CobolFeature.SUBTRACT, CobolFeature.ON_SIZE_ERROR)
def test_corresponding_statements_carry_rounded_and_size_error_phrases():
    source = "".join("       " + line + "\n" for line in _PROGRAM).encode()
    add, subtract, _goback = make_cobol_parser().parse(source).paragraphs[0].statements
    assert [_shape(add), _shape(subtract)] == [
        ("ADD", "G1", "G2", True, [("'E'", ["F"])], [("'N'", ["F"])]),
        ("SUBTRACT", "G1", "G2", False, [("'S'", ["F"])], []),
    ]
