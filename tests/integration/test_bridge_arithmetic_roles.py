"""The bridge names SUBTRACT's and DIVIDE's operand roles as written; the typed ASG
reads them by name."""

from __future__ import annotations

import pytest

from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.cobol_statements import ArithmeticStatement, CobolStatementType
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401

pytestmark = pytest.mark.usefixtures("bridge_jar")

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. ROLES.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 X PIC 99.",
    "01 W PIC 99.",
    "01 Y PIC 99.",
    "01 Z PIC 99.",
    "01 R PIC 99.",
    "PROCEDURE DIVISION.",
    "MAIN.",
    "    SUBTRACT X W FROM Y GIVING Z.",
    "    SUBTRACT X W FROM Y Z.",
    "    DIVIDE X INTO Y GIVING Z.",
    "    DIVIDE X BY Y GIVING Z REMAINDER R.",
    "    DIVIDE X INTO Y Z.",
    "    GOBACK.",
]


def _names(stmt: CobolStatementType) -> tuple[list[str], list[str], list[str], str]:
    assert isinstance(stmt, ArithmeticStatement)
    return (
        [o.name for o in stmt.operands],
        [t.name for t in stmt.targets],
        [g.name for g in stmt.giving],
        stmt.remainder.name if stmt.remainder else "",
    )


def _roles(stmt: CobolStatementType) -> dict[str, str | list[str]]:
    assert isinstance(stmt, ArithmeticStatement)
    return {
        key: (
            [item["name"] for item in value]
            if isinstance(value, list)
            else value["name"]
        )
        for key, value in stmt.to_dict().items()
        if key in ("minuend", "subtrahends", "dividend", "divisor")
    }


@covers(CobolFeature.SUBTRACT, CobolFeature.DIVIDE, CobolFeature.GIVING_CLAUSE)
def test_subtract_and_divide_operands_arrive_by_role():
    source = "".join("       " + line + "\n" for line in _PROGRAM).encode()
    *arithmetic, _goback = make_cobol_parser().parse(source).paragraphs[0].statements
    assert [(_names(s), _roles(s)) for s in arithmetic] == [
        (
            (["Y", "X", "W"], [], ["Z"], ""),
            {"minuend": "Y", "subtrahends": ["X", "W"]},
        ),
        ((["X", "W"], ["Y", "Z"], [], ""), {"subtrahends": ["X", "W"]}),
        ((["Y", "X"], [], ["Z"], ""), {"dividend": "Y", "divisor": "X"}),
        ((["X", "Y"], [], ["Z"], "R"), {"dividend": "X", "divisor": "Y"}),
        ((["X"], ["Y", "Z"], [], ""), {"divisor": "X"}),
    ]
