"""Integration tests for COBOL programs: real .cbl source → ProLeap bridge → IR → CFG → VM.

These tests exercise the full pipeline starting from actual COBOL source code,
going through the ProLeap Java bridge parser, ASG construction, IR lowering,
CFG building, and VM execution. They verify decoded numeric values in memory regions.

Requires the ProLeap bridge JAR to be available (set PROLEAP_BRIDGE_JAR env var
or have it at the default path). Tests skip gracefully when the JAR is absent.
"""

import os

import pytest

from interpreter.run import run

_JAR_PATH = os.environ.get(
    "PROLEAP_BRIDGE_JAR",
    os.path.expanduser(
        "~/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
    ),
)
_JAR_AVAILABLE = os.path.isfile(_JAR_PATH)

pytestmark = pytest.mark.skipif(
    not _JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)


@pytest.fixture(autouse=True, scope="session")
def _set_bridge_jar_env():
    """Ensure PROLEAP_BRIDGE_JAR is set for the entire test session."""
    old = os.environ.get("PROLEAP_BRIDGE_JAR")
    os.environ["PROLEAP_BRIDGE_JAR"] = _JAR_PATH
    yield
    if old is None:
        os.environ.pop("PROLEAP_BRIDGE_JAR", None)
    else:
        os.environ["PROLEAP_BRIDGE_JAR"] = old


def _decode_zoned_unsigned(region: list[int], offset: int, length: int) -> int:
    """Decode unsigned zoned decimal from a memory region.

    Each byte is EBCDIC zoned: 0xF0=0, 0xF1=1, ..., 0xF9=9.
    The digit is in the low nibble (b & 0x0F).
    """
    digits = [region[offset + i] & 0x0F for i in range(length)]
    return sum(d * (10 ** (length - 1 - i)) for i, d in enumerate(digits))


def _to_fixed(lines: list[str]) -> str:
    """Convert short-form COBOL lines to FIXED format (columns 1-80).

    Each input line is treated as starting at column 8 (Area A).
    6 spaces for sequence area + 1 space for indicator area are prepended.
    """
    prefix = "       "  # 7 spaces: cols 1-6 (seq) + col 7 (indicator)
    return "\n".join(prefix + line for line in lines) + "\n"


def _run_cobol(lines: list[str], max_steps: int = 500):
    """Run a COBOL program through the full pipeline and return VMState."""
    source = _to_fixed(lines)
    return run(source=source, language="cobol", max_steps=max_steps)


def _first_region(vm):
    """Return the first memory region from the VM state."""
    return vm.regions[list(vm.regions.keys())[0]]


# ---------------------------------------------------------------------------
# Test programs
# ---------------------------------------------------------------------------


class TestInitialValues:
    def test_initial_values(self):
        """DATA DIVISION VALUE clauses initialise fields correctly."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-INIT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 10.",
                "77 WS-B PIC 9(4) VALUE 5.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 10
        assert _decode_zoned_unsigned(region, 4, 4) == 5


class TestAddSubtract:
    def test_add_subtract(self):
        """ADD and SUBTRACT produce correct results."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ADDSUB.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 10.",
                "77 WS-B PIC 9(4) VALUE 5.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD WS-A TO WS-R.",
                "    ADD WS-B TO WS-R.",
                "    SUBTRACT 3 FROM WS-R.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 8, 4) == 12


class TestMultiplyDivide:
    def test_multiply_divide(self):
        """MULTIPLY ... GIVING and DIVIDE ... GIVING produce correct results."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-MULDIV.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 10.",
                "77 WS-B PIC 9(4) VALUE 5.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "77 WS-Q PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MULTIPLY WS-A BY 3 GIVING WS-R.",
                "    DIVIDE WS-R BY WS-B GIVING WS-Q.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-R = 10 * 3 = 30
        assert _decode_zoned_unsigned(region, 8, 4) == 30
        # WS-Q = 30 / 5 = 6
        assert _decode_zoned_unsigned(region, 12, 4) == 6


class TestComputeExpression:
    def test_compute_expression(self):
        """COMPUTE with arithmetic expression."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMPUTE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 10.",
                "77 WS-B PIC 9(4) VALUE 5.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-R = WS-A + WS-B * 2.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 8, 4) == 20


class TestMoveLiteral:
    def test_move_literal(self):
        """MOVE literal to numeric field."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-MOVE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 42 TO WS-A.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 42


class TestIfElseBranch:
    def test_if_else_branch(self):
        """IF/ELSE comparison sets correct field."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-IFELSE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 10.",
                "77 WS-B PIC 9(4) VALUE 5.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-A > WS-B",
                "        MOVE 1 TO WS-R",
                "    ELSE",
                "        MOVE 2 TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 8, 4) == 1


