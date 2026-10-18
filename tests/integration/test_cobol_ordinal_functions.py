"""FUNCTION CHAR and ORD follow the program collating sequence."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    first_region,
    run_cobol,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


def _program(
    alphabet: str, char_1: int, ord_1: str, ord_2: str, char_2: int
) -> list[str]:
    configuration = (
        [
            "ENVIRONMENT DIVISION.",
            "CONFIGURATION SECTION.",
            "OBJECT-COMPUTER. TESTER",
            "    PROGRAM COLLATING SEQUENCE IS SEQ.",
            "SPECIAL-NAMES.",
            f"    ALPHABET SEQ IS {alphabet}.",
        ]
        if alphabet
        else []
    )
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. ORDINAL.",
        *configuration,
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-R.",
        "   05 C-1 PIC X.",
        "   05 O-1 PIC 999.",
        "   05 O-2 PIC 999.",
        "   05 C-2 PIC X.",
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        f"    MOVE FUNCTION CHAR({char_1}) TO C-1.",
        f'    COMPUTE O-1 = FUNCTION ORD("{ord_1}").',
        f'    COMPUTE O-2 = FUNCTION ORD("{ord_2}").',
        f"    MOVE FUNCTION CHAR({char_2}) TO C-2.",
        "    STOP RUN.",
    ]


def _results(program: list[str]) -> str:
    return bytes(first_region(run_cobol(program, max_steps=5000))[0:8]).decode("cp037")


class TestOrdinalFunctions:
    @covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.PROGRAM_COLLATING_SEQUENCE)
    def test_char_and_ord_use_the_program_collating_sequence(self):
        """IBM Enterprise COBOL LR, CHAR and ORD: the ordinal position is in the
        program collating sequence, counted from 1; where characters share a
        position, CHAR returns the first literal the ALPHABET clause names for it.
        With no PROGRAM COLLATING SEQUENCE the sequence is native EBCDIC."""
        assert [
            _results(_program("", 194, "0", "A", 241)),
            _results(_program("STANDARD-2", 37, "5", "A", 66)),
            _results(_program('"B" ALSO "A" "C"', 1, "A", "C", 2)),
        ] == ["A241194" + "0", "$054066A", "B001002C"]
