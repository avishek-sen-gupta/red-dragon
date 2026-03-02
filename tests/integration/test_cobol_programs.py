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
