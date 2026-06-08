"""End-to-end feature showcase tests: each test exercises multiple COBOL features
working together through the full pipeline (source → ProLeap bridge → IR → CFG → VM).

Unlike the focused tests in test_cobol_programs.py (one feature per test), these
tests combine multiple features in a single program to verify they compose correctly.
"""

import os

import pytest

from interpreter.address import Address
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    JAR_PATH,
    JAR_AVAILABLE,
    decode_zoned_unsigned as _decode,
    first_region as _first_region,
    run_cobol,
)

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)


@pytest.fixture(autouse=True, scope="session")
def _set_bridge_jar_env():
    """Ensure PROLEAP_BRIDGE_JAR is set for the entire test session."""
    old = os.environ.get("PROLEAP_BRIDGE_JAR")
    os.environ["PROLEAP_BRIDGE_JAR"] = JAR_PATH
    yield
    if old is None:
        os.environ.pop("PROLEAP_BRIDGE_JAR", None)
    else:
        os.environ["PROLEAP_BRIDGE_JAR"] = old


# ── Helpers ──────────────────────────────────────────────────────


def _run_cobol(lines: list[str], max_steps: int = 20000):
    """Run COBOL source through the full pipeline, return VMState.

    These multi-feature programs need a higher default step budget than the
    shared ``run_cobol`` default, so this thin wrapper preserves it.
    """
    return run_cobol(lines, max_steps=max_steps)


def _decode_alpha(region, offset: int, length: int) -> str:
    """Decode EBCDIC alphanumeric bytes to ASCII string."""
    ebcdic_to_ascii = {
        0x40: " ",
        0xC1: "A",
        0xC2: "B",
        0xC3: "C",
        0xC4: "D",
        0xC5: "E",
        0xC6: "F",
        0xC7: "G",
        0xC8: "H",
        0xC9: "I",
        0xD1: "J",
        0xD2: "K",
        0xD3: "L",
        0xD4: "M",
        0xD5: "N",
        0xD6: "O",
        0xD7: "P",
        0xD8: "Q",
        0xD9: "R",
        0xE2: "S",
        0xE3: "T",
        0xE4: "U",
        0xE5: "V",
        0xE6: "W",
        0xE7: "X",
        0xE8: "Y",
        0xE9: "Z",
        0xF0: "0",
        0xF1: "1",
        0xF2: "2",
        0xF3: "3",
        0xF4: "4",
        0xF5: "5",
        0xF6: "6",
        0xF7: "7",
        0xF8: "8",
        0xF9: "9",
    }
    return "".join(ebcdic_to_ascii.get(region[offset + i], "?") for i in range(length))


# ── E2E Feature Tests ───────────────────────────────────────────


