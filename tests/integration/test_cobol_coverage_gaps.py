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
    bridge_jar,  # noqa: F401
    run_cobol,
)
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned as _decode,
)
from tests.integration.cobol_helpers import (
    decode_zoned_with_decimal as _decode_dec,
)
from tests.integration.cobol_helpers import (
    first_region as _first_region,
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
    # red-dragon-clpn: REVERSE implemented. Was xfail; now green.
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

    # red-dragon-clpn: MAX implemented. Was xfail; now green.
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

    # red-dragon-clpn: MIN implemented. Was xfail; now green.
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

    # red-dragon-clpn: SUM implemented. Was xfail; now green.
    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_sum(self):
        """FUNCTION SUM(3 7 5) must yield 15."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNSUM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION SUM(3 7 5).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 15

    # red-dragon-clpn: RANDOM implemented (Python's random module). Was xfail; now green.
    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_random_seeded_yields_value_below_one(self):
        """FUNCTION RANDOM(1) is a fraction in [0,1); scaled by 1e6 it must be
        < 1000000 — not an echo of the seed argument."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNRND.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(7) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION RANDOM(1) * 1000000.",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 7) < 1000000

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_abs(self):
        """FUNCTION ABS(3 - 10) must yield 7."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNABS.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION ABS(3 - 10).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 7

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_sqrt(self):
        """FUNCTION SQRT(16) must yield 4."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNSQT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION SQRT(16).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 4

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_cos_of_zero(self):
        """FUNCTION COS(0) must yield 1 (distinguishes from the arg-1 fallback)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNCOS.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION COS(0).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 1) == 1

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_sin_of_zero(self):
        """FUNCTION SIN(0) must yield 0."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNSIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(1) VALUE 5.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION SIN(0).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 1) == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_tan_of_zero(self):
        """FUNCTION TAN(0) must yield 0."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNTAN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(1) VALUE 5.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION TAN(0).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 1) == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_acos_of_one(self):
        """FUNCTION ACOS(1) must yield 0 (distinguishes from the arg-1 fallback of 1)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNACS.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(1) VALUE 5.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION ACOS(1).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 1) == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_asin_of_zero(self):
        """FUNCTION ASIN(0) must yield 0."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNASN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(1) VALUE 5.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION ASIN(0).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 1) == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_atan_of_zero(self):
        """FUNCTION ATAN(0) must yield 0."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNATN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(1) VALUE 5.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION ATAN(0).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 1) == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_range(self):
        """FUNCTION RANGE(3 7 5) must yield 4."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNRNG.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION RANGE(3 7 5).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 4

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_mean(self):
        """FUNCTION MEAN(2 4 6) must yield 4."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNMEA.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION MEAN(2 4 6).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 4

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_median_odd_count(self):
        """FUNCTION MEDIAN(3 7 5) must yield 5."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNMED.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION MEDIAN(3 7 5).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 5

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_midrange(self):
        """FUNCTION MIDRANGE(2 8) must yield 5."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNMID.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION MIDRANGE(2 8).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 5

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_variance(self):
        """FUNCTION VARIANCE(2 4 6) must yield 4 (sample variance, n-1 divisor)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNVAR.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION VARIANCE(2 4 6).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 4

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_ord_max(self):
        """FUNCTION ORD-MAX(3 7 5) must yield 2 (1-based position of 7)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNOMX.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION ORD-MAX(3 7 5).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 2

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_ord_min(self):
        """FUNCTION ORD-MIN(3 7 5) must yield 1 (1-based position of 3)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNOMN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION ORD-MIN(3 7 5).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 1

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_concatenate(self):
        """FUNCTION CONCATENATE('AB' 'CD' 'EF') must yield 'ABCDEF'."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNCAT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-OUT PIC X(6) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE FUNCTION CONCATENATE('AB' 'CD' 'EF') TO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert bytes(region[0:6]).decode("cp037") == "ABCDEF"

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_exp_of_zero(self):
        """FUNCTION EXP(0) must yield 1 (distinguishes from the arg-1 fallback of 0)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNEXP.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION EXP(0).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 1) == 1

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_log_of_one(self):
        """FUNCTION LOG(1) must yield 0 (distinguishes from the arg-1 fallback of 1)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNLOG.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(1) VALUE 5.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION LOG(1).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 1) == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_factorial(self):
        """FUNCTION FACTORIAL(5) must yield 120."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNFAC.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(3) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION FACTORIAL(5).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 3) == 120

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_integer_floors(self):
        """FUNCTION INTEGER(7.2) must yield 7."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNINT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION INTEGER(7.2).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 1) == 7

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_integer_part(self):
        """FUNCTION INTEGER-PART(7.2) must yield 7."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNIPT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION INTEGER-PART(7.2).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 1) == 7

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_fraction_part(self):
        """FUNCTION FRACTION-PART(7.2) must yield .2 (distinguishes from the
        arg-1 fallback echoing the full 7.2)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNFPT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9V9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION FRACTION-PART(7.2).",
                "    STOP RUN.",
            ]
        )
        assert _decode_dec(_first_region(vm), 0, 1, 1) == Decimal("0.2")

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_rem(self):
        """FUNCTION REM(7 3) must yield 1."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNREM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(2) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION REM(7 3).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 2) == 1

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_substitute(self):
        """FUNCTION SUBSTITUTE('ABCABC' 'A' 'X') must yield 'XBCXBC'."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNSUB.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-OUT PIC X(6) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE FUNCTION SUBSTITUTE('ABCABC' 'A' 'X') TO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert bytes(region[0:6]).decode("cp037") == "XBCXBC"

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_exp10(self):
        """FUNCTION EXP10(2) must yield 100."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNE10.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(3) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION EXP10(2).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 3) == 100

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_log10(self):
        """FUNCTION LOG10(100) must yield 2 (distinguishes from the arg-1
        fallback of 100)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNL10.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(1) VALUE 5.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION LOG10(100).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 1) == 2

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_char(self):
        """FUNCTION CHAR(194) must yield 'A' (EBCDIC byte 0xC1)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNCHR.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-OUT PIC X(1) VALUE SPACE.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE FUNCTION CHAR(194) TO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert bytes(region[0:1]).decode("cp037") == "A"

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_ord(self):
        """FUNCTION ORD('A') must yield 194."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNORD.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(3) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION ORD('A').",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 3) == 194

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_day_of_integer(self):
        """FUNCTION DAY-OF-INTEGER(154498) must yield 2024001 (Julian date)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNDOI2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(7) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION DAY-OF-INTEGER(154498).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 7) == 2024001

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_integer_of_day(self):
        """FUNCTION INTEGER-OF-DAY(2024001) must yield 154498 (inverse of
        DAY-OF-INTEGER)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNIOD2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(6) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION INTEGER-OF-DAY(2024001).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 6) == 154498

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_annuity(self):
        """FUNCTION ANNUITY(0 4) must yield .25 (zero-rate special case)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNANN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9V99 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION ANNUITY(0 4).",
                "    STOP RUN.",
            ]
        )
        assert _decode_dec(_first_region(vm), 0, 1, 2) == Decimal("0.25")

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_present_value(self):
        """FUNCTION PRESENT-VALUE(0 100 100) must yield 200 (zero-rate: an
        undiscounted sum)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNPV.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(3) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION PRESENT-VALUE(0 100 100).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 3) == 200

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_date_to_yyyymmdd(self):
        """FUNCTION DATE-TO-YYYYMMDD(240101) must yield 20240101 (default
        cutoff 50: yy=24 < 50 -> 20yy)."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FND2Y.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(8) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION DATE-TO-YYYYMMDD(240101).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 8) == 20240101

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_day_to_yyyyddd(self):
        """FUNCTION DAY-TO-YYYYDDD(24001) must yield 2024001."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FND2D.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(7) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION DAY-TO-YYYYDDD(24001).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 7) == 2024001

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_year_to_yyyy(self):
        """FUNCTION YEAR-TO-YYYY(24) must yield 2024."""
        vm = _run(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNY2Y.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = FUNCTION YEAR-TO-YYYY(24).",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 0, 4) == 2024


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
