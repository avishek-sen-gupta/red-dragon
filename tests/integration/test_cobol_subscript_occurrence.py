"""Regression: subscripted field access on non-first OCCURS occurrences.

red-dragon-9cxh: a relational/condition operand load dropped the
``(subscript - 1) * stride`` term, so ``IF XNUM(n) ...`` read occurrence 1
regardless of ``n``. A loop that increments ``XNUM(n)`` and exits on
``IF XNUM(n) ...`` therefore never terminated for ``n >= 2`` (the comparison
read a different occurrence than the increment wrote). It was invisible for
``n == 1`` because ``(1 - 1) * stride == 0``.

These tests increment ``XNUM(n)`` in a GO TO loop until it reaches 5, then read
the value back from the correct occurrence's offset and assert it is exactly 5.
For ``n >= 2`` this only holds once the comparison resolves the same occurrence
the increment writes; before the fix the loop ran away and the value never
settled at 5.
"""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,
    decode_zoned_unsigned as _decode,
    first_region as _first_region,
    run_cobol,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR (fails loudly if unset)."""


# Each OCCURS element (GRP) is P1 = 34 + 6 + 80 = 120 bytes; XNUM sits at
# offset 34 within the element, so occurrence n (1-based) is at (n-1)*120 + 34.
_ELEMENT_STRIDE = 120
_XNUM_OFFSET_IN_ELEMENT = 34
_XNUM_LEN = 6


def _program(sub: int) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. SUBOCC.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01  REC.",
        "    03  GRP OCCURS 10 TIMES.",
        "        05  P1.",
        "            07  FILLER PIC X(34).",
        "            07  XNUM   PIC 9(6).",
        "            07  FILLER PIC X(80).",
        "PROCEDURE DIVISION.",
        "MAIN.",
        f"    MOVE ZERO TO XNUM ({sub}).",
        "LP.",
        f"    ADD 1 TO XNUM ({sub}).",
        f"    IF XNUM ({sub}) LESS THAN 5 GO TO LP.",
        "    STOP RUN.",
    ]


class TestSubscriptedOccurrenceIncrement:
    @pytest.mark.parametrize("sub", [1, 2, 3])
    @covers(CobolFeature.OCCURS_FIXED)
    def test_increment_loop_terminates_at_correct_occurrence(self, sub: int):
        # max_steps bounds the run: if the comparison read the wrong occurrence
        # the loop would not settle at 5 within this budget (the regression).
        vm = run_cobol(_program(sub), max_steps=5000)
        region = _first_region(vm)
        offset = (sub - 1) * _ELEMENT_STRIDE + _XNUM_OFFSET_IN_ELEMENT
        assert _decode(region, offset, _XNUM_LEN) == 5