class TestAllArithmeticForms:
    """Combines in-place ADD/SUBTRACT, all four GIVING forms, and COMPUTE
    in a single program with cross-paragraph PERFORM."""

    @covers(
        CobolFeature.ADD,
        CobolFeature.SUBTRACT,
        CobolFeature.MULTIPLY,
        CobolFeature.DIVIDE,
        CobolFeature.COMPUTE,
        CobolFeature.GIVING_CLAUSE,
        CobolFeature.PERFORM,
    )
    def test_arithmetic_all_forms(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-ARITH.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A     PIC 9(4) VALUE 10.",
                "77 WS-B     PIC 9(4) VALUE 25.",
                "77 WS-C     PIC 9(4) VALUE 3.",
                "77 WS-SUM   PIC 9(4) VALUE 0.",
                "77 WS-PROD  PIC 9(4) VALUE 0.",
                "77 WS-QUOT  PIC 9(4) VALUE 0.",
                "77 WS-ADDG  PIC 9(4) VALUE 0.",
                "77 WS-SUBG  PIC 9(4) VALUE 0.",
                "77 WS-COMP  PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM CALC-PARA.",
                "    STOP RUN.",
                "",
                "CALC-PARA.",
                "* In-place ADD and SUBTRACT",
                "    ADD WS-A TO WS-SUM.",
                "    ADD WS-B TO WS-SUM.",
                "    SUBTRACT WS-C FROM WS-SUM.",
                "* ADD / SUBTRACT GIVING",
                "    ADD WS-A TO WS-B GIVING WS-ADDG.",
                "    SUBTRACT WS-C FROM WS-B GIVING WS-SUBG.",
                "* MULTIPLY / DIVIDE GIVING",
                "    MULTIPLY WS-A BY WS-C GIVING WS-PROD.",
                "    DIVIDE WS-B BY WS-A GIVING WS-QUOT.",
                "* COMPUTE with expression",
                "    COMPUTE WS-COMP = WS-A + WS-B * WS-C.",
            ]
        )
        region = _first_region(vm)

        # Inputs unchanged
        assert _decode(region, 0, 4) == 10  # WS-A
        assert _decode(region, 4, 4) == 25  # WS-B
        assert _decode(region, 8, 4) == 3  # WS-C

        # In-place: 10 + 25 - 3 = 32
        assert _decode(region, 12, 4) == 32  # WS-SUM

        # MULTIPLY 10 BY 3 GIVING = 30
        assert _decode(region, 16, 4) == 30  # WS-PROD

        # DIVIDE 25 BY 10 GIVING = 2
        assert _decode(region, 20, 4) == 2  # WS-QUOT

        # ADD 10 TO 25 GIVING = 35
        assert _decode(region, 24, 4) == 35  # WS-ADDG

        # SUBTRACT 3 FROM 25 GIVING = 22
        assert _decode(region, 28, 4) == 22  # WS-SUBG

        # COMPUTE 10 + 25*3 = 85
        assert _decode(region, 32, 4) == 85  # WS-COMP


