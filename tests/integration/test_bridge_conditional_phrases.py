"""STRING / UNSTRING overflow and CALL exception phrases reach the typed ASG."""

from __future__ import annotations

from collections.abc import Sequence

from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.cobol_statements import (
    CallStatement,
    CobolStatementType,
    MoveStatement,
    StringStatement,
    UnstringStatement,
)
from interpreter.cobol.features import CobolFeature
from tests.covers import covers

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. PHRASES.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-A   PIC X(4) VALUE 'ABCD'.",
    "01 WS-B   PIC X(2).",
    "01 WS-C   PIC X(2).",
    "01 WS-PGM PIC X(8) VALUE 'SUBPROG'.",
    "PROCEDURE DIVISION.",
    "MAIN.",
    "    STRING WS-A DELIMITED BY SIZE INTO WS-B",
    "        ON OVERFLOW MOVE 'O' TO WS-C",
    "        NOT ON OVERFLOW MOVE 'N' TO WS-C",
    "    END-STRING.",
    "    UNSTRING WS-A DELIMITED BY ',' INTO WS-B",
    "        ON OVERFLOW MOVE 'U' TO WS-C",
    "        NOT ON OVERFLOW MOVE 'V' TO WS-C",
    "    END-UNSTRING.",
    "    CALL WS-PGM",
    "        ON EXCEPTION MOVE 'X' TO WS-C",
    "        NOT ON EXCEPTION MOVE 'Y' TO WS-C",
    "    END-CALL.",
    "    CALL 'SUBPROG'",
    "        ON OVERFLOW MOVE 'Z' TO WS-C",
    "    END-CALL.",
    "    GOBACK.",
]


def _move(stmt: CobolStatementType) -> tuple[str, list[str]] | str:
    if not isinstance(stmt, MoveStatement):
        return type(stmt).__name__
    return (stmt.source.name, [t.name for t in stmt.targets])


def _moves(stmts: Sequence[CobolStatementType]) -> list[tuple[str, list[str]] | str]:
    return [_move(s) for s in stmts]


@covers(CobolFeature.STRING_VERB, CobolFeature.UNSTRING_VERB, CobolFeature.CALL)
def test_conditional_phrases_carry_their_statements_into_the_asg():
    source = "".join("       " + line + "\n" for line in _PROGRAM).encode()
    string_stmt, unstring_stmt, dynamic_call, static_call, _goback = (
        make_cobol_parser().parse(source).paragraphs[0].statements
    )
    assert isinstance(string_stmt, StringStatement)
    assert isinstance(unstring_stmt, UnstringStatement)
    assert isinstance(dynamic_call, CallStatement)
    assert isinstance(static_call, CallStatement)

    assert [
        (_moves(string_stmt.on_overflow), _moves(string_stmt.not_on_overflow)),
        (_moves(unstring_stmt.on_overflow), _moves(unstring_stmt.not_on_overflow)),
        (_moves(dynamic_call.on_exception), _moves(dynamic_call.not_on_exception)),
        (_moves(static_call.on_exception), _moves(static_call.not_on_exception)),
    ] == [
        ([("'O'", ["WS-C"])], [("'N'", ["WS-C"])]),
        ([("'U'", ["WS-C"])], [("'V'", ["WS-C"])]),
        ([("'X'", ["WS-C"])], [("'Y'", ["WS-C"])]),
        ([("'Z'", ["WS-C"])], []),
    ]