class TestPerformTimes:
    def test_perform_times(self):
        """PERFORM paragraph N TIMES increments counter correctly."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-PTIMES.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-CTR PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM ADD-PARA 3 TIMES.",
                "    STOP RUN.",
                "ADD-PARA.",
                "    ADD 1 TO WS-CTR.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 3


class TestPerformUntil:
    def test_perform_until(self):
        """PERFORM UNTIL condition loops correctly."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-PUNTIL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM ADD-PARA UNTIL WS-A > 2.",
                "    STOP RUN.",
                "ADD-PARA.",
                "    ADD 1 TO WS-A.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 3


class TestNestedPerform:
    def test_nested_perform(self):
        """PERFORM paragraph calling another PERFORM accumulates correctly."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-NESTED.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-SUM PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM OUTER-PARA.",
                "    STOP RUN.",
                "OUTER-PARA.",
                "    ADD 100 TO WS-SUM.",
                "    PERFORM INNER-PARA.",
                "    ADD 1 TO WS-SUM.",
                "INNER-PARA.",
                "    ADD 10 TO WS-SUM.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 111


class TestGotoSkipsParagraph:
    def test_goto_skips_paragraph(self):
        """GO TO jumps over a paragraph, skipping its code."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-GOTO.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-VAL PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "PARA-A.",
                "    ADD 1 TO WS-VAL.",
                "    GO TO PARA-C.",
                "PARA-B.",
                "    ADD 100 TO WS-VAL.",
                "PARA-C.",
                "    ADD 10 TO WS-VAL.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 11


class TestGotoExitsPerform:
    def test_goto_exits_perform(self):
        """GO TO from inside a PERFORMed paragraph exits the PERFORM."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-GOTOPERF.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-VAL PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM WORK-PARA.",
                "    ADD 1 TO WS-VAL.",
                "    STOP RUN.",
                "WORK-PARA.",
                "    ADD 10 TO WS-VAL.",
                "    GO TO EXIT-PARA.",
                "EXIT-PARA.",
                "    ADD 100 TO WS-VAL.",
            ]
        )
        region = _first_region(vm)
        # GO TO bypasses PERFORM continuation — ADD 1 after PERFORM does not execute.
        # WORK-PARA adds 10, GO TO EXIT-PARA adds 100 = 110.
        assert _decode_zoned_unsigned(region, 0, 4) == 110


class TestEvaluateWhen:
    def test_evaluate_when(self):
        """EVALUATE/WHEN (COBOL switch-case) selects correct branch."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-EVAL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 2.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    EVALUATE WS-A",
                "        WHEN 1",
                "            MOVE 10 TO WS-R",
                "        WHEN 2",
                "            MOVE 20 TO WS-R",
                "        WHEN 3",
                "            MOVE 30 TO WS-R",
                "    END-EVALUATE.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 4, 4) == 20


class TestPerformVarying:
    def test_perform_varying(self):
        """PERFORM VARYING accumulates a sum of 1+2+3 = 6."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-PVARY.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-IDX PIC 9(4) VALUE 0.",
                "77 WS-SUM PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM ADD-PARA",
                "        VARYING WS-IDX FROM 1 BY 1",
                "        UNTIL WS-IDX > 3.",
                "    STOP RUN.",
                "ADD-PARA.",
                "    ADD WS-IDX TO WS-SUM.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 4, 4) == 6


class TestStringMove:
    def test_string_move(self):
        """MOVE alphanumeric literal to PIC X field stores EBCDIC bytes."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-STR.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-MSG PIC X(5) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                '    MOVE "HELLO" TO WS-MSG.',
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # EBCDIC encoding of "HELLO": H=0xC8, E=0xC5, L=0xD3, L=0xD3, O=0xD6
        expected = [0xC8, 0xC5, 0xD3, 0xD3, 0xD6]
        assert list(region[:5]) == expected


