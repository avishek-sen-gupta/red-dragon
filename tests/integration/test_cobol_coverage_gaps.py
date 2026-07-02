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

    # red-dragon-clpn: MOD implemented (used in CardDemo). Was xfail; now green.
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

    # red-dragon-clpn: DATE-OF-INTEGER implemented (used in CardDemo).
    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_date_of_integer(self):
        """FUNCTION DATE-OF-INTEGER(154498) must yield 20240101 (inverse of
        INTEGER-OF-DATE; day 154498 after the 1600-12-31 epoch)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNDOI.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-D PIC 9(8) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-D = FUNCTION DATE-OF-INTEGER(154498).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 8) == 20240101


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


# ── red-dragon-zgwl: arithmetic expression as an intrinsic-function argument ───
# F(g(x) - 1) must be ONE argument, not split by the bridge into [g(x), -1].


class TestFunctionArgArithmetic:
    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_date_of_integer_of_nested_minus_one_is_yesterday(self):
        """DATE-OF-INTEGER(INTEGER-OF-DATE(20240101) - 1) must be 20231231
        (yesterday), not 20240101 — the '- 1' must not be dropped.

        red-dragon-zgwl: the ProLeap bridge splits the single arithmetic argument
        'INTEGER-OF-DATE(WS-N) - 1' into two args [INTEGER-OF-DATE(WS-N), -1], so
        the subtraction is lost and DATE-OF-INTEGER round-trips the input unchanged.
        This is the real CardDemo report usage shape.
        """
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNARG.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-N   PIC 9(8) VALUE 20240101.",
                "01 WS-OUT PIC 9(8) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-OUT = FUNCTION DATE-OF-INTEGER(",
                "            FUNCTION INTEGER-OF-DATE(WS-N) - 1).",
                "    STOP RUN.",
            ]
        )
        # WS-N 8 bytes @0, WS-OUT @8.
        assert _decode(_first_region(vm), 8, 8) == 20231231


# ── red-dragon-kt70: arithmetic operators in a relation/expression operand ─────
# _lower_expr_dict must honour '-'/'*'/'/' rather than defaulting them to '+'.


class TestRelationArithmeticOperators:
    def _cmp(self, relation: str) -> str:
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. RELOP.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-A PIC 9(2) VALUE 10.",
                "01 WS-R PIC X(3) VALUE 'xxx'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                f"    IF {relation}",
                "        MOVE 'YES' TO WS-R",
                "    ELSE",
                "        MOVE 'NO ' TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        return bytes(_first_region(vm)[2:5]).decode("cp037")

    @covers(CobolFeature.COMPARISON_OPERATORS)
    def test_subtraction_in_relation_operand(self):
        # 10 - 1 = 9 must be TRUE (not 10 + 1 = 11).
        assert self._cmp("WS-A - 1 = 9") == "YES"

    @covers(CobolFeature.COMPARISON_OPERATORS)
    def test_multiplication_in_relation_operand(self):
        # 10 * 2 = 20 must be TRUE (not 10 + 2 = 12).
        assert self._cmp("WS-A * 2 = 20") == "YES"

    @covers(CobolFeature.COMPARISON_OPERATORS)
    def test_division_in_relation_operand(self):
        # 10 / 2 = 5 must be TRUE (not 10 + 2 = 12).
        assert self._cmp("WS-A / 2 = 5") == "YES"


# ── red-dragon-apoq: ROUNDED must not force integer division to float ──────────
# COBOL integer division truncates; the mod idiom A - (A / B) * B relies on it.


class TestIntegerDivisionSemantics:
    @covers(CobolFeature.COMPUTE)
    def test_mod_idiom_integer_division_truncates(self):
        """WS-Y - (WS-Y / 4 * 4) is the COBOL 'WS-Y mod 4' idiom: 2023/4=505
        (truncated), *4=2020, 2023-2020=3. red-dragon-apoq: the ROUNDED work
        forced ALL division to float (505.75*4=2023 -> 0), breaking this."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. IDIV.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-Y PIC 9(4) VALUE 2023.",
                "01 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = WS-Y - (WS-Y / 4 * 4).",
                "    STOP RUN.",
            ]
        )
        # WS-Y 4 bytes @0, WS-R @4.
        assert _decode(_first_region(vm), 4, 4) == 3

    @covers(CobolFeature.COMPUTE, CobolFeature.ROUNDED_CLAUSE)
    def test_rounded_division_still_rounds(self):
        """Guard the interaction: COMPUTE X ROUNDED = 10 / 3 must still round the
        fraction (3.33 -> 3) — i.e. the fix keeps float division for ROUNDED."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. RDIV.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-X PIC 9(3) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-X ROUNDED = 20 / 3.",
                "    STOP RUN.",
            ]
        )
        # 20/3 = 6.667 -> ROUNDED -> 7.
        assert _decode(_first_region(vm), 0, 3) == 7
