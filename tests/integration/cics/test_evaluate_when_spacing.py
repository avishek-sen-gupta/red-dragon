"""Integration: EVALUATE WHEN conditions are structured by the bridge.

Originally red-dragon-lu25 space-normalized a flat WHEN-condition string. That
bandaid was superseded by red-dragon-z31u: the bridge now routes EVALUATE WHEN
conditions through the SAME structured serializer the IF path uses, so a WHEN
condition is a structured condition dict (op/left/right + relation/figurative),
not a string. Assert the structured shape — including the abbreviated OR and the
figurative operands that the flat-string path could not represent.
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


def _find_when_condition(asg):
    for stmt in _all_statements(asg):
        if isinstance(stmt, EvaluateStatement):
            for child in stmt.children:
                if isinstance(child, WhenStatement) and child.condition:
                    return child.condition
    raise AssertionError("No EVALUATE WHEN condition found in parsed ASG")


@covers(CobolFeature.EVALUATE)
def test_evaluate_when_condition_is_structured():
    """EVALUATE WHEN condition is a structured dict matching the IF path."""
    parser = ProLeapCobolParser(RealSubprocessRunner(), JAR_PATH)
    asg = parser.parse(EVALUATE_SOURCE.encode("utf-8"))

    condition = _find_when_condition(asg)

    # Structured shape — the abbreviated "WS-X = SPACES OR LOW-VALUES" expands
    # into an OR of two relations, with figurative operands sized downstream.
    assert isinstance(condition, dict), f"expected structured dict, got {condition!r}"
    assert condition.get("op") == "OR", condition
    left = condition["left"]["relation"]
    right = condition["right"]["relation"]
    assert left["left"] == {"kind": "ref", "name": "WS-X"}
    assert left["op"] == "=="
    assert left["right"] == {"kind": "figurative", "value": "SPACES"}
    # The trailing operand inherits the subject WS-X and operator "=".
    assert right["left"] == {"kind": "ref", "name": "WS-X"}
    assert right["op"] == "=="
    assert right["right"] == {"kind": "figurative", "value": "LOW-VALUES"}