class TestCombinedProgram:
    def test_combined_program(self):
        """Combined program with arithmetic, IF, PERFORM TIMES, and GO TO."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMBINED.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 10.",
                "77 WS-B PIC 9(4) VALUE 5.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "77 WS-CTR PIC 9(4) VALUE 0.",
                "77 WS-FLAG PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD WS-A TO WS-R.",
                "    ADD WS-B TO WS-R.",
                "    SUBTRACT 3 FROM WS-R.",
                "    IF WS-R > 10",
                "        MOVE 1 TO WS-FLAG",
                "    ELSE",
                "        MOVE 2 TO WS-FLAG",
                "    END-IF.",
                "    PERFORM COUNT-PARA 3 TIMES.",
                "    GO TO DONE-PARA.",
                "SKIP-PARA.",
                "    MOVE 999 TO WS-R.",
                "DONE-PARA.",
                "    STOP RUN.",
                "COUNT-PARA.",
                "    ADD 1 TO WS-CTR.",
            ],
            max_steps=3000,
        )
        region = _first_region(vm)
        # WS-R = 10 + 5 - 3 = 12
        assert _decode_zoned_unsigned(region, 8, 4) == 12
        # WS-CTR = 3 (PERFORM 3 TIMES)
        assert _decode_zoned_unsigned(region, 12, 4) == 3
        # WS-FLAG = 1 (12 > 10 is true)
        assert _decode_zoned_unsigned(region, 16, 4) == 1


# ---------------------------------------------------------------------------
# Additional statement type coverage
# ---------------------------------------------------------------------------


class TestInitialize:
    def test_initialize_resets_numeric_to_zero(self):
        """INITIALIZE resets a numeric PIC 9 field to zero."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-INIT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 123.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INITIALIZE WS-A.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 0

    def test_initialize_resets_alphanumeric_to_spaces(self):
        """INITIALIZE resets a PIC X field to EBCDIC spaces (0x40)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-INIT2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-B PIC X(5) VALUE "HELLO".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INITIALIZE WS-B.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # All 5 bytes should be EBCDIC space (0x40)
        assert list(region[:5]) == [0x40] * 5

    def test_initialize_multiple_fields(self):
        """INITIALIZE resets multiple fields in one statement."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-INIT3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 99.",
                '77 WS-B PIC X(3) VALUE "XYZ".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INITIALIZE WS-A WS-B.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 0
        assert list(region[4:7]) == [0x40] * 3


class TestSetStatement:
    def test_set_to(self):
        """SET field TO literal assigns the value."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SET-TO.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-IDX PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SET WS-IDX TO 5.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 5

    def test_set_up_by(self):
        """SET field UP BY increments the value."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SET-UP.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-IDX PIC 9(4) VALUE 10.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SET WS-IDX UP BY 3.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 13

    def test_set_down_by(self):
        """SET field DOWN BY decrements the value."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SET-DN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-IDX PIC 9(4) VALUE 10.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SET WS-IDX DOWN BY 4.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 6

    def test_set_to_then_up_by(self):
        """SET TO followed by SET UP BY accumulates correctly."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SET-COMBO.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-IDX PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SET WS-IDX TO 5.",
                "    SET WS-IDX UP BY 3.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 8


class TestSearchStatement:
    def test_search_finds_match(self):
        """SEARCH WHEN condition finds the matching index."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SEARCH.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-IDX PIC 9(4) VALUE 1.",
                "77 WS-FOUND PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SEARCH WS-IDX VARYING WS-IDX",
                "        AT END MOVE 99 TO WS-FOUND",
                "        WHEN WS-IDX = 3",
                "            MOVE 1 TO WS-FOUND.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # WS-IDX should be 3 (the matching value)
        assert _decode_zoned_unsigned(region, 0, 4) == 3
        # WS-FOUND should be 1 (WHEN branch executed)
        assert _decode_zoned_unsigned(region, 4, 4) == 1

    def test_search_at_end(self):
        """SEARCH AT END fires when no WHEN matches within bound."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SEARCH2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-IDX PIC 9(4) VALUE 1.",
                "77 WS-FOUND PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SEARCH WS-IDX VARYING WS-IDX",
                "        AT END MOVE 99 TO WS-FOUND",
                "        WHEN WS-IDX = 9999",
                "            MOVE 1 TO WS-FOUND.",
                "    STOP RUN.",
            ],
            max_steps=50000,
        )
        region = _first_region(vm)
        # No match found — AT END should execute
        assert _decode_zoned_unsigned(region, 4, 4) == 99


