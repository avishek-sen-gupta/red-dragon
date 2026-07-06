"""End-to-end feature showcase tests: each test exercises multiple COBOL features
working together through the full pipeline (source → ProLeap bridge → IR → CFG → VM).

Unlike the focused tests in test_cobol_programs.py (one feature per test), these
tests combine multiple features in a single program to verify they compose correctly.
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
    """Enforce the required PROLEAP_BRIDGE_JAR for run()/compile_directory-based
    tests (fails loudly via bridge_jar if it's unset)."""


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
        0x4B: ".",
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

    @covers(CobolFeature.UNSTRING_DELIMITED_BY)
    def test_unstring_multiple_delimiters_first_match_wins(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-UNSTRING-OR.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "A,B;C".',
                "77 WS-F1  PIC X(5) VALUE SPACES.",
                "77 WS-F2  PIC X(5) VALUE SPACES.",
                "77 WS-F3  PIC X(5) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    UNSTRING WS-SRC DELIMITED BY ',' OR ';'",
                "        INTO WS-F1 WS-F2 WS-F3.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 10, 5).strip() == "A"
        assert _decode_alpha(region, 15, 5).strip() == "B"
        assert _decode_alpha(region, 20, 5).strip() == "C"

    @covers(CobolFeature.UNSTRING_DELIMITED_BY)
    def test_unstring_single_delimiter_still_works(self):
        """Regression: single-delimiter UNSTRING (no OR) is unaffected."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-UNSTRING-SINGLE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "A,B,C".',
                "77 WS-F1  PIC X(5) VALUE SPACES.",
                "77 WS-F2  PIC X(5) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    UNSTRING WS-SRC DELIMITED BY ','",
                "        INTO WS-F1 WS-F2.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 10, 5).strip() == "A"
        assert _decode_alpha(region, 15, 5).strip() == "B"

    @covers(CobolFeature.UNSTRING_VERB)
    def test_unstring_tallying_in_counts_populated_fields(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-UNSTRING-TALLY.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "A,B,C".',
                "77 WS-F1  PIC X(5) VALUE SPACES.",
                "77 WS-F2  PIC X(5) VALUE SPACES.",
                "77 WS-F3  PIC X(5) VALUE SPACES.",
                "77 WS-CNT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    UNSTRING WS-SRC DELIMITED BY ','",
                "        INTO WS-F1 WS-F2 WS-F3",
                "        TALLYING IN WS-CNT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-SRC (X10) @0-9, WS-F1 @10-14, WS-F2 @15-19, WS-F3 @20-24, WS-CNT (9(4)) @25-28.
        assert _decode(region, 25, 4) == 3

    @covers(CobolFeature.UNSTRING_VERB)
    def test_unstring_tallying_in_accumulates_and_caps_at_into_count(self):
        """TALLYING IN adds to the counter's existing value (doesn't reset to
        zero), and counts fields actually populated — capped at len(INTO) —
        not the raw number of delimited substrings, when there are more
        substrings than INTO targets."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-UNSTRING-TALLY2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "A,B,C,D".',
                "77 WS-F1  PIC X(5) VALUE SPACES.",
                "77 WS-F2  PIC X(5) VALUE SPACES.",
                "77 WS-CNT PIC 9(4) VALUE 10.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    UNSTRING WS-SRC DELIMITED BY ','",
                "        INTO WS-F1 WS-F2",
                "        TALLYING IN WS-CNT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-SRC (X10) @0-9, WS-F1 @10-14, WS-F2 @15-19, WS-CNT (9(4)) @20-23.
        # "A,B,C,D" splits into 4 substrings but only 2 INTO targets exist, so
        # only 2 are "populated" -> tally adds 2, not 4. Starting value 10 ->
        # expect 12 (accumulate), NOT 2 (overwrite) and NOT 14 (uncapped raw count).
        assert _decode(region, 20, 4) == 12

    @covers(CobolFeature.UNSTRING_VERB)
    def test_unstring_without_tallying_in_still_works(self):
        """Regression: UNSTRING with no TALLYING IN clause is unaffected."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-UNSTRING-NOTALLY.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "A,B".',
                "77 WS-F1  PIC X(5) VALUE SPACES.",
                "77 WS-F2  PIC X(5) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    UNSTRING WS-SRC DELIMITED BY ',' INTO WS-F1 WS-F2.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-SRC (X10) @0-9, WS-F1 @10-14, WS-F2 @15-19.
        assert _decode_alpha(region, 10, 5).strip() == "A"
        assert _decode_alpha(region, 15, 5).strip() == "B"

    @covers(CobolFeature.STRING_VERB)
    def test_string_with_pointer_appends_across_two_statements(self):
        """Two STRING ... WITH POINTER calls append at the cursor, not overwrite."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-STRING-PTR.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-DST PIC X(10) VALUE SPACES.",
                "77 WS-PTR PIC 9(4) VALUE 1.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                '    STRING "AB" DELIMITED BY SIZE',
                "        INTO WS-DST WITH POINTER WS-PTR.",
                '    STRING "CD" DELIMITED BY SIZE',
                "        INTO WS-DST WITH POINTER WS-PTR.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 0, 10) == "ABCD      "
        assert _decode(region, 10, 4) == 5  # ptr started at 1, advanced by 4 -> 5

    @covers(CobolFeature.UNSTRING_VERB)
    def test_unstring_with_pointer_advances_past_consumed_delimiter(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-UNSTRING-PTR.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "A,B".',
                "77 WS-F1  PIC X(5) VALUE SPACES.",
                "77 WS-PTR PIC 9(4) VALUE 1.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    UNSTRING WS-SRC DELIMITED BY ','",
                "        INTO WS-F1 WITH POINTER WS-PTR.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-SRC (X10) @0-9, WS-F1 @10-14, WS-PTR (9(4)) @15-18.
        assert _decode_alpha(region, 10, 5).strip() == "A"
        assert _decode(region, 15, 4) == 3  # positioned just after the comma

    @covers(CobolFeature.UNSTRING_VERB)
    def test_unstring_with_pointer_resumes_scan_from_cursor_on_second_call(self):
        """Real WITH POINTER semantics: the SECOND UNSTRING call must scan
        starting at the cursor position left by the first, not re-scan from
        offset 0 (a bug a whole-branch review caught: the pointer was being
        advanced/written correctly but never actually used to offset where
        the scan itself began)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-UNSTRING-PTR3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "A,B,C".',
                "77 WS-F1  PIC X(5) VALUE SPACES.",
                "77 WS-F2  PIC X(5) VALUE SPACES.",
                "77 WS-PTR PIC 9(4) VALUE 1.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    UNSTRING WS-SRC DELIMITED BY ','",
                "        INTO WS-F1 WITH POINTER WS-PTR.",
                "    UNSTRING WS-SRC DELIMITED BY ','",
                "        INTO WS-F2 WITH POINTER WS-PTR.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-SRC (X10) @0-9, WS-F1 @10-14, WS-F2 @15-19, WS-PTR (9(4)) @20-23.
        # 1st call: ptr=1 -> scans "A,B,C" from offset 0 -> WS-F1="A", ptr
        # advances by len("A")+len(",")=2 -> 3.
        # 2nd call: ptr=3 -> MUST scan from offset 2 ("B,C"), not offset 0
        # again -> WS-F2="B" (not "A"), ptr advances by len("B")+len(",")=2 -> 5.
        assert _decode_alpha(region, 10, 5).strip() == "A"
        assert _decode_alpha(region, 15, 5).strip() == "B"
        assert _decode(region, 20, 4) == 5

    @covers(CobolFeature.UNSTRING_VERB)
    def test_unstring_with_pointer_advances_past_multi_char_delimiter(self):
        """Regression for the pre-dispatch fix: the cursor must advance past
        the delimiter's ACTUAL length, not an assumed 1 character."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-UNSTRING-PTR2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "A::B::C".',
                "77 WS-F1  PIC X(5) VALUE SPACES.",
                "77 WS-F2  PIC X(5) VALUE SPACES.",
                "77 WS-PTR PIC 9(4) VALUE 1.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    UNSTRING WS-SRC DELIMITED BY '::'",
                "        INTO WS-F1 WS-F2 WITH POINTER WS-PTR.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-SRC (X10) @0-9, WS-F1 @10-14, WS-F2 @15-19, WS-PTR (9(4)) @20-23.
        # "A::B::C": "A" (1) + "::" (2) + "B" (1) + "::" (2) consumed for 2
        # targets = 6 chars; ptr started at 1 -> expect 7, NOT 1+len("A")+
        # len("B")+2*1=5 (which is what a wrong 1-char-per-delimiter
        # assumption would produce).
        assert _decode_alpha(region, 10, 5).strip() == "A"
        assert _decode_alpha(region, 15, 5).strip() == "B"
        assert _decode(region, 20, 4) == 7

    @covers(CobolFeature.INSPECT_TALLYING)
    def test_inspect_tallying_multiple_independent_targets(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-INSPECT-MULTI.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "AAABB".',
                "77 WS-CNT-A PIC 9(4) VALUE 0.",
                "77 WS-CNT-B PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INSPECT WS-SRC TALLYING WS-CNT-A FOR ALL 'A'",
                "        WS-CNT-B FOR ALL 'B'.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode(region, 10, 4) == 3
        assert _decode(region, 14, 4) == 2

    @covers(CobolFeature.INSPECT_TALLYING)
    def test_inspect_tallying_three_targets_mixed_modes(self):
        """3 simultaneous counters, mixed ALL/LEADING modes (original bead's
        acceptance criterion #4 for red-dragon-4q25.17)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-INSPECT-MULTI3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "BBBAACCCC".',
                "77 WS-CNT-A PIC 9(4) VALUE 0.",
                "77 WS-CNT-B PIC 9(4) VALUE 0.",
                "77 WS-CNT-C PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INSPECT WS-SRC TALLYING WS-CNT-A FOR ALL 'A'",
                "        WS-CNT-B FOR LEADING 'B'",
                "        WS-CNT-C FOR ALL 'C'.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-SRC (X10) @0-9, WS-CNT-A @10-13, WS-CNT-B @14-17, WS-CNT-C @18-21.
        assert _decode(region, 10, 4) == 2  # ALL 'A' -> 2
        assert _decode(region, 14, 4) == 3  # LEADING 'B' -> "BBB" at start -> 3
        assert _decode(region, 18, 4) == 4  # ALL 'C' -> 4

    @covers(CobolFeature.INSPECT_TALLYING)
    def test_inspect_tallying_single_target_still_works(self):
        """Regression: single-target INSPECT TALLYING is unaffected."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-INSPECT-SINGLE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "ABCABC".',
                "77 WS-CNT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INSPECT WS-SRC TALLYING WS-CNT FOR ALL 'A'.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode(region, 10, 4) == 2

    @covers(CobolFeature.INSPECT_TALLYING)
    def test_inspect_tallying_before_initial_bounds_the_scan(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-INSPECT-BEFORE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "ABCABC.ABC".',
                "77 WS-CNT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INSPECT WS-SRC TALLYING WS-CNT FOR ALL 'A' BEFORE INITIAL '.'.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode(region, 10, 4) == 2

    @covers(CobolFeature.INSPECT_TALLYING)
    def test_inspect_tallying_after_initial_bounds_the_scan(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-INSPECT-AFTER.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "ABCABC.ABC".',
                "77 WS-CNT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INSPECT WS-SRC TALLYING WS-CNT FOR ALL 'A' AFTER INITIAL '.'.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode(region, 10, 4) == 1

    @covers(CobolFeature.INSPECT_REPLACING)
    def test_inspect_replacing_before_initial_bounds_the_scan(self):
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-INSPECT-REPL-BEFORE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "AA.AA     ".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INSPECT WS-SRC REPLACING ALL 'A' BY 'Z' BEFORE INITIAL '.'.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 0, 10) == "ZZ.AA     "

    @covers(CobolFeature.INSPECT_REPLACING)
    def test_inspect_replacing_after_initial_bounds_the_scan(self):
        """The AFTER-boundary splice order (remainder + replaced_bounded) had
        no dedicated e2e coverage; only hand-traced during review."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-INSPECT-REPL-AFTER.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "AA.AA     ".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INSPECT WS-SRC REPLACING ALL 'A' BY 'Z' AFTER INITIAL '.'.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 0, 10) == "AA.ZZ     "

    @covers(CobolFeature.INSPECT_TALLYING)
    def test_inspect_tallying_without_before_after_still_works(self):
        """Regression: INSPECT TALLYING with no BEFORE/AFTER is unaffected."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. E2E-INSPECT-NOBOUND.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-SRC PIC X(10) VALUE "ABCABC".',
                "77 WS-CNT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INSPECT WS-SRC TALLYING WS-CNT FOR ALL 'A'.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode(region, 10, 4) == 2


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


# ── EVALUATE with ALSO (red-dragon-vbm4) ─────────────────────────────────────
#
# Layout for all tests:
#   77 WS-A    PIC 9  offset=0
#   77 WS-B    PIC 9  offset=1
#   77 RESULT  PIC 9  offset=2


class TestEvaluateAlso:
    """EVALUATE subject ALSO subject WHEN val ALSO val END-EVALUATE."""

    def _pgm(self, a: int, b: int, branches: list[str]) -> list[str]:
        return [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. EVALSO.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            f"77 WS-A    PIC 9 VALUE {a}.",
            f"77 WS-B    PIC 9 VALUE {b}.",
            "77 RESULT  PIC 9 VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN.",
            "    EVALUATE WS-A ALSO WS-B",
            *branches,
            "    END-EVALUATE.",
            "    STOP RUN.",
        ]

    @covers(CobolFeature.EVALUATE)
    def test_both_subjects_match_executes_branch(self):
        """WS-A=2, WS-B=3: WHEN 2 ALSO 3 matches → RESULT=1."""
        vm = _run_cobol(
            self._pgm(
                2,
                3,
                [
                    "        WHEN 2 ALSO 3",
                    "            MOVE 1 TO RESULT",
                    "        WHEN OTHER",
                    "            MOVE 9 TO RESULT",
                ],
            )
        )
        assert _decode(_first_region(vm), 2, 1) == 1

    @covers(CobolFeature.EVALUATE)
    def test_second_subject_mismatch_falls_to_when_other(self):
        """WS-A=2, WS-B=5: WHEN 2 ALSO 3 does NOT match (WS-B≠3) → WHEN OTHER → RESULT=9."""
        vm = _run_cobol(
            self._pgm(
                2,
                5,
                [
                    "        WHEN 2 ALSO 3",
                    "            MOVE 1 TO RESULT",
                    "        WHEN OTHER",
                    "            MOVE 9 TO RESULT",
                ],
            )
        )
        assert _decode(_first_region(vm), 2, 1) == 9

    @covers(CobolFeature.EVALUATE)
    def test_first_subject_mismatch_falls_to_when_other(self):
        """WS-A=7, WS-B=3: WHEN 2 ALSO 3 does NOT match (WS-A≠2) → WHEN OTHER → RESULT=9."""
        vm = _run_cobol(
            self._pgm(
                7,
                3,
                [
                    "        WHEN 2 ALSO 3",
                    "            MOVE 1 TO RESULT",
                    "        WHEN OTHER",
                    "            MOVE 9 TO RESULT",
                ],
            )
        )
        assert _decode(_first_region(vm), 2, 1) == 9

    @covers(CobolFeature.EVALUATE)
    def test_also_any_skips_that_subject(self):
        """WHEN 2 ALSO ANY: second subject is irrelevant → matches whenever WS-A=2."""
        vm = _run_cobol(
            self._pgm(
                2,
                7,
                [
                    "        WHEN 2 ALSO ANY",
                    "            MOVE 1 TO RESULT",
                    "        WHEN OTHER",
                    "            MOVE 9 TO RESULT",
                ],
            )
        )
        assert _decode(_first_region(vm), 2, 1) == 1

    @covers(CobolFeature.EVALUATE)
    def test_single_subject_when_any_always_matches(self):
        """EVALUATE WS-A WHEN ANY: primary WHEN ANY must match regardless of WS-A's value.

        red-dragon-9j01: WHEN ANY on the primary subject is a wildcard per the
        COBOL spec, but was silently treated as a literal comparison against a
        field named ANY, so the branch never fired.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. EVALANY.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A    PIC 9 VALUE 7.",
                "77 RESULT  PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN.",
                "    EVALUATE WS-A",
                "        WHEN ANY",
                "            MOVE 1 TO RESULT",
                "        WHEN OTHER",
                "            MOVE 9 TO RESULT",
                "    END-EVALUATE.",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 1, 1) == 1

    @covers(CobolFeature.EVALUATE)
    def test_evaluate_true_when_any_matches_as_catch_all(self):
        """EVALUATE TRUE WHEN ANY: primary WHEN ANY under EVALUATE TRUE always matches."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. EVALTRUEANY.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A    PIC 9 VALUE 3.",
                "77 RESULT  PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN.",
                "    EVALUATE TRUE",
                "        WHEN WS-A = 9",
                "            MOVE 2 TO RESULT",
                "        WHEN ANY",
                "            MOVE 1 TO RESULT",
                "    END-EVALUATE.",
                "    STOP RUN.",
            ]
        )
        assert _decode(_first_region(vm), 1, 1) == 1


class TestAddCorresponding:
    """ADD/SUBTRACT CORRESPONDING — only matching direct children are operated on."""

    _WS = [
        "       WORKING-STORAGE SECTION.",
        "       01 WS-GROUP-A.",
        "           05 GA-X PIC 99.",
        "           05 GA-Y PIC 99.",
        "           05 GA-ONLY PIC 99.",
        "       01 WS-GROUP-B.",
        "           05 GA-X PIC 99.",
        "           05 GA-Y PIC 99.",
        "           05 GB-ONLY PIC 99.",
    ]
    # Layout (all zoned-decimal, 2 bytes each):
    #   WS-GROUP-A: GA-X@0, GA-Y@2, GA-ONLY@4  (6 bytes)
    #   WS-GROUP-B: GA-X@6, GA-Y@8, GB-ONLY@10 (6 bytes)

    def _pgm(self, ax: int, ay: int, bx: int, by: int, corr_stmt: str) -> list[str]:
        return [
            "       IDENTIFICATION DIVISION.",
            "       PROGRAM-ID. CORR-TEST.",
            "       DATA DIVISION.",
            *self._WS,
            "       PROCEDURE DIVISION.",
            f"           MOVE {ax} TO GA-X IN WS-GROUP-A.",
            f"           MOVE {ay} TO GA-Y IN WS-GROUP-A.",
            f"           MOVE {bx} TO GA-X IN WS-GROUP-B.",
            f"           MOVE {by} TO GA-Y IN WS-GROUP-B.",
            f"           {corr_stmt}",
            "           STOP RUN.",
        ]

    @covers(CobolFeature.ADD)
    def test_add_corresponding_matching_fields(self):
        """ADD CORRESPONDING adds GA-X(A→B) and GA-Y(A→B); GA-ONLY and GB-ONLY untouched."""
        vm = _run_cobol(
            self._pgm(10, 20, 3, 4, "ADD CORRESPONDING WS-GROUP-A TO WS-GROUP-B.")
        )
        region = _first_region(vm)
        assert _decode(region, 6, 2) == 13  # GA-X in WS-GROUP-B: 3+10=13
        assert _decode(region, 8, 2) == 24  # GA-Y in WS-GROUP-B: 4+20=24

    @covers(CobolFeature.SUBTRACT)
    def test_subtract_corresponding_matching_fields(self):
        """SUBTRACT CORRESPONDING subtracts GA-X(A) from GA-X(B) and GA-Y(A) from GA-Y(B)."""
        vm = _run_cobol(
            self._pgm(
                3, 4, 10, 20, "SUBTRACT CORRESPONDING WS-GROUP-A FROM WS-GROUP-B."
            )
        )
        region = _first_region(vm)
        assert _decode(region, 6, 2) == 7  # GA-X in WS-GROUP-B: 10-3=7
        assert _decode(region, 8, 2) == 16  # GA-Y in WS-GROUP-B: 20-4=16
