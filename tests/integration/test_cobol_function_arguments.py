"""Arithmetic-expression arguments of intrinsic functions, run end to end."""

from __future__ import annotations

from decimal import Decimal

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    decode_zoned_with_decimal,
    run_cobol,
    ws_region,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_a_division_argument_keeps_the_statements_decimal_places():
    """SQRT is a floating-point function, so 9 / 7 is computed in floating point;
    REM is fixed point, so 3 / 2 carries the COMPUTE receiver's six decimals and
    the MOVE source's .75 its two -- neither truncates to an integer."""
    region = ws_region(
        run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNARG.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-S PIC 9V9(6) VALUE 0.",
                "01 WS-R PIC 9V9(6) VALUE 9.",
                "01 WS-M PIC 9V99 VALUE 9.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-S = FUNCTION SQRT(9 / 7).",
                "    COMPUTE WS-R = FUNCTION REM(3 / 2, .75).",
                "    MOVE FUNCTION REM(3 / 2, .75) TO WS-M.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        ),
        "FNARG",
    )
    assert (
        decode_zoned_with_decimal(region, 0, 1, 6),
        decode_zoned_with_decimal(region, 7, 1, 6),
        decode_zoned_with_decimal(region, 14, 1, 2),
    ) == (Decimal("1.133893"), Decimal("0"), Decimal("0"))


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_all_subscript_expands_to_every_occurrence_rightmost_fastest():
    """IBM Enterprise COBOL LR, "ALL subscripting": T(ALL, ALL) is T(1, 1)
    T(1, 2) ... T(2, 1) ..., so the 9 at C2(1, 2) is the second argument."""
    region = ws_region(
        run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FNALL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '01 ARR VALUE "126".',
                "   02 IND OCCURS 3 TIMES PIC 9.",
                '01 T2 VALUE "193456".',
                "   02 R2 OCCURS 2 TIMES.",
                "      03 C2 OCCURS 3 TIMES PIC 9.",
                "01 WS-SUM PIC 99 VALUE 0.",
                "01 WS-ORD PIC 99 VALUE 0.",
                "01 WS-COL PIC 99 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-SUM = FUNCTION SUM(IND(ALL)).",
                "    COMPUTE WS-ORD = FUNCTION ORD-MAX(C2(ALL, ALL)).",
                "    COMPUTE WS-COL = FUNCTION SUM(C2(ALL, 2) 1).",
                "    STOP RUN.",
            ],
            max_steps=4000,
        ),
        "FNALL",
    )
    assert (
        decode_zoned_with_decimal(region, 9, 2, 0),
        decode_zoned_with_decimal(region, 11, 2, 0),
        decode_zoned_with_decimal(region, 13, 2, 0),
    ) == (Decimal("9"), Decimal("2"), Decimal("15"))