class TestInspectTallying:
    def test_inspect_tallying_all(self):
        """INSPECT TALLYING FOR ALL counts all occurrences of a character."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-TALLY.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-DATA PIC X(10) VALUE "ABCABCABC ".',
                "77 WS-COUNT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INSPECT WS-DATA TALLYING WS-COUNT",
                '        FOR ALL "A".',
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # "ABCABCABC " has 3 occurrences of "A"
        assert _decode_zoned_unsigned(region, 10, 4) == 3


class TestInspectReplacing:
    def test_inspect_replacing_all(self):
        """INSPECT REPLACING ALL substitutes all occurrences."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REPL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-DATA PIC X(5) VALUE "AABAA".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                '    INSPECT WS-DATA REPLACING ALL "A" BY "B".',
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # All A's (EBCDIC 0xC1) should become B's (EBCDIC 0xC2)
        # "AABAA" → "BBBBB" (B at 0xC2 in all 5 positions)
        assert list(region[:5]) == [0xC2] * 5


class TestCallStatement:
    def test_call_does_not_crash(self):
        """CALL to external program is symbolic — verify pipeline doesn't crash."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-CALL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 10.",
                "77 WS-B PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 42 TO WS-B.",
                '    CALL "SUBPROG" USING WS-A.',
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # MOVE 42 before CALL should persist
        assert _decode_zoned_unsigned(region, 4, 4) == 42
        # WS-A unchanged (CALL is symbolic, doesn't modify memory)
        assert _decode_zoned_unsigned(region, 0, 4) == 10


class TestStringStatement:
    def test_string_concatenation(self):
        """STRING concatenates fields into target."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-STRCAT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-A PIC X(3) VALUE "ABC".',
                '77 WS-B PIC X(3) VALUE "DEF".',
                "77 WS-OUT PIC X(6) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STRING WS-A DELIMITED BY SIZE",
                "           WS-B DELIMITED BY SIZE",
                "           INTO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # EBCDIC: A=C1, B=C2, C=C3, D=C4, E=C5, F=C6
        expected = [0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6]
        assert list(region[6:12]) == expected


class TestUnstringStatement:
    def test_unstring_splits_by_space(self):
        """UNSTRING splits a string into parts by delimiter."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-UNSTR.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-FULL PIC X(11) VALUE "HELLO WORLD".',
                "77 WS-FIRST PIC X(5) VALUE SPACES.",
                "77 WS-LAST PIC X(5) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    UNSTRING WS-FULL DELIMITED BY SPACES",
                "        INTO WS-FIRST WS-LAST.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIRST (offset 11, 5 bytes) should be EBCDIC "HELLO"
        expected_hello = [0xC8, 0xC5, 0xD3, 0xD3, 0xD6]
        assert list(region[11:16]) == expected_hello
        # WS-LAST (offset 16, 5 bytes) should be EBCDIC "WORLD"
        expected_world = [0xE6, 0xD6, 0xD9, 0xD3, 0xC4]
        assert list(region[16:21]) == expected_world


class TestElementaryOccursMove:
    def test_move_to_occurs_element(self):
        """MOVE 42 TO WS-TBL(2) — stores 42 in the second element."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-OCCURS.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-TBL PIC 9(4) OCCURS 3.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 42 TO WS-TBL(2).",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-TBL occupies 12 bytes (4 * 3)
        # Element 1 at offset 0: should be 0 (uninitialised/zeros)
        assert _decode_zoned_unsigned(region, 0, 4) == 0
        # Element 2 at offset 4: should be 42
        assert _decode_zoned_unsigned(region, 4, 4) == 42
        # Element 3 at offset 8: should be 0
        assert _decode_zoned_unsigned(region, 8, 4) == 0


class TestOccursFieldSubscript:
    def test_move_with_field_subscript(self):
        """MOVE 99 TO WS-TBL(WS-IDX) — field-based subscript."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-OCCURS-IDX.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-TBL PIC 9(4) OCCURS 3.",
                "77 WS-IDX PIC 9(4) VALUE 2.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 99 TO WS-TBL(WS-IDX).",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-TBL: 12 bytes (4*3), WS-IDX: 4 bytes at offset 12
        # Element WS-IDX=2, so offset 4
        assert _decode_zoned_unsigned(region, 4, 4) == 99
        # Elements 1 and 3 untouched
        assert _decode_zoned_unsigned(region, 0, 4) == 0
        assert _decode_zoned_unsigned(region, 8, 4) == 0


class TestOccursLoop:
    def test_perform_varying_with_occurs(self):
        """PERFORM VARYING I FROM 1 BY 1 UNTIL I > 3, MOVE I TO WS-TBL(I)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-OCCURS-LOOP.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-TBL PIC 9(4) OCCURS 3.",
                "77 WS-I PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM VARYING WS-I FROM 1 BY 1",
                "        UNTIL WS-I > 3",
                "        MOVE WS-I TO WS-TBL(WS-I)",
                "    END-PERFORM.",
                "    STOP RUN.",
            ],
            max_steps=5000,
        )
        region = _first_region(vm)
        # Each element should contain its 1-based index
        assert _decode_zoned_unsigned(region, 0, 4) == 1
        assert _decode_zoned_unsigned(region, 4, 4) == 2
        assert _decode_zoned_unsigned(region, 8, 4) == 3


