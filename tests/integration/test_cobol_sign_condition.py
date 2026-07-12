"""Sign conditions: IF identifier IS [NOT] POSITIVE / NEGATIVE / ZERO.

red-dragon-tqog: sign conditions were serialized by the bridge as a text-only
relation ({'relation': {'text': 'NISPOSITIVE'}}) and crashed in
_lower_relation_node with KeyError 'left'. The bridge now emits a structured
{'sign': 'POSITIVE'|'NEGATIVE'|'ZERO', 'operand': <expr>, 'not': bool} node
(mirroring class conditions), and condition lowering compares the decoded operand
against zero (>0 / <0 / ==0).

These exercise all three sign types, positive/negative/zero operand values, and
the NOT form, asserting the correct IF branch is taken (RESULT=1 = THEN, 9 = ELSE).
"""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    run_cobol,
)
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned as _decode,
)
from tests.integration.cobol_helpers import (
    first_region as _first_region,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR (fails loudly if unset)."""


# WS = N PIC S9(3) (offset 0, 3 bytes) + RESULT PIC 9(1) (offset 3).
_RESULT_OFFSET = 3


def _program(value: int, condition: str) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. SIGNT.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01  WS.",
        "    05  N      PIC S9(3).",
        "    05  RESULT PIC 9(1).",
        "PROCEDURE DIVISION.",
        "MAIN.",
        f"    MOVE {value} TO N.",
        f"    IF {condition} MOVE 1 TO RESULT ELSE MOVE 9 TO RESULT.",
        "    STOP RUN.",
    ]


def _branch(value: int, condition: str) -> int:
    vm = run_cobol(_program(value, condition), max_steps=3000)
    return _decode(_first_region(vm), _RESULT_OFFSET, 1)


class TestSignCondition:
    @pytest.mark.parametrize(
        "value, condition, expected",
        [
            (5, "N IS POSITIVE", 1),
            (-5, "N IS POSITIVE", 9),
            (0, "N IS POSITIVE", 9),
            (-5, "N IS NEGATIVE", 1),
            (5, "N IS NEGATIVE", 9),
            (0, "N IS NEGATIVE", 9),
            (0, "N IS ZERO", 1),
            (5, "N IS ZERO", 9),
            (-5, "N IS NOT POSITIVE", 1),
            (5, "N IS NOT POSITIVE", 9),
        ],
    )
    @covers(CobolFeature.IF_ELSE)
    def test_sign_condition_selects_correct_branch(
        self, value: int, condition: str, expected: int
    ):
        assert _branch(value, condition) == expected
