"""Integration tests for COBOL coverage gaps (run() through the VM).

Two kinds of test live here:

* ``xfail(strict=True)`` tests characterize a KNOWN, still-open gap: they encode
  the COBOL-correct behavior, fail today, and will turn into a hard failure the
  moment the feature is implemented — that is the signal to delete the xfail.
* Plain tests fill an integration-coverage hole for a feature that IS already
  implemented but was only unit-tested (flipping a PARTIAL issue to DONE).

Each test cites the Beads issue it pins.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,
    decode_zoned_unsigned as _decode,
    decode_zoned_with_decimal as _decode_dec,
    first_region as _first_region,
    run_cobol,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR (fails loudly if unset)."""


def _run(lines: list[str], max_steps: int = 4000):
    return run_cobol(lines, max_steps=max_steps)


# ── red-dragon-d3ww: field-to-field numeric MOVE loses the fractional part ────


class TestNumericMoveFractionalDigits:
    # red-dragon-d3ww was fixed since filing (this test XPASSed under xfail-strict):
    # field-to-field numeric MOVE now preserves the fraction. Kept as a regression.
    @covers(CobolFeature.MOVE)
    def test_numeric_field_move_preserves_fraction(self):
        """MOVE WS-SRC TO WS-DST (both 9(5)V99) must preserve .67, not store .00."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MVFRAC.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-SRC PIC 9(5)V99 VALUE 12345.67.",
                "01 WS-DST PIC 9(5)V99 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-SRC TO WS-DST.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-SRC = 7 bytes @0, WS-DST = 7 bytes @7. 5 integer + 2 fractional digits.
        assert _decode_dec(region, 7, 5, 2) == Decimal("12345.67")


# ── red-dragon-clpn: most intrinsic FUNCTIONs fall back to their first arg ─────


class TestIntrinsicFunctions:
    @pytest.mark.xfail(
        strict=True,
        reason="red-dragon-clpn: FUNCTION REVERSE not implemented (returns arg 1)",
    )
    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_reverse(self):
        """FUNCTION REVERSE('ABCDE') must yield 'EDCBA'."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNREV.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-OUT PIC X(5) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE FUNCTION REVERSE('ABCDE') TO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert bytes(region[0:5]).decode("cp037") == "EDCBA"

    @pytest.mark.xfail(
        strict=True,
        reason="red-dragon-clpn: FUNCTION MAX not implemented (returns arg 1)",
    )
    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_max(self):
        """FUNCTION MAX(3 7 5) must yield 7."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNMAX.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION MAX(3 7 5).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 7

    @pytest.mark.xfail(
        strict=True,
        reason="red-dragon-clpn: FUNCTION MIN not implemented (returns arg 1)",
    )
    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_min(self):
        """FUNCTION MIN(3 7 5) must yield 3."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNMIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION MIN(8 3 5).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 3

    @pytest.mark.xfail(
        strict=True,
        reason="red-dragon-clpn: FUNCTION MOD not implemented (returns arg 1)",
    )
    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_mod(self):
        """FUNCTION MOD(17 5) must yield 2."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNMOD.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION MOD(17 5).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 2


# ── red-dragon-frdu: arithmetic target ref-mod for SUBTRACT/MULTIPLY/DIVIDE ────
# ADD (TO and GIVING) is already integration-tested; these close the partial gap
# for the other three verbs. Expected to PASS (the writeback path is shared).


class TestArithmeticTargetRefModNonAdd:
    def _buf_program(self, stmt: str) -> list[str]:
        return [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. ARTRM.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "77 WS-A PIC 9(3) VALUE 100.",
            "01 WS-BUF PIC X(9) VALUE 'XXXYYYZZZ'.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            f"    {stmt}",
            "    STOP RUN.",
        ]

    @covers(CobolFeature.ARITHMETIC_TARGET_REF_MOD, CobolFeature.SUBTRACT)
    def test_subtract_giving_target_ref_mod(self):
        """SUBTRACT 5 FROM WS-A GIVING WS-BUF(4:3): 100-5=95 → splice '095'."""
        vm = _run(self._buf_program("SUBTRACT 5 FROM WS-A GIVING WS-BUF(4:3)."))
        # WS-A 3 bytes @0; WS-BUF 9 bytes @3.
        assert bytes(_first_region(vm)[3:12]).decode("cp037") == "XXX095ZZZ"

    @covers(CobolFeature.ARITHMETIC_TARGET_REF_MOD, CobolFeature.MULTIPLY)
    def test_multiply_giving_target_ref_mod(self):
        """MULTIPLY WS-A BY 2 GIVING WS-BUF(4:3): 100*2=200 → splice '200'."""
        vm = _run(self._buf_program("MULTIPLY WS-A BY 2 GIVING WS-BUF(4:3)."))
        assert bytes(_first_region(vm)[3:12]).decode("cp037") == "XXX200ZZZ"

    @covers(CobolFeature.ARITHMETIC_TARGET_REF_MOD, CobolFeature.DIVIDE)
    def test_divide_giving_target_ref_mod(self):
        """DIVIDE WS-A BY 4 GIVING WS-BUF(4:3): 100/4=25 → splice '025'."""
        vm = _run(self._buf_program("DIVIDE WS-A BY 4 GIVING WS-BUF(4:3)."))
        assert bytes(_first_region(vm)[3:12]).decode("cp037") == "XXX025ZZZ"
