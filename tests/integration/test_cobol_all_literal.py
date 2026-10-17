"""Integration: ALL literal repeats its literal to the size of the associated item."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration import cobol_helpers
from tests.integration.cobol_helpers import first_region, run_cobol

bridge_jar = cobol_helpers.bridge_jar
pytestmark = pytest.mark.usefixtures("bridge_jar")


def _characters(region: bytearray, start: int, end: int) -> str:
    return bytes(region[start:end]).decode("cp037")


class TestAllLiteral:
    @covers(CobolFeature.FIGURATIVE_ALL, CobolFeature.VALUE_CLAUSE)
    def test_value_all_fills_the_item(self):
        region = first_region(
            run_cobol(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. ALLVAL.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    '01 W2 PIC X(10) VALUE ALL "AB".',
                    "01 W3 PIC X(4) VALUE ALL SPACES.",
                    "77 D5 PIC X(5) VALUE ALL QUOTE.",
                    "01 GRP VALUE ALL 'XYZ'.",
                    "   02 GA PIC X(4).",
                    "   02 GB PIC X(3).",
                    "PROCEDURE DIVISION.",
                    "MAIN-PARA.",
                    "    STOP RUN.",
                ]
            )
        )
        assert _characters(region, 0, 26) == 'ABABABABAB    """""XYZXYZX'

    @covers(CobolFeature.FIGURATIVE_ALL, CobolFeature.MOVE)
    def test_move_all_repeats_to_each_receiver(self):
        region = first_region(
            run_cobol(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. ALLMOVE.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "01 W4 PIC X(7).",
                    "01 W1 PIC X(1).",
                    "01 TBL.",
                    "   02 ROW OCCURS 3.",
                    "      03 CELL PIC X(2) OCCURS 2.",
                    "01 WZ PIC X(3).",
                    "PROCEDURE DIVISION.",
                    "MAIN-PARA.",
                    '    MOVE ALL "AB" TO W4 W1.',
                    '    MOVE ALL "ABCDE" TO TBL.',
                    "    MOVE ALL ZEROES TO WZ.",
                    "    STOP RUN.",
                ]
            )
        )
        assert _characters(region, 0, 23) == "ABABABAAABCDEABCDEAB000"

    @covers(CobolFeature.FIGURATIVE_ALL, CobolFeature.COMPARISON_OPERATORS)
    def test_comparison_and_condition_name_size_all_to_the_other_operand(self):
        conditions = (
            'D6 EQUAL TO ALL "BA"',
            'ALL "BA" = D6',
            'D6 = ALL "B"',
            'D5 = ALL "BA"',
            "DC = ALL 'BAC'",
            "DCOK",
            "DCNO",
            "ALL ZEROES = Z5",
            "D6 = ALL SPACES",
        )
        tests = [
            line
            for position, condition in enumerate(conditions, start=1)
            for line in (
                f"    IF {condition}",
                f"        MOVE 'Y' TO RES ({position}:1)",
                "    ELSE",
                f"        MOVE 'N' TO RES ({position}:1)",
                "    END-IF.",
            )
        ]
        region = first_region(
            run_cobol(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. ALLCMP.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "01 RES PIC X(9) VALUE SPACES.",
                    "01 D6 PIC X(6) VALUE 'BABABA'.",
                    "01 D5 PIC X(5) VALUE 'BABAB'.",
                    "01 DC PIC X(4) VALUE 'BACB'.",
                    "   88 DCOK VALUE ALL 'BAC'.",
                    "   88 DCNO VALUE ALL 'BA'.",
                    "01 Z5 PIC 9(5) VALUE 0.",
                    "PROCEDURE DIVISION.",
                    "MAIN-PARA.",
                    *tests,
                    "    SET DCNO TO TRUE.",
                    "    STOP RUN.",
                ],
                max_steps=100_000,
            )
        )
        assert _characters(region, 0, 9) + _characters(region, 20, 24) == (
            "YYNYYYNYNBABA"
        )
