"""Every form of EXIT reaches the typed ASG as the construct it leaves."""

from __future__ import annotations

from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.cobol_statements import (
    CobolStatementType,
    ExitStatement,
    PerformStatement,
)
from cobol_asg.exit_kind import ExitKind
from interpreter.cobol.features import CobolFeature
from tests.covers import covers

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. EXITS.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-N PIC 9 VALUE 0.",
    "PROCEDURE DIVISION.",
    "MAIN SECTION.",
    "P1.",
    "    PERFORM UNTIL WS-N > 3",
    "        ADD 1 TO WS-N",
    "        EXIT PERFORM",
    "    END-PERFORM.",
    "    PERFORM UNTIL WS-N > 6",
    "        ADD 1 TO WS-N",
    "        EXIT PERFORM CYCLE",
    "    END-PERFORM.",
    "    EXIT PARAGRAPH.",
    "P2.",
    "    EXIT SECTION.",
    "P3.",
    "    EXIT.",
]


def _exit(statement: CobolStatementType) -> ExitStatement:
    assert isinstance(statement, ExitStatement)
    return statement


def _inner_exit(statement: CobolStatementType) -> ExitStatement:
    assert isinstance(statement, PerformStatement)
    _, leaving = statement.children
    return _exit(leaving)


@covers(CobolFeature.EXIT, CobolFeature.EXIT_PARAGRAPH)
def test_each_exit_carries_the_construct_it_leaves():
    """EXIT PARAGRAPH once made the whole program fail to parse, and EXIT PERFORM
    read as a plain EXIT; each now arrives as its own kind, and a plain paragraph-end
    EXIT is still the no-op."""
    source = "".join("       " + line + "\n" for line in _PROGRAM).encode()
    p1, p2, p3 = make_cobol_parser().parse(source).sections[0].paragraphs
    first_loop, second_loop, leave_paragraph = p1.statements

    assert [
        _inner_exit(first_loop).kind,
        _inner_exit(second_loop).kind,
        _exit(leave_paragraph).kind,
        _exit(p2.statements[0]).kind,
        _exit(p3.statements[0]).kind,
    ] == [
        ExitKind.PERFORM,
        ExitKind.PERFORM_CYCLE,
        ExitKind.PARAGRAPH,
        ExitKind.SECTION,
        ExitKind.PLAIN,
    ]
