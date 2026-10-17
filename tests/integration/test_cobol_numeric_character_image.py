"""Integration: what MOVE, STRING and INSPECT read out of a numeric item as characters."""

from collections.abc import Sequence

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    first_region,
    run_cobol,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


def _region_text(
    receivers: Sequence[str], data: Sequence[str], body: Sequence[str], width: int
) -> str:
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. NUMIMG.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            *receivers,
            *data,
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            *body,
            "    STOP RUN.",
        ],
        max_steps=100_000,
    )
    return bytes(first_region(vm)[:width]).decode("cp037")


class TestNumericCharacterImage:
    @covers(CobolFeature.MOVE, CobolFeature.SIGN_CLAUSE)
    def test_move_to_a_character_receiver_sends_the_unsigned_digits_with_scaling_zeros(
        self,
    ):
        text = _region_text(
            [
                "01 R-S1   PIC X.",
                "01 R-S2   PIC X(2).",
                "01 R-C3   PIC X(4).",
                "01 R-B3   PIC X(4).",
                "01 R-P3   PIC X(4).",
                "01 R-PP   PIC X(3).",
                "01 R-P17  PIC X(18).",
                "01 R-AE   PIC XBXXX/XXX/XXX/XXX/XXXBXX.",
                "01 R-DEC  PIC X(2).",
                "01 R-U4   PIC X(4).",
            ],
            [
                "01 S1   PIC S9 VALUE 1.",
                "01 S2   PIC S9(2) VALUE -12.",
                "01 C3   PIC S9(3) COMP-3 VALUE -123.",
                "01 B3   PIC S9(3) COMP VALUE -123.",
                "01 P3   PIC 9P(3) VALUE 5000.",
                "01 PP   PIC S9PP VALUE 200.",
                "01 P17  PIC S9P(17) SIGN LEADING SEPARATE.",
                "01 DEC  PIC 9V9 VALUE 1.5.",
                "01 U4   PIC 9(4) VALUE 12.",
            ],
            [
                "    MOVE -100000000000000000 TO P17",
                "    MOVE S1 TO R-S1",
                "    MOVE S2 TO R-S2",
                "    MOVE C3 TO R-C3",
                "    MOVE B3 TO R-B3",
                "    MOVE P3 TO R-P3",
                "    MOVE PP TO R-PP",
                "    MOVE P17 TO R-P17 R-AE",
                "    MOVE DEC TO R-DEC",
                "    MOVE U4 TO R-U4",
            ],
            1 + 2 + 4 + 4 + 4 + 3 + 18 + 24 + 2 + 4,
        )
        assert text == (
            "1"
            "12"
            "123 "
            "123 "
            "5000"
            "200"
            "100000000000000000"
            "1 000/000/000/000/000 00"
            "15"
            "0012"
        )

    @covers(CobolFeature.STRING_VERB, CobolFeature.SIGN_CLAUSE)
    def test_string_sends_the_stored_characters_sign_included(self):
        text = _region_text(
            ["01 OUT PIC X(21) VALUE SPACES."],
            [
                "01 LS4  PIC S9(4) SIGN LEADING SEPARATE VALUE +1001.",
                "01 TS4  PIC S9(4) SIGN TRAILING SEPARATE VALUE -1001.",
                "01 OP4  PIC S9(4) VALUE -1001.",
                "01 U4   PIC 9(4) VALUE 12.",
            ],
            [
                "    STRING LS4 DELIMITED BY SIZE '/' DELIMITED BY SIZE",
                "           TS4 DELIMITED BY SIZE '/' DELIMITED BY SIZE",
                "           OP4 DELIMITED BY SIZE '/' DELIMITED BY SIZE",
                "           U4 DELIMITED BY SIZE INTO OUT",
            ],
            21,
        )
        assert text == "+1001/1001-/100J/0012"

    @covers(
        CobolFeature.INSPECT_TALLYING,
        CobolFeature.INSPECT_REPLACING,
        CobolFeature.SIGN_CLAUSE,
    )
    def test_inspect_sees_the_digits_and_keeps_the_sign_on_write_back(self):
        text = _region_text(
            [
                "01 N-MINUS  PIC 9(3).",
                "01 N-FIVE   PIC 9(3).",
                "01 N-LMINUS PIC 9(3).",
                "01 N-LFIVE  PIC 9(3).",
                "01 R-OP     PIC X(6) VALUE SPACES.",
                "01 R-LS     PIC X(6).",
                "01 R-TS     PIC X(6).",
            ],
            [
                "01 OP5  PIC S9(5) VALUE -12345.",
                "01 LS5  PIC S9(5) SIGN LEADING SEPARATE VALUE -12345.",
                "01 TS5  PIC S9(5) SIGN TRAILING SEPARATE VALUE -12345.",
            ],
            [
                "    MOVE ZERO TO N-MINUS N-FIVE N-LMINUS N-LFIVE",
                '    INSPECT OP5 TALLYING N-MINUS FOR ALL "-"',
                '                         N-FIVE FOR ALL "5"',
                '    INSPECT LS5 TALLYING N-LMINUS FOR ALL "-"',
                '                         N-LFIVE FOR ALL "5"',
                '    INSPECT OP5 REPLACING ALL "5" BY "7"',
                '    INSPECT LS5 REPLACING ALL "1" BY "9"',
                '    INSPECT TS5 CONVERTING "12" TO "34"',
                "    STRING OP5 DELIMITED BY SIZE INTO R-OP",
                "    STRING LS5 DELIMITED BY SIZE INTO R-LS",
                "    STRING TS5 DELIMITED BY SIZE INTO R-TS",
            ],
            4 * 3 + 3 * 6,
        )
        assert text == "000001000001" "1234P " "-92345" "34345-"
