"""Combined and abbreviated combined relation conditions: precedence and NOT."""

import pytest

from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.cobol_statements import IfStatement
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    first_region,
    run_cobol,
    to_fixed,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR for this test module."""


def _if(condition: list[str], flag: str) -> list[str]:
    return [
        f"    IF {condition[0]}",
        *[f"       {line}" for line in condition[1:]],
        f"        MOVE 1 TO {flag}",
        "    ELSE",
        f"        MOVE 0 TO {flag}",
        "    END-IF.",
    ]


_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. COMBCOND.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-R.",
    *[f"   05 R{n} PIC 9 VALUE 9." for n in range(1, 8)],
    "01 C1 PIC 99 VALUE 11.",
    "01 C2 PIC 99 VALUE 12.",
    "01 C3 PIC 99 VALUE 13.",
    "01 A PIC 9 VALUE 1.",
    "01 B PIC 9 VALUE 0.",
    "01 C PIC 9 VALUE 0.",
    "01 SW1 PIC 9 VALUE 1.",
    "   88 ON-SW-1 VALUE 1.",
    "   88 OFF-SW-1 VALUE 0.",
    "01 SW2 PIC 9 VALUE 1.",
    "   88 OFF-SW-2 VALUE 0.",
    "01 W1 PIC 9 VALUE 1.",
    "01 W2 PIC 9 VALUE 2.",
    "01 W3 PIC 9 VALUE 3.",
    "01 W4 PIC 9 VALUE 0.",
    "01 X1 PIC 99 VALUE 9.",
    "01 X2 PIC 99 VALUE 8.",
    "01 X3 PIC 99 VALUE 10.",
    "01 X4 PIC 99 VALUE 11.",
    "01 X5 PIC 99 VALUE 12.",
    "01 X6 PIC 99 VALUE 7.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
    *_if(["C1 = 11 AND C3 > 12 OR C2 < 20 AND C1 > 12"], "R1"),
    *_if(["A = 1 OR B = 1 AND C = 1"], "R2"),
    *_if(["ON-SW-1 OR NOT OFF-SW-2 AND OFF-SW-1"], "R3"),
    *_if(["NOT (W1 NOT GREATER W2 AND", "W3 AND NOT W4)"], "R4"),
    *_if(["X1 > X2 AND NOT < X3 OR", "X4 OR NOT X5 AND X6"], "R5"),
    *_if(["X1 > X4 OR NOT X5"], "R6"),
    *_if(["X1 > X2 AND NOT < X3"], "R7"),
    "    STOP RUN.",
]


class TestCombinedConditions:
    @covers(CobolFeature.IF_ELSE, CobolFeature.LEVEL_88_CONDITION)
    def test_and_binds_tighter_than_or_and_abbreviations_keep_their_not(self):
        """ANSI X3.23-1985 VI-6.15: NOT binds tighter than AND, AND tighter
        than OR; an abbreviated operand takes the last stated subject and
        relational operator, a NOT before an operator is part of it, and a NOT
        before a bare operand negates that one relation."""
        vm = run_cobol(_PROGRAM, max_steps=5000)
        assert bytes(first_region(vm)[0:7]).decode("cp037") == "1110110"

    def test_bridge_groups_or_of_and_runs_with_abbreviation_subjects(self):
        source = to_fixed(_PROGRAM).encode()
        stmt = make_cobol_parser().parse(source).paragraphs[0].statements[4]
        assert isinstance(stmt, IfStatement)
        x1 = {"kind": "ref", "name": "X1"}

        def ref(name: str) -> dict:
            return {"kind": "ref", "name": name}

        def rel(op: str, right: str, left: dict = x1) -> dict:
            return {
                "not": False,
                "relation": {"left": left, "op": op, "right": ref(right)},
            }

        def abbreviated(name: str, negated: bool, op: str) -> dict:
            return {
                "not": negated,
                "condition_name": name,
                "abbreviation": {"left": x1, "op": op},
            }

        assert stmt.condition == {
            "op": "OR",
            "left": {
                "op": "OR",
                "left": {"op": "AND", "left": rel(">", "X2"), "right": rel(">=", "X3")},
                "right": abbreviated("X4", False, ">="),
            },
            "right": {
                "op": "AND",
                "left": abbreviated("X5", True, ">="),
                "right": abbreviated("X6", False, ">="),
            },
        }