class TestControlFlowComposition:
    """IF/ELSE, EVALUATE/WHEN, three PERFORM forms, all in one program."""

    @covers(
        CobolFeature.IF_ELSE,
        CobolFeature.EVALUATE,
        CobolFeature.EVALUATE_WHEN_OTHER,
        CobolFeature.PERFORM,
        CobolFeature.PERFORM_TIMES,
        CobolFeature.PERFORM_UNTIL,
        CobolFeature.PERFORM_VARYING,
        CobolFeature.ADD,
    )
    def test_control_flow_all_forms(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-CTLFLOW.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-X     PIC 9(4) VALUE 15.",
                "77 WS-IF-R  PIC 9(4) VALUE 0.",
                "77 WS-CODE  PIC 9(4) VALUE 2.",
                "77 WS-EV-R  PIC 9(4) VALUE 0.",
                "77 WS-CTR   PIC 9(4) VALUE 0.",
                "77 WS-SUM   PIC 9(4) VALUE 0.",
                "77 WS-I     PIC 9(4) VALUE 0.",
                "77 WS-ACC   PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "* IF / ELSE",
                "    IF WS-X > 10",
                "        MOVE 1 TO WS-IF-R",
                "    ELSE",
                "        MOVE 2 TO WS-IF-R",
                "    END-IF.",
                "* EVALUATE / WHEN",
                "    EVALUATE WS-CODE",
                "        WHEN 1",
                "            MOVE 10 TO WS-EV-R",
                "        WHEN 2",
                "            MOVE 20 TO WS-EV-R",
                "        WHEN OTHER",
                "            MOVE 99 TO WS-EV-R",
                "    END-EVALUATE.",
                "* PERFORM TIMES",
                "    PERFORM 3 TIMES",
                "        ADD 1 TO WS-CTR",
                "    END-PERFORM.",
                "* PERFORM UNTIL",
                "    PERFORM UNTIL WS-SUM > 20",
                "        ADD 7 TO WS-SUM",
                "    END-PERFORM.",
                "* PERFORM VARYING",
                "    PERFORM VARYING WS-I FROM 1 BY 1",
                "        UNTIL WS-I > 5",
                "        ADD WS-I TO WS-ACC",
                "    END-PERFORM.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)

        assert _decode(region, 0, 4) == 15  # WS-X unchanged
        assert _decode(region, 4, 4) == 1  # IF 15>10 -> true -> 1
        assert _decode(region, 8, 4) == 2  # WS-CODE unchanged
        assert _decode(region, 12, 4) == 20  # EVALUATE 2 -> WHEN 2 -> 20
        assert _decode(region, 16, 4) == 3  # PERFORM 3 TIMES -> 3
        assert _decode(region, 20, 4) == 21  # UNTIL > 20: 7+7+7=21
        assert _decode(region, 24, 4) == 6  # VARYING counter exits at 6
        assert _decode(region, 28, 4) == 15  # VARYING 1+2+3+4+5 = 15


class TestStringOperations:
    """STRING, UNSTRING, INSPECT TALLYING, and INSPECT REPLACING together."""

    @covers(
        CobolFeature.STRING_VERB,
        CobolFeature.STRING_DELIMITED_BY,
        CobolFeature.UNSTRING_VERB,
        CobolFeature.UNSTRING_DELIMITED_BY,
        CobolFeature.INSPECT_TALLYING,
        CobolFeature.INSPECT_REPLACING,
    )
    def test_string_ops_combined(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-STRING.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-FIRST PIC X(5) VALUE "HELLO".',
                '77 WS-LAST  PIC X(5) VALUE "WORLD".',
                "77 WS-JOINED PIC X(10) VALUE SPACES.",
                '77 WS-FULL  PIC X(11) VALUE "ALPHA BRAVO".',
                "77 WS-PART1 PIC X(5) VALUE SPACES.",
                "77 WS-PART2 PIC X(5) VALUE SPACES.",
                '77 WS-DATA  PIC X(10) VALUE "ABCABCABCA".',
                "77 WS-COUNT PIC 9(4) VALUE 0.",
                '77 WS-REPL  PIC X(5) VALUE "AABAA".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "* STRING concatenation",
                "    STRING WS-FIRST DELIMITED BY SIZE",
                "           WS-LAST  DELIMITED BY SIZE",
                "           INTO WS-JOINED.",
                "* UNSTRING splitting",
                "    UNSTRING WS-FULL DELIMITED BY SPACES",
                "        INTO WS-PART1 WS-PART2.",
                "* INSPECT TALLYING",
                "    INSPECT WS-DATA TALLYING WS-COUNT",
                '        FOR ALL "A".',
                "* INSPECT REPLACING",
                '    INSPECT WS-REPL REPLACING ALL "A" BY "Z".',
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)

        # STRING: HELLO + WORLD -> HELLOWORLD
        assert _decode_alpha(region, 10, 10) == "HELLOWORLD"

        # UNSTRING: "ALPHA BRAVO" -> "ALPHA", "BRAVO"
        assert _decode_alpha(region, 31, 5) == "ALPHA"
        assert _decode_alpha(region, 36, 5) == "BRAVO"

        # INSPECT TALLYING: 4 occurrences of "A" in "ABCABCABCA"
        assert _decode(region, 51, 4) == 4

        # INSPECT REPLACING: "AABAA" -> "ZZBZZ"
        assert _decode_alpha(region, 55, 5) == "ZZBZZ"


class TestLevel88ConditionNames:
    """Single-value, THRU range, and multi-value level-88 conditions in one program."""

    @covers(
        CobolFeature.LEVEL_88_CONDITION,
        CobolFeature.VALUE_THRU_RANGE,
        CobolFeature.CONDITION_VALUES_THRU,
        CobolFeature.IF_ELSE,
    )
    def test_level88_all_forms(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-LVL88.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '05 WS-STATUS PIC X(1) VALUE "A".',
                '   88 STATUS-ACTIVE VALUE "A".',
                '   88 STATUS-INACTIVE VALUE "I".',
                "05 WS-SCORE  PIC 9(4) VALUE 35.",
                "   88 IN-RANGE VALUE 10 THRU 50.",
                '05 WS-LETTER PIC X(1) VALUE "B".',
                '   88 IS-VOWEL VALUE "A" "E" "I" "O" "U".',
                "77 WS-R1 PIC 9(4) VALUE 0.",
                "77 WS-R2 PIC 9(4) VALUE 0.",
                "77 WS-R3 PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "* Single-value condition",
                "    IF STATUS-ACTIVE",
                "        MOVE 1 TO WS-R1",
                "    ELSE",
                "        MOVE 2 TO WS-R1",
                "    END-IF.",
                "* THRU range condition",
                "    IF IN-RANGE",
                "        MOVE 1 TO WS-R2",
                "    ELSE",
                "        MOVE 2 TO WS-R2",
                "    END-IF.",
                '* Multi-value condition ("B" is not a vowel)',
                "    IF IS-VOWEL",
                "        MOVE 1 TO WS-R3",
                "    ELSE",
                "        MOVE 2 TO WS-R3",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)

        # STATUS-ACTIVE? A=A -> true -> 1
        assert _decode(region, 6, 4) == 1  # WS-R1

        # IN-RANGE 10..50? 35 in range -> true -> 1
        assert _decode(region, 10, 4) == 1  # WS-R2

        # IS-VOWEL? B not in AEIOU -> false -> 2
        assert _decode(region, 14, 4) == 2  # WS-R3


class TestLevel88FigurativeValues:
    """A level-88 whose VALUES are figurative constants (LOW-VALUES / SPACES):
    SET <88> TO TRUE writes the first figurative, and IF <88> must compare the
    field against the figurative *fill character*, not the literal text
    'LOW-VALUES'. (CardDemo COACTUPC ACUP-DETAILS-NOT-FETCHED regression.)"""

    @covers(CobolFeature.LEVEL_88_CONDITION, CobolFeature.SET_TO, CobolFeature.IF_ELSE)
    def test_set_and_test_88_figurative_low_values(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-LVL88-FIG.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "05 WS-FLAG PIC X(1) VALUE SPACE.",
                "   88 FLAG-UNSET VALUE LOW-VALUES SPACES.",
                "   88 FLAG-SET   VALUE 'S'.",
                "77 WS-R1 PIC 9(4) VALUE 0.",
                "77 WS-R2 PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "* SET the 88 to its first figurative VALUE (LOW-VALUES)",
                "    SET FLAG-UNSET TO TRUE.",
                "* IF must match the figurative LOW-VALUES, not the text",
                "    IF FLAG-UNSET",
                "        MOVE 1 TO WS-R1",
                "    ELSE",
                "        MOVE 2 TO WS-R1",
                "    END-IF.",
                "* Now flip to FLAG-SET and re-test FLAG-UNSET (should be false)",
                "    SET FLAG-SET TO TRUE.",
                "    IF FLAG-UNSET",
                "        MOVE 1 TO WS-R2",
                "    ELSE",
                "        MOVE 2 TO WS-R2",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # FLAG-UNSET after SET LOW-VALUES -> true -> 1
        assert _decode(region, 1, 4) == 1  # WS-R1
        # After SET FLAG-SET ('S'), FLAG-UNSET is false -> 2
        assert _decode(region, 5, 4) == 2  # WS-R2


class TestPerformAndParagraphs:
    """Multi-paragraph PERFORM calls with VARYING using field-based limit."""

    @covers(CobolFeature.PERFORM, CobolFeature.PERFORM_VARYING, CobolFeature.ADD)
    def test_perform_paragraph_composition(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-PERF.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A   PIC 9(4) VALUE 0.",
                "77 WS-B   PIC 9(4) VALUE 0.",
                "77 WS-C   PIC 9(4) VALUE 0.",
                "77 WS-I   PIC 9(4) VALUE 0.",
                "77 WS-ACC PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM INIT-PARA.",
                "    PERFORM CALC-PARA.",
                "    PERFORM LOOP-PARA.",
                "    STOP RUN.",
                "",
                "INIT-PARA.",
                "    MOVE 10 TO WS-A.",
                "    MOVE 20 TO WS-B.",
                "",
                "CALC-PARA.",
                "    ADD WS-A TO WS-B GIVING WS-C.",
                "",
                "LOOP-PARA.",
                "    PERFORM VARYING WS-I FROM 1 BY 1",
                "        UNTIL WS-I > WS-A",
                "        ADD 1 TO WS-ACC",
                "    END-PERFORM.",
            ],
            max_steps=50000,
        )
        region = _first_region(vm)

        assert _decode(region, 0, 4) == 10  # WS-A from INIT-PARA
        assert _decode(region, 4, 4) == 20  # WS-B from INIT-PARA
        assert _decode(region, 8, 4) == 30  # WS-C = ADD 10 TO 20 GIVING
        assert _decode(region, 12, 4) == 11  # WS-I exits at 11
        assert _decode(region, 16, 4) == 10  # WS-ACC = 10 iterations


class TestOccursWithSubscripts:
    """OCCURS table filled by PERFORM VARYING, read back with literal and field subscripts."""

    @covers(
        CobolFeature.OCCURS_FIXED,
        CobolFeature.PERFORM,
        CobolFeature.PERFORM_VARYING,
        CobolFeature.SUBSCRIPT_ACCESS,
        CobolFeature.MULTIPLY,
        CobolFeature.ADD,
    )
    def test_occurs_fill_and_read(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-OCCURS.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-TBL PIC 9(4) OCCURS 5.",
                "77 WS-IDX PIC 9(4) VALUE 3.",
                "77 WS-SUM PIC 9(4) VALUE 0.",
                "77 WS-I   PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "* Fill table: TBL(i) = i * 10",
                "    PERFORM VARYING WS-I FROM 1 BY 1",
                "        UNTIL WS-I > 5",
                "        MULTIPLY WS-I BY 10 GIVING WS-TBL(WS-I)",
                "    END-PERFORM.",
                "* Sum TBL(1) + TBL(WS-IDX=3) + TBL(5)",
                "    ADD WS-TBL(1) TO WS-SUM.",
                "    ADD WS-TBL(WS-IDX) TO WS-SUM.",
                "    ADD WS-TBL(5) TO WS-SUM.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)

        # Table contents: 10, 20, 30, 40, 50
        assert _decode(region, 0, 4) == 10  # TBL(1)
        assert _decode(region, 4, 4) == 20  # TBL(2)
        assert _decode(region, 8, 4) == 30  # TBL(3)
        assert _decode(region, 12, 4) == 40  # TBL(4)
        assert _decode(region, 16, 4) == 50  # TBL(5)

        assert _decode(region, 20, 4) == 3  # WS-IDX unchanged
        # SUM = TBL(1) + TBL(3) + TBL(5) = 10 + 30 + 50 = 90
        assert _decode(region, 24, 4) == 90  # WS-SUM
        assert _decode(region, 28, 4) == 6  # WS-I loop counter final


class TestBlankWhenZeroComposition:
    """BLANK WHEN ZERO with VALUE clauses and runtime MOVE 0."""

    @covers(CobolFeature.BLANK_WHEN_ZERO, CobolFeature.MOVE)
    def test_blank_when_zero_mixed(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-BWZ.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-AMT1 PIC 9(4) BLANK WHEN ZERO VALUE 0.",
                "77 WS-AMT2 PIC 9(4) BLANK WHEN ZERO VALUE 42.",
                "77 WS-AMT3 PIC 9(4) BLANK WHEN ZERO VALUE 99.",
                "77 WS-NORM PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 0 TO WS-AMT3.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)

        # WS-AMT1: BWZ + VALUE 0 -> all EBCDIC spaces (0x40)
        assert list(region[0:4]) == [0x40, 0x40, 0x40, 0x40]

        # WS-AMT2: BWZ + VALUE 42 -> normal zoned decimal
        assert _decode(region, 4, 4) == 42

        # WS-AMT3: BWZ + MOVE 0 at runtime -> all EBCDIC spaces
        assert list(region[8:12]) == [0x40, 0x40, 0x40, 0x40]

        # WS-NORM: no BWZ + VALUE 0 -> normal zoned zeros (0xF0)
        assert list(region[12:16]) == [0xF0, 0xF0, 0xF0, 0xF0]

    @covers(CobolFeature.BLANK_WHEN_ZERO, CobolFeature.MOVE)
    def test_blank_when_zero_blanked_field_reads_back_as_zero(self):
        """AC3: a blanked field (spaces in memory) MOVEd to a non-BWZ field transfers as 0."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-BWZ-AC3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-BLANK PIC 9(4) BLANK WHEN ZERO VALUE 0.",
                "77 WS-DEST  PIC 9(4) VALUE 99.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-BLANK TO WS-DEST.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-BLANK occupies bytes 0-3: EBCDIC spaces (blanked)
        assert list(region[0:4]) == [0x40, 0x40, 0x40, 0x40]
        # WS-DEST occupies bytes 4-7: MOVE from blanked field must transfer 0 as
        # normal zoned zeros (0xF0), not as spaces — WS-DEST has no BWZ clause
        assert list(region[4:8]) == [0xF0, 0xF0, 0xF0, 0xF0]

    @covers(CobolFeature.BLANK_WHEN_ZERO, CobolFeature.SUBTRACT)
    def test_blank_when_zero_arithmetic_result_zero_blanks_field(self):
        """AC4: a BWZ field whose value reaches zero via arithmetic is stored as spaces."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-BWZ-AC4.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-AMT PIC 9(4) BLANK WHEN ZERO VALUE 42.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SUBTRACT 42 FROM WS-AMT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # After SUBTRACT 42 FROM 42, result is 0 — BWZ must produce EBCDIC spaces
        assert list(region[0:4]) == [0x40, 0x40, 0x40, 0x40]


class TestLogicalOperators:
    """AND / OR / NOT in IF conditions."""

    @covers(CobolFeature.LOGICAL_AND)
    def test_logical_and_both_true(self):
        """IF A > 0 AND B > 0: both true → result field set to 1."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-AND.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A      PIC 9(4) VALUE 5.",
                "77 WS-B      PIC 9(4) VALUE 3.",
                "77 WS-RESULT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-A > 0 AND WS-B > 0",
                "        MOVE 1 TO WS-RESULT",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode(region, 8, 4) == 1

    @covers(CobolFeature.LOGICAL_AND)
    def test_logical_and_one_false(self):
        """IF A > 0 AND B > 10: B fails → result stays 0."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-AND2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A      PIC 9(4) VALUE 5.",
                "77 WS-B      PIC 9(4) VALUE 3.",
                "77 WS-RESULT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-A > 0 AND WS-B > 10",
                "        MOVE 1 TO WS-RESULT",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode(region, 8, 4) == 0

    @covers(CobolFeature.LOGICAL_OR)
    def test_logical_or_one_true(self):
        """IF A > 10 OR B > 0: B is true → result set to 1."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-OR.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A      PIC 9(4) VALUE 5.",
                "77 WS-B      PIC 9(4) VALUE 3.",
                "77 WS-RESULT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-A > 10 OR WS-B > 0",
                "        MOVE 1 TO WS-RESULT",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode(region, 8, 4) == 1

    @covers(CobolFeature.LOGICAL_OR)
    def test_logical_or_both_false(self):
        """IF A > 10 OR B > 10: both false → result stays 0."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-OR2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A      PIC 9(4) VALUE 5.",
                "77 WS-B      PIC 9(4) VALUE 3.",
                "77 WS-RESULT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-A > 10 OR WS-B > 10",
                "        MOVE 1 TO WS-RESULT",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode(region, 8, 4) == 0

    @covers(CobolFeature.LOGICAL_NOT)
    def test_logical_not_true_condition(self):
        """IF NOT WS-A > 10: WS-A=5 so A>10 is false → NOT makes it true → result=1."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-NOT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A      PIC 9(4) VALUE 5.",
                "77 WS-RESULT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF NOT WS-A > 10",
                "        MOVE 1 TO WS-RESULT",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode(region, 4, 4) == 1

    @covers(CobolFeature.LOGICAL_NOT)
    def test_logical_not_false_condition(self):
        """IF NOT WS-A > 0: WS-A=5 so A>0 is true → NOT makes it false → result stays 0."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-NOT2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A      PIC 9(4) VALUE 5.",
                "77 WS-RESULT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF NOT WS-A > 0",
                "        MOVE 1 TO WS-RESULT",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode(region, 4, 4) == 0