# ---------------------------------------------------------------------------
# Level-88 condition names, FILLER disambiguation, multi-value VALUE clauses
# ---------------------------------------------------------------------------


class TestLevel88ConditionName:
    def test_if_condition_name_single_value(self):
        """IF STATUS-ACTIVE expands to IF WS-STATUS = 'A' and takes the true branch."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COND88.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '05 WS-STATUS PIC X(1) VALUE "A".',
                '   88 STATUS-ACTIVE VALUE "A".',
                '   88 STATUS-INACTIVE VALUE "I".',
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF STATUS-ACTIVE",
                "        MOVE 1 TO WS-R",
                "    ELSE",
                "        MOVE 2 TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-STATUS is 'A' which matches STATUS-ACTIVE, so WS-R = 1
        assert _decode_zoned_unsigned(region, 1, 4) == 1

    def test_if_condition_name_false_branch(self):
        """IF STATUS-ACTIVE with WS-STATUS='I' takes the false branch."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COND88F.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '05 WS-STATUS PIC X(1) VALUE "I".',
                '   88 STATUS-ACTIVE VALUE "A".',
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF STATUS-ACTIVE",
                "        MOVE 1 TO WS-R",
                "    ELSE",
                "        MOVE 2 TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-STATUS is 'I' which does NOT match STATUS-ACTIVE, so WS-R = 2
        assert _decode_zoned_unsigned(region, 1, 4) == 2

    def test_condition_name_multi_value_or(self):
        """IF VALID-CODE with VALUE 'A' 'B' 'C' matches when field is 'B'."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COND88M.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '05 WS-CODE PIC X(1) VALUE "B".',
                '   88 VALID-CODE VALUE "A" "B" "C".',
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF VALID-CODE",
                "        MOVE 1 TO WS-R",
                "    ELSE",
                "        MOVE 2 TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-CODE is 'B' which matches one of 'A','B','C' → true → WS-R = 1
        assert _decode_zoned_unsigned(region, 1, 4) == 1

    def test_condition_name_multi_value_no_match(self):
        """IF VALID-CODE with VALUE 'A' 'B' 'C' fails when field is 'X'."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COND88N.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '05 WS-CODE PIC X(1) VALUE "X".',
                '   88 VALID-CODE VALUE "A" "B" "C".',
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF VALID-CODE",
                "        MOVE 1 TO WS-R",
                "    ELSE",
                "        MOVE 2 TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-CODE is 'X' which does NOT match any of 'A','B','C' → false → WS-R = 2
        assert _decode_zoned_unsigned(region, 1, 4) == 2


class TestFillerDisambiguation:
    def test_filler_fields_do_not_collide(self):
        """Multiple FILLER fields are disambiguated and don't crash layout building."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-FILLER.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-RECORD.",
                "   05 WS-NAME PIC X(5) VALUE SPACES.",
                "   05 FILLER PIC X(2) VALUE SPACES.",
                "   05 WS-CODE PIC 9(4) VALUE 42.",
                "   05 FILLER PIC X(3) VALUE SPACES.",
                "   05 WS-FLAG PIC 9(1) VALUE 7.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-NAME at offset 0 (5 bytes), FILLER_1 at 5 (2 bytes),
        # WS-CODE at 7 (4 bytes), FILLER_2 at 11 (3 bytes),
        # WS-FLAG at 14 (1 byte)
        assert _decode_zoned_unsigned(region, 7, 4) == 42
        assert _decode_zoned_unsigned(region, 14, 1) == 7

    def test_filler_between_computed_fields(self):
        """FILLER padding doesn't affect arithmetic on surrounding fields."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-FILLER2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-REC.",
                "   05 WS-A PIC 9(4) VALUE 10.",
                "   05 FILLER PIC X(5) VALUE SPACES.",
                "   05 WS-B PIC 9(4) VALUE 20.",
                "   05 FILLER PIC X(3) VALUE SPACES.",
                "   05 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD WS-A TO WS-R.",
                "    ADD WS-B TO WS-R.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A at 0 (4), FILLER_1 at 4 (5), WS-B at 9 (4),
        # FILLER_2 at 13 (3), WS-R at 16 (4)
        assert _decode_zoned_unsigned(region, 16, 4) == 30
