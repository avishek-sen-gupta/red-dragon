"""Integration: EVALUATE WHEN conditions are space-normalized by the bridge.

Regression test for red-dragon-lu25. The ProLeap bridge's serializeEvaluate
emitted WHEN conditions via raw getText() (token concatenation with no spaces),
unlike the IF / SEARCH WHEN paths which apply insertSpaces. This produced
conditions like "WS-X=SPACES..." which downstream condition lowering cannot
parse. Assert at the parse/serialization layer that the relational operator in
the WHEN condition is space-separated.
"""

from __future__ import annotations

import pytest

from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.cobol_statements import EvaluateStatement, WhenStatement
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import JAR_AVAILABLE, JAR_PATH, to_fixed

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)


EVALUATE_SOURCE = to_fixed(
    [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. EVALSP.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-X PIC X(4).",
        "PROCEDURE DIVISION.",
        "    EVALUATE TRUE",
        "        WHEN WS-X = SPACES OR LOW-VALUES",
        "            CONTINUE",
        "        WHEN OTHER",
        "            CONTINUE",
        "    END-EVALUATE.",
        "    STOP RUN.",
    ]
)


def _all_statements(asg):
    stmts = list(asg.statements)
    for para in asg.paragraphs:
        stmts.extend(para.statements)
    for section in asg.sections:
        stmts.extend(section.statements)
        for para in section.paragraphs:
            stmts.extend(para.statements)
    return stmts


def _find_when_condition(asg) -> str:
    for stmt in _all_statements(asg):
        if isinstance(stmt, EvaluateStatement):
            for child in stmt.children:
                if isinstance(child, WhenStatement) and child.condition:
                    return child.condition
    raise AssertionError("No EVALUATE WHEN condition found in parsed ASG")


@covers(CobolFeature.EVALUATE)
def test_evaluate_when_condition_is_space_normalized():
    """EVALUATE WHEN condition has its relational operator space-separated."""
    parser = ProLeapCobolParser(RealSubprocessRunner(), JAR_PATH)
    asg = parser.parse(EVALUATE_SOURCE.encode("utf-8"))

    condition = _find_when_condition(asg)

    # Today (pre-fix): "WS-X=SPACESORLOW-VALUES" — operator glued to operands.
    assert (
        "WS-X = SPACES" in condition
    ), f"WHEN condition not space-normalized: {condition!r}"
