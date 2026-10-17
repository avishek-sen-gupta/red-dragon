"""PROGRAM COLLATING SEQUENCE: comparisons and HIGH-VALUE / LOW-VALUE follow it."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    first_region,
    run_cobol,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


def _if(condition: str, flag: str) -> list[str]:
    return [
        f"    IF {condition}",
        f"        MOVE 1 TO {flag}",
        "    ELSE",
        f"        MOVE 0 TO {flag}",
        "    END-IF.",
    ]


_CONDITIONS = [
    "F-1 < U-1",
    "U-1 < N-1",
    "I-1 = J-1",
    "F-1 = LOW-VALUE",
    'NEW-LOW = "F"',
    'MOVED = "FF"',
    "N-1 = HIGH-VALUE",
    "A-1 > Y-1",
]

_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. COLLSEQ.",
    "ENVIRONMENT DIVISION.",
    "CONFIGURATION SECTION.",
    "OBJECT-COMPUTER. TESTER",
    "    PROGRAM COLLATING SEQUENCE IS SEQ.",
    "SPECIAL-NAMES.",
    '    ALPHABET SEQ IS "F" "U" "N" ALSO HIGH-VALUE ALSO LOW-VALUE',
    '        "Y" "A" THRU "C" "I" ALSO "J".',
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-R.",
    *[f"   05 R{n} PIC 9 VALUE 9." for n in range(1, len(_CONDITIONS) + 1)],
    "01 HI-1 PIC X.",
    "01 NEW-LOW PIC X VALUE LOW-VALUE.",
    "01 MOVED PIC X(2).",
    *[f'01 {c}-1 PIC X VALUE "{c}".' for c in "FUNIJAY"],
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
    "    MOVE LOW-VALUE TO MOVED.",
    "    MOVE HIGH-VALUE TO HI-1.",
    *[
        line
        for n, condition in enumerate(_CONDITIONS, start=1)
        for line in _if(condition, f"R{n}")
    ],
    "    STOP RUN.",
]


class TestProgramCollatingSequence:
    @covers(
        CobolFeature.PROGRAM_COLLATING_SEQUENCE,
        CobolFeature.FIGURATIVE_LOW_VALUES,
        CobolFeature.FIGURATIVE_HIGH_VALUES,
    )
    def test_comparisons_and_high_and_low_value_follow_the_alphabet(self):
        """ANSI X3.23-1985 VI-4.5.4 and VI-6.15: nonnumeric comparisons use the
        program collating sequence; LOW-VALUE is its first character and
        HIGH-VALUE its last, here the highest native byte left unnamed."""
        region = first_region(run_cobol(_PROGRAM, max_steps=5000))
        assert (bytes(region[0:8]).decode("cp037"), region[8]) == ("11111101", 0xFE)


_NATIVE_CONDITIONS = ["LOWER-A < UPPER-A", "UPPER-A < DIGIT-1", "UPPER-Z < DIGIT-1"]

_NATIVE_PROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. NATIVESQ.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-R.",
    *[f"   05 R{n} PIC 9 VALUE 9." for n in range(1, len(_NATIVE_CONDITIONS) + 1)],
    '01 LOWER-A PIC X VALUE "a".',
    '01 UPPER-A PIC X VALUE "A".',
    '01 UPPER-Z PIC X VALUE "Z".',
    '01 DIGIT-1 PIC X VALUE "1".',
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
    *[
        line
        for n, condition in enumerate(_NATIVE_CONDITIONS, start=1)
        for line in _if(condition, f"R{n}")
    ],
    "    STOP RUN.",
]


class TestNativeCollatingSequence:
    @covers(CobolFeature.COMPARISON_OPERATORS)
    def test_without_the_clause_comparisons_follow_ebcdic(self):
        """IBM Enterprise COBOL: the native collating sequence is EBCDIC, where
        lowercase letters sort before uppercase and letters before digits."""
        region = first_region(run_cobol(_NATIVE_PROGRAM, max_steps=5000))
        assert bytes(region[0:3]).decode("cp037") == "111"
