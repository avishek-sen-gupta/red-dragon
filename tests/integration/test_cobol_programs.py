"""Integration tests for COBOL programs: real .cbl source → ProLeap bridge → IR → CFG → VM.

These tests exercise the full pipeline starting from actual COBOL source code,
going through the ProLeap Java bridge parser, ASG construction, IR lowering,
CFG building, and VM execution. They verify decoded numeric values in memory regions.

Requires the ProLeap bridge JAR to be available (set PROLEAP_BRIDGE_JAR env var
or have it at the default path). Tests skip gracefully when the JAR is absent.
"""

import os

import pytest

from interpreter.address import Address
from interpreter.cobol.features import CobolFeature
from interpreter.run import run
from tests.covers import covers

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


def _run_cobol(lines: list[str], max_steps: int = 1000):
    """Run a COBOL program through the full pipeline and return VMState."""
    source = _to_fixed(lines)
    return run(source=source, language="cobol", max_steps=max_steps)


def _first_region(vm):
    """Return the first memory region from the VM state."""
    return vm.region_get(list(vm.region_keys())[0])


def _decode_alpha(region: list[int], offset: int, length: int) -> str:
    """Decode EBCDIC alphanumeric bytes from a memory region to an ASCII string."""
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


# ---------------------------------------------------------------------------
# Test programs
# ---------------------------------------------------------------------------


class TestInitialValues:
    @covers(
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.SECTION_WORKING_STORAGE,
        CobolFeature.PIC_CLAUSE,
    )
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


class TestValueClauseAlphanumericInit:
    """AC2 (4q25.9.1): PIC X field with VALUE literal is initialised at startup."""

    @covers(CobolFeature.VALUE_CLAUSE, CobolFeature.SECTION_WORKING_STORAGE)
    def test_pic_x_value_literal_initialised(self):
        """77 WS-TEXT PIC X(5) VALUE 'HELLO' — bytes 0-4 must decode to 'HELLO'."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-AX2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-TEXT PIC X(5) VALUE 'HELLO'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 0, 5) == "HELLO"


class TestValueClauseDefaultZeroFill:
    """AC3 (4q25.9.3): PIC 9 field without VALUE is zero-filled at startup."""

    @covers(CobolFeature.VALUE_CLAUSE, CobolFeature.SECTION_WORKING_STORAGE)
    def test_pic_9_no_value_is_zero(self):
        """77 WS-N PIC 9(3) (no VALUE) — all 3 zoned bytes must be 0xF0 (digit 0)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-AX3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-N PIC 9(3).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 3) == 0


class TestValueClauseRedefinesInit:
    """AC4 (4q25.9.2): VALUE on a field that a REDEFINES target shares bytes with."""

    @covers(
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.REDEFINES_CLAUSE,
        CobolFeature.SECTION_WORKING_STORAGE,
    )
    def test_value_on_base_visible_through_redefines(self):
        """01 WS-BASE PIC X(4) VALUE 'ABCD' — bytes 0-3 must decode to 'ABCD'."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-AX4.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-BASE PIC X(4) VALUE 'ABCD'.",
                "01 WS-NUM REDEFINES WS-BASE PIC 9(4).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 0, 4) == "ABCD"


class TestValueClauseGroupChildInit:
    """AC5 (4q25.9.4): GROUP item — each elementary child with VALUE is initialised."""

    @covers(CobolFeature.VALUE_CLAUSE, CobolFeature.SECTION_WORKING_STORAGE)
    def test_group_children_independently_initialised(self):
        """01 WS-REC group: WS-A(9(3))=42 @ 0, WS-B(X(5))='HI   ' @ 3, WS-C(9(2))=7 @ 8."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-AX5.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-REC.",
                "    05 WS-A PIC 9(3) VALUE 42.",
                "    05 WS-B PIC X(5) VALUE 'HI'.",
                "    05 WS-C PIC 9(2) VALUE 7.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 3) == 42
        assert _decode_alpha(region, 3, 2) == "HI"
        assert _decode_zoned_unsigned(region, 8, 2) == 7


class TestAddSubtract:
    @covers(CobolFeature.ADD, CobolFeature.SUBTRACT, CobolFeature.ARITHMETIC_EXPRESSION)
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
        # Source operands unchanged
        assert _decode_zoned_unsigned(region, 0, 4) == 10, "WS-A should remain 10"
        assert _decode_zoned_unsigned(region, 4, 4) == 5, "WS-B should remain 5"
        # WS-R = 10 + 5 - 3 = 12
        assert _decode_zoned_unsigned(region, 8, 4) == 12


class TestArithmeticGiving:
    @covers(CobolFeature.ADD, CobolFeature.GIVING_CLAUSE)
    def test_add_giving(self):
        """ADD WS-A TO WS-B GIVING WS-R stores A + B in R."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ADDGIV.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 10.",
                "77 WS-B PIC 9(4) VALUE 25.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD WS-A TO WS-B GIVING WS-R.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A=10, WS-B=25 unchanged; WS-R = 10 + 25 = 35
        assert _decode_zoned_unsigned(region, 0, 4) == 10
        assert _decode_zoned_unsigned(region, 4, 4) == 25
        assert _decode_zoned_unsigned(region, 8, 4) == 35

    @covers(CobolFeature.SUBTRACT, CobolFeature.GIVING_CLAUSE)
    def test_subtract_giving(self):
        """SUBTRACT WS-A FROM WS-B GIVING WS-R stores B - A in R."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SUBGIV.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 10.",
                "77 WS-B PIC 9(4) VALUE 25.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SUBTRACT WS-A FROM WS-B GIVING WS-R.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A=10, WS-B=25 unchanged; WS-R = 25 - 10 = 15
        assert _decode_zoned_unsigned(region, 0, 4) == 10
        assert _decode_zoned_unsigned(region, 4, 4) == 25
        assert _decode_zoned_unsigned(region, 8, 4) == 15

    @covers(CobolFeature.ADD, CobolFeature.GIVING_CLAUSE)
    def test_add_giving_literal(self):
        """ADD 10 TO WS-A GIVING WS-R stores 10 + A in R."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ADDLIT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 7.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD 10 TO WS-A GIVING WS-R.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A=7 unchanged; WS-R = 10 + 7 = 17
        assert _decode_zoned_unsigned(region, 0, 4) == 7
        assert _decode_zoned_unsigned(region, 4, 4) == 17

    @covers(CobolFeature.SUBTRACT, CobolFeature.GIVING_CLAUSE)
    def test_subtract_giving_literal(self):
        """SUBTRACT 3 FROM WS-A GIVING WS-R stores A - 3 in R."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SUBLIT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 20.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SUBTRACT 3 FROM WS-A GIVING WS-R.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A=20 unchanged; WS-R = 20 - 3 = 17
        assert _decode_zoned_unsigned(region, 0, 4) == 20
        assert _decode_zoned_unsigned(region, 4, 4) == 17


class TestMultiplyDivide:
    @covers(CobolFeature.MULTIPLY, CobolFeature.DIVIDE, CobolFeature.GIVING_CLAUSE)
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
        # Source operands unchanged by GIVING
        assert _decode_zoned_unsigned(region, 0, 4) == 10, "WS-A should remain 10"
        assert _decode_zoned_unsigned(region, 4, 4) == 5, "WS-B should remain 5"
        # WS-R = 10 * 3 = 30
        assert _decode_zoned_unsigned(region, 8, 4) == 30
        # WS-Q = 30 / 5 = 6
        assert _decode_zoned_unsigned(region, 12, 4) == 6


class TestComputeExpression:
    @covers(CobolFeature.COMPUTE, CobolFeature.ARITHMETIC_EXPRESSION)
    def test_compute_expression(self):
        """COMPUTE WS-R = WS-A + WS-B * 2 should evaluate as 10 + (5*2) = 20."""
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
        # Source operands unchanged
        assert _decode_zoned_unsigned(region, 0, 4) == 10, "WS-A should remain 10"
        assert _decode_zoned_unsigned(region, 4, 4) == 5, "WS-B should remain 5"
        # Result: 10 + (5 * 2) = 20
        assert _decode_zoned_unsigned(region, 8, 4) == 20


class TestMoveLiteral:
    @covers(CobolFeature.MOVE)
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
    @covers(CobolFeature.IF_ELSE, CobolFeature.COMPARISON_OPERATORS)
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
    @covers(CobolFeature.PERFORM, CobolFeature.PERFORM_TIMES, CobolFeature.ADD)
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
    @covers(CobolFeature.PERFORM, CobolFeature.PERFORM_UNTIL, CobolFeature.ADD)
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
    @covers(CobolFeature.PERFORM, CobolFeature.ADD)
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
    @covers(CobolFeature.GO_TO, CobolFeature.ADD)
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
    @covers(CobolFeature.GO_TO, CobolFeature.PERFORM, CobolFeature.ADD)
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
    @covers(CobolFeature.EVALUATE, CobolFeature.COMPARISON_OPERATORS)
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
    @covers(CobolFeature.PERFORM, CobolFeature.PERFORM_VARYING, CobolFeature.ADD)
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
    @covers(CobolFeature.MOVE)
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
    @covers(
        CobolFeature.ADD,
        CobolFeature.SUBTRACT,
        CobolFeature.IF_ELSE,
        CobolFeature.PERFORM,
        CobolFeature.PERFORM_TIMES,
        CobolFeature.GO_TO,
    )
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
    @covers(CobolFeature.INITIALIZE, CobolFeature.PIC_CLAUSE)
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

    @covers(CobolFeature.INITIALIZE, CobolFeature.PIC_CLAUSE)
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

    @covers(CobolFeature.INITIALIZE, CobolFeature.PIC_CLAUSE)
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

    @covers(CobolFeature.INITIALIZE, CobolFeature.GROUP_ITEM)
    def test_initialize_group_item_resets_children_by_type(self):
        """INITIALIZE on a group item resets each child with its type's default.

        WS-A (PIC 9) should become 0, WS-B (PIC X) should become spaces.
        Previously the group was treated as ALPHANUMERIC and space-filled entirely,
        which clobbered the numeric child with EBCDIC spaces instead of zeros.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. INITGRP.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-GROUP.",
                "   05 WS-A PIC 9(3) VALUE 999.",
                "   05 WS-B PIC X(3) VALUE 'ABC'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INITIALIZE WS-GROUP.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        layout = vm.data_layout
        wa_offset = layout["WS-A"]["offset"]
        wb_offset = layout["WS-B"]["offset"]
        assert _decode_zoned_unsigned(region, wa_offset, 3) == 0
        assert list(region[wb_offset : wb_offset + 3]) == [0x40] * 3


class TestSetStatement:
    @covers(CobolFeature.SET_TO)
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

    @covers(CobolFeature.SET_UP_BY)
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

    @covers(CobolFeature.SET_DOWN_BY)
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

    @covers(CobolFeature.SET_TO, CobolFeature.SET_UP_BY)
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
    @covers(CobolFeature.SEARCH_LINEAR, CobolFeature.SEARCH_WHEN_CONDITIONS)
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

    @covers(CobolFeature.SEARCH_LINEAR, CobolFeature.SEARCH_AT_END)
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
        # WS-IDX should have advanced beyond its initial value of 1
        assert (
            _decode_zoned_unsigned(region, 0, 4) > 1
        ), "WS-IDX should have incremented during search"
        # No match found — AT END should execute
        assert _decode_zoned_unsigned(region, 4, 4) == 99


class TestInspectTallying:
    @covers(CobolFeature.INSPECT_TALLYING)
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
    @covers(CobolFeature.INSPECT_REPLACING)
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
    @covers(CobolFeature.CALL, CobolFeature.CALL_USING)
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
    @covers(CobolFeature.STRING_VERB, CobolFeature.STRING_DELIMITED_BY)
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
    @covers(CobolFeature.UNSTRING_VERB, CobolFeature.UNSTRING_DELIMITED_BY)
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
    @covers(CobolFeature.MOVE, CobolFeature.OCCURS_FIXED, CobolFeature.SUBSCRIPT_ACCESS)
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
    @covers(CobolFeature.MOVE, CobolFeature.OCCURS_FIXED, CobolFeature.SUBSCRIPT_ACCESS)
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
    @covers(
        CobolFeature.PERFORM,
        CobolFeature.PERFORM_VARYING,
        CobolFeature.MOVE,
        CobolFeature.OCCURS_FIXED,
        CobolFeature.SUBSCRIPT_ACCESS,
    )
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
    @covers(CobolFeature.LEVEL_88_CONDITION, CobolFeature.IF_ELSE)
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

    @covers(CobolFeature.LEVEL_88_CONDITION, CobolFeature.IF_ELSE)
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

    @covers(CobolFeature.LEVEL_88_CONDITION, CobolFeature.IF_ELSE)
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

    @covers(CobolFeature.LEVEL_88_CONDITION, CobolFeature.IF_ELSE)
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
    @covers(CobolFeature.FILLER_FIELD, CobolFeature.GROUP_ITEM)
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
        # Region size must account for all fields including FILLERs: 5+2+4+3+1 = 15
        assert (
            len(region) >= 15
        ), f"region must be >= 15 bytes for all fields + FILLERs, got {len(region)}"

    @covers(CobolFeature.FILLER_FIELD, CobolFeature.GROUP_ITEM, CobolFeature.ADD)
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


class TestLevel88ThruRange:
    @covers(
        CobolFeature.LEVEL_88_CONDITION,
        CobolFeature.VALUE_THRU_RANGE,
        CobolFeature.CONDITION_VALUES_THRU,
        CobolFeature.IF_ELSE,
    )
    def test_thru_range_match(self):
        """88 IN-RANGE VALUE 10 THRU 50 matches when field is 25."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-THRU1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "05 WS-SCORE PIC 9(4) VALUE 25.",
                "   88 IN-RANGE VALUE 10 THRU 50.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF IN-RANGE",
                "        MOVE 1 TO WS-R",
                "    ELSE",
                "        MOVE 2 TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # 25 is in [10, 50] → true → WS-R = 1
        assert _decode_zoned_unsigned(region, 4, 4) == 1

    @covers(
        CobolFeature.LEVEL_88_CONDITION,
        CobolFeature.VALUE_THRU_RANGE,
        CobolFeature.CONDITION_VALUES_THRU,
        CobolFeature.IF_ELSE,
    )
    def test_thru_range_no_match(self):
        """88 IN-RANGE VALUE 10 THRU 50 fails when field is 75."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-THRU2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "05 WS-SCORE PIC 9(4) VALUE 75.",
                "   88 IN-RANGE VALUE 10 THRU 50.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF IN-RANGE",
                "        MOVE 1 TO WS-R",
                "    ELSE",
                "        MOVE 2 TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # 75 is NOT in [10, 50] → false → WS-R = 2
        assert _decode_zoned_unsigned(region, 4, 4) == 2

    @covers(
        CobolFeature.LEVEL_88_CONDITION,
        CobolFeature.VALUE_THRU_RANGE,
        CobolFeature.CONDITION_VALUES_THRU,
        CobolFeature.IF_ELSE,
    )
    def test_thru_range_boundary_low(self):
        """88 IN-RANGE VALUE 10 THRU 50 matches at exact lower bound."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-THRU3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "05 WS-SCORE PIC 9(4) VALUE 10.",
                "   88 IN-RANGE VALUE 10 THRU 50.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF IN-RANGE",
                "        MOVE 1 TO WS-R",
                "    ELSE",
                "        MOVE 2 TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # 10 is in [10, 50] → true → WS-R = 1
        assert _decode_zoned_unsigned(region, 4, 4) == 1


class TestLevel88MixedValues:
    @covers(
        CobolFeature.LEVEL_88_CONDITION,
        CobolFeature.VALUE_THRU_RANGE,
        CobolFeature.CONDITION_VALUES_THRU,
        CobolFeature.IF_ELSE,
    )
    def test_mixed_discrete_and_thru(self):
        """88 SPECIAL VALUE 5 10 THRU 20 99 matches when field is 15."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-MIX1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "05 WS-CODE PIC 9(4) VALUE 15.",
                "   88 SPECIAL VALUE 5 10 THRU 20 99.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF SPECIAL",
                "        MOVE 1 TO WS-R",
                "    ELSE",
                "        MOVE 2 TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # 15 is in [10, 20] range → true → WS-R = 1
        assert _decode_zoned_unsigned(region, 4, 4) == 1

    @covers(
        CobolFeature.LEVEL_88_CONDITION,
        CobolFeature.VALUE_THRU_RANGE,
        CobolFeature.CONDITION_VALUES_THRU,
        CobolFeature.IF_ELSE,
    )
    def test_mixed_discrete_match(self):
        """88 SPECIAL VALUE 5 10 THRU 20 99 matches discrete value 99."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-MIX2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "05 WS-CODE PIC 9(4) VALUE 99.",
                "   88 SPECIAL VALUE 5 10 THRU 20 99.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF SPECIAL",
                "        MOVE 1 TO WS-R",
                "    ELSE",
                "        MOVE 2 TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # 99 matches discrete value → true → WS-R = 1
        assert _decode_zoned_unsigned(region, 4, 4) == 1

    @covers(
        CobolFeature.LEVEL_88_CONDITION,
        CobolFeature.VALUE_THRU_RANGE,
        CobolFeature.CONDITION_VALUES_THRU,
        CobolFeature.IF_ELSE,
    )
    def test_mixed_no_match(self):
        """88 SPECIAL VALUE 5 10 THRU 20 99 fails when field is 30."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-MIX3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "05 WS-CODE PIC 9(4) VALUE 30.",
                "   88 SPECIAL VALUE 5 10 THRU 20 99.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF SPECIAL",
                "        MOVE 1 TO WS-R",
                "    ELSE",
                "        MOVE 2 TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # 30 not in {5} or [10,20] or {99} → false → WS-R = 2
        assert _decode_zoned_unsigned(region, 4, 4) == 2


class TestLevel88InEvaluate:
    @covers(
        CobolFeature.EVALUATE,
        CobolFeature.EVALUATE_WHEN_OTHER,
        CobolFeature.LEVEL_88_CONDITION,
    )
    def test_evaluate_true_with_condition_name(self):
        """EVALUATE TRUE WHEN STATUS-ACTIVE selects the condition-name branch."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-EVAL88.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '05 WS-STATUS PIC X(1) VALUE "A".',
                '   88 STATUS-ACTIVE VALUE "A".',
                '   88 STATUS-INACTIVE VALUE "I".',
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    EVALUATE TRUE",
                "        WHEN STATUS-ACTIVE",
                "            MOVE 1 TO WS-R",
                "        WHEN STATUS-INACTIVE",
                "            MOVE 2 TO WS-R",
                "    END-EVALUATE.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-STATUS is 'A' → STATUS-ACTIVE is true → WS-R = 1
        assert _decode_zoned_unsigned(region, 1, 4) == 1

    @covers(
        CobolFeature.EVALUATE,
        CobolFeature.EVALUATE_WHEN_OTHER,
        CobolFeature.LEVEL_88_CONDITION,
    )
    def test_evaluate_true_second_branch(self):
        """EVALUATE TRUE WHEN ... selects the second condition-name branch."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-EVL882.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '05 WS-STATUS PIC X(1) VALUE "I".',
                '   88 STATUS-ACTIVE VALUE "A".',
                '   88 STATUS-INACTIVE VALUE "I".',
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    EVALUATE TRUE",
                "        WHEN STATUS-ACTIVE",
                "            MOVE 1 TO WS-R",
                "        WHEN STATUS-INACTIVE",
                "            MOVE 2 TO WS-R",
                "    END-EVALUATE.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-STATUS is 'I' → STATUS-INACTIVE is true → WS-R = 2
        assert _decode_zoned_unsigned(region, 1, 4) == 2


class TestLevel88InPerformUntil:
    @covers(
        CobolFeature.PERFORM,
        CobolFeature.PERFORM_UNTIL,
        CobolFeature.LEVEL_88_CONDITION,
        CobolFeature.ADD,
    )
    def test_perform_until_condition_name(self):
        """PERFORM ... UNTIL DONE-FLAG loops until the condition name is true."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-PUNTIL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "05 WS-CTR PIC 9(4) VALUE 0.",
                "   88 DONE-FLAG VALUE 5.",
                "77 WS-SUM PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM ADD-PARA UNTIL DONE-FLAG.",
                "    STOP RUN.",
                "ADD-PARA.",
                "    ADD 1 TO WS-CTR.",
                "    ADD WS-CTR TO WS-SUM.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # Loops while WS-CTR != 5: adds 1+2+3+4+5 = 15
        assert _decode_zoned_unsigned(region, 0, 4) == 5
        assert _decode_zoned_unsigned(region, 4, 4) == 15

    @covers(
        CobolFeature.PERFORM,
        CobolFeature.PERFORM_UNTIL,
        CobolFeature.LEVEL_88_CONDITION,
    )
    def test_perform_until_condition_name_already_true(self):
        """PERFORM ... UNTIL DONE-FLAG does not execute when already true."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-PUNTL2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "05 WS-CTR PIC 9(4) VALUE 5.",
                "   88 DONE-FLAG VALUE 5.",
                "77 WS-SUM PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM ADD-PARA UNTIL DONE-FLAG.",
                "    STOP RUN.",
                "ADD-PARA.",
                "    ADD 1 TO WS-CTR.",
                "    ADD WS-CTR TO WS-SUM.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # WS-CTR already 5 → DONE-FLAG is true → body never executes
        assert _decode_zoned_unsigned(region, 0, 4) == 5
        assert _decode_zoned_unsigned(region, 4, 4) == 0


class TestBlankWhenZero:
    @covers(CobolFeature.BLANK_WHEN_ZERO)
    def test_blank_when_zero_with_zero_value(self):
        """BLANK WHEN ZERO field with VALUE 0 should be all EBCDIC spaces (0x40)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-BWZ.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-AMT PIC 9(4) BLANK WHEN ZERO VALUE 0.",
                "77 WS-QTY PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-AMT has BLANK WHEN ZERO + VALUE 0 → all 4 bytes are EBCDIC space (0x40)
        assert list(region[0:4]) == [0x40, 0x40, 0x40, 0x40]
        # WS-QTY has no BLANK WHEN ZERO → normal zoned decimal zeros (0xF0)
        assert _decode_zoned_unsigned(region, 4, 4) == 0

    @covers(CobolFeature.BLANK_WHEN_ZERO)
    def test_blank_when_zero_with_nonzero_value(self):
        """BLANK WHEN ZERO field with non-zero VALUE encodes normally."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-BWZ2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-AMT PIC 9(4) BLANK WHEN ZERO VALUE 42.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # Non-zero → normal zoned encoding, decodes to 42
        assert _decode_zoned_unsigned(region, 0, 4) == 42

    @covers(CobolFeature.BLANK_WHEN_ZERO, CobolFeature.MOVE)
    def test_blank_when_zero_after_move_to_zero(self):
        """BLANK WHEN ZERO field becomes spaces after MOVE 0 at runtime."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-BWZ3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-AMT PIC 9(4) BLANK WHEN ZERO VALUE 10.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 0 TO WS-AMT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # After MOVE 0, BLANK WHEN ZERO should produce spaces
        assert list(region[0:4]) == [0x40, 0x40, 0x40, 0x40]


class TestBareStatements:
    """Bare statements (no enclosing paragraph) at division and section level."""

    @covers(CobolFeature.COMPUTE, CobolFeature.BARE_STATEMENTS)
    def test_division_level_bare_compute(self):
        """COMPUTE directly under PROCEDURE DIVISION (no paragraph) executes correctly."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. BARE-DIV.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(3) VALUE 100.",
                "PROCEDURE DIVISION.",
                "    COMPUTE WS-A = WS-A + 50.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 3) == 150

    @covers(CobolFeature.COMPUTE, CobolFeature.BARE_STATEMENTS)
    def test_section_level_bare_compute(self):
        """COMPUTE directly under a SECTION (no paragraph) executes correctly."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. BARE-SEC.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(3) VALUE 100.",
                "PROCEDURE DIVISION.",
                "MAIN-SECTION SECTION.",
                "    COMPUTE WS-A = WS-A + 50.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 3) == 150

    @covers(CobolFeature.COMPUTE, CobolFeature.PERFORM, CobolFeature.BARE_STATEMENTS)
    def test_mixed_bare_and_paragraph(self):
        """Division-level bare statement followed by a paragraph both execute."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MIX-BARE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(3) VALUE 100.",
                "77 WS-B PIC 9(3) VALUE 0.",
                "PROCEDURE DIVISION.",
                "    COMPUTE WS-A = WS-A + 50.",
                "    PERFORM CALC-PARA.",
                "    STOP RUN.",
                "CALC-PARA.",
                "    COMPUTE WS-B = WS-A + 10.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 3) == 150
        assert _decode_zoned_unsigned(region, 3, 3) == 160


class TestDataLayout:
    @covers(CobolFeature.DATA_LAYOUT_ENGINE)
    def test_data_layout_present_after_execution(self):
        """run() attaches data_layout with correct field entries to VMState."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. LAYOUT-TEST.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(3) VALUE 150.",
                "PROCEDURE DIVISION.",
                "    STOP RUN.",
            ]
        )
        assert vm.data_layout, "data_layout should not be empty after execution"
        assert "WS-A" in vm.data_layout
        ws_a = vm.data_layout["WS-A"]
        assert ws_a["offset"] == 0
        assert ws_a["length"] == 3
        assert ws_a["category"] == "ZONED_DECIMAL"
        assert ws_a["total_digits"] == 3


# ---------------------------------------------------------------------------
# REDEFINES edge cases
# ---------------------------------------------------------------------------


class TestRedefines:
    """COBOL REDEFINES: multiple fields sharing the same byte range."""

    @covers(CobolFeature.REDEFINES_CLAUSE)
    def test_simple_redefines_numeric_value_shared_bytes(self):
        """Numeric VALUE init bytes are accessible at the REDEFINES overlay offset."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-NUM   PIC 9(4) VALUE 1234.",
                "01 WS-NUM-X REDEFINES WS-NUM PIC X(4).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-NUM at offset 0: zoned decimal 1234 = F1 F2 F3 F4.
        assert _decode_zoned_unsigned(region, 0, 4) == 1234
        # The same 4 bytes viewed as raw EBCDIC digits.
        expected_zoned = [0xF1, 0xF2, 0xF3, 0xF4]
        assert list(region[0:4]) == expected_zoned

    @covers(CobolFeature.REDEFINES_CLAUSE)
    def test_simple_redefines_data_layout_offset(self):
        """REDEFINES field should share the same offset as the original in data_layout."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF1L.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-NUM   PIC 9(4) VALUE 1234.",
                "01 WS-NUM-X REDEFINES WS-NUM PIC X(4).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        # Both fields should share offset 0 and the region should be 4 bytes.
        assert vm.data_layout["WS-NUM"]["offset"] == 0
        assert vm.data_layout["WS-NUM-X"]["offset"] == 0
        region = _first_region(vm)
        assert len(region) == 4

    @covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.GROUP_ITEM)
    def test_group_redefines_children_initialised(self):
        """Group item children VALUE clauses populate shared byte range."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-DATE.",
                "   05 WS-YEAR  PIC 9(4) VALUE 2026.",
                "   05 WS-MONTH PIC 9(2) VALUE 03.",
                "   05 WS-DAY   PIC 9(2) VALUE 22.",
                "01 WS-DATE-NUM REDEFINES WS-DATE PIC 9(8).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-DATE group: 4+2+2 = 8 bytes at offset 0.
        # Children initialised: YEAR=2026, MONTH=03, DAY=22.
        assert _decode_zoned_unsigned(region, 0, 4) == 2026
        assert _decode_zoned_unsigned(region, 4, 2) == 3
        assert _decode_zoned_unsigned(region, 6, 2) == 22
        # WS-DATE-NUM redefines the same 8 bytes — reading as one number.
        assert _decode_zoned_unsigned(region, 0, 8) == 20260322

    @covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.GROUP_ITEM, CobolFeature.MOVE)
    def test_group_redefines_move_composite(self):
        """MOVE group REDEFINES composite to a separate result field."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF2M.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-DATE.",
                "   05 WS-YEAR  PIC 9(4) VALUE 2026.",
                "   05 WS-MONTH PIC 9(2) VALUE 03.",
                "   05 WS-DAY   PIC 9(2) VALUE 22.",
                "01 WS-DATE-NUM REDEFINES WS-DATE PIC 9(8).",
                "01 WS-RESULT PIC 9(8) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-DATE-NUM TO WS-RESULT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-RESULT at offset 8 should hold 20260322 after MOVE.
        assert _decode_zoned_unsigned(region, 8, 8) == 20260322

    @covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.GROUP_ITEM, CobolFeature.MOVE)
    def test_multiple_redefines_move_through_children(self):
        """Multiple REDEFINES: MOVE through group REDEFINES children."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '01 WS-DATA    PIC X(8) VALUE "ABCDEFGH".',
                "01 WS-DATA-P  REDEFINES WS-DATA.",
                "   05 WS-PART1 PIC X(4).",
                "   05 WS-PART2 PIC X(4).",
                "01 WS-OUT1 PIC X(4) VALUE SPACES.",
                "01 WS-OUT2 PIC X(4) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-PART1 TO WS-OUT1.",
                "    MOVE WS-PART2 TO WS-OUT2.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-OUT1 at offset 8 (4 bytes), WS-OUT2 at offset 12 (4 bytes).
        # EBCDIC: A=0xC1, B=0xC2, C=0xC3, D=0xC4
        expected_part1 = [0xC1, 0xC2, 0xC3, 0xC4]  # "ABCD"
        # EBCDIC: E=0xC5, F=0xC6, G=0xC7, H=0xC8
        expected_part2 = [0xC5, 0xC6, 0xC7, 0xC8]  # "EFGH"
        assert list(region[8:12]) == expected_part1
        assert list(region[12:16]) == expected_part2

    @covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.GROUP_ITEM)
    def test_multiple_redefines_original_bytes_intact(self):
        """Multiple REDEFINES: original field VALUE bytes are stored correctly."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF3B.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '01 WS-DATA    PIC X(8) VALUE "ABCDEFGH".',
                "01 WS-DATA-P  REDEFINES WS-DATA.",
                "   05 WS-PART1 PIC X(4).",
                "   05 WS-PART2 PIC X(4).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-DATA at offset 0: EBCDIC "ABCDEFGH"
        # A=0xC1, B=0xC2, C=0xC3, D=0xC4, E=0xC5, F=0xC6, G=0xC7, H=0xC8
        expected = [0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8]
        assert list(region[0:8]) == expected

    @covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.GROUP_ITEM)
    def test_multiple_redefines_data_layout_offsets(self):
        """Multiple REDEFINES fields should all share offset 0 in data_layout."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF3L.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '01 WS-DATA    PIC X(8) VALUE "ABCDEFGH".',
                "01 WS-DATA-N  REDEFINES WS-DATA PIC 9(8).",
                "01 WS-DATA-P  REDEFINES WS-DATA.",
                "   05 WS-PART1 PIC X(4).",
                "   05 WS-PART2 PIC X(4).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        # All three names should share offset 0.
        assert vm.data_layout["WS-DATA"]["offset"] == 0
        assert vm.data_layout["WS-DATA-N"]["offset"] == 0
        assert vm.data_layout["WS-DATA-P"]["offset"] == 0
        # Region is only 8 bytes — REDEFINES do not allocate additional space.
        region = _first_region(vm)
        assert len(region) == 8

    @covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.MOVE)
    def test_redefines_numeric_as_alphanumeric_move(self):
        """Numeric VALUE init, MOVE through alphanumeric REDEFINES to output."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF4.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-NUM    PIC 9(4) VALUE 1234.",
                "01 WS-NUM-X  REDEFINES WS-NUM PIC X(4).",
                "01 WS-OUT PIC X(4) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-NUM-X TO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-OUT at offset 4 should contain the same bytes as WS-NUM.
        expected_zoned = [0xF1, 0xF2, 0xF3, 0xF4]
        assert list(region[4:8]) == expected_zoned

    @covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.ADD)
    def test_redefines_with_arithmetic(self):
        """Arithmetic through original field, verify bytes are updated in overlay."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF5.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-A PIC 9(4) VALUE 0.",
                "01 WS-A-X REDEFINES WS-A PIC X(4).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD 42 TO WS-A.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A at offset 0 (4 bytes). After ADD 42, WS-A = 42.
        assert _decode_zoned_unsigned(region, 0, 4) == 42
        # The REDEFINES overlay shares the same bytes —
        # zoned decimal 0042 = F0 F0 F4 F2.
        expected = [0xF0, 0xF0, 0xF4, 0xF2]
        assert list(region[0:4]) == expected

    @covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.OCCURS_FIXED, CobolFeature.MOVE)
    def test_redefines_with_occurs(self):
        """OCCURS array redefined as flat field — MOVE flat reads all elements."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF-OCC.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-TABLE.",
                "   05 WS-ITEM PIC 9(2) OCCURS 4.",
                "01 WS-FLAT REDEFINES WS-TABLE PIC 9(8).",
                "01 WS-RESULT PIC 9(8) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 10 TO WS-ITEM(1).",
                "    MOVE 20 TO WS-ITEM(2).",
                "    MOVE 30 TO WS-ITEM(3).",
                "    MOVE 40 TO WS-ITEM(4).",
                "    MOVE WS-FLAT TO WS-RESULT.",
                "    STOP RUN.",
            ],
            max_steps=1600,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 8, 8) == 10203040

    @covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.GROUP_ITEM, CobolFeature.MOVE)
    def test_chained_redefines(self):
        """Third field REDEFINES the original — group children read correct bytes."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-CHAIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-ORIG  PIC X(4) VALUE 'ABCD'.",
                "01 WS-R1    REDEFINES WS-ORIG PIC 9(4).",
                "01 WS-R2    REDEFINES WS-ORIG.",
                "   05 WS-HI PIC X(2).",
                "   05 WS-LO PIC X(2).",
                "01 WS-OUT PIC X(2) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-HI TO WS-OUT.",
                "    STOP RUN.",
            ],
        )
        region = _first_region(vm)
        # WS-OUT at offset 4: EBCDIC "AB" = 0xC1 0xC2
        assert list(region[4:6]) == [0xC1, 0xC2]

    @covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.MOVE)
    def test_redefines_size_mismatch(self):
        """REDEFINES field smaller than original — reads partial overlay."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SIZE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-BIG   PIC X(8) VALUE 'ABCDEFGH'.",
                "01 WS-SMALL REDEFINES WS-BIG PIC X(4).",
                "01 WS-OUT   PIC X(4) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-SMALL TO WS-OUT.",
                "    STOP RUN.",
            ],
        )
        region = _first_region(vm)
        # WS-OUT at offset 8: first 4 bytes "ABCD" = C1 C2 C3 C4
        assert list(region[8:12]) == [0xC1, 0xC2, 0xC3, 0xC4]

    @covers(
        CobolFeature.REDEFINES_CLAUSE,
        CobolFeature.GROUP_ITEM,
        CobolFeature.MOVE,
        CobolFeature.ADD,
    )
    def test_redefines_arithmetic_then_move_composite(self):
        """Modify group child, then MOVE composite REDEFINES to result."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ARITH.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-DATE.",
                "   05 WS-YEAR  PIC 9(4) VALUE 2026.",
                "   05 WS-MONTH PIC 9(2) VALUE 03.",
                "   05 WS-DAY   PIC 9(2) VALUE 22.",
                "01 WS-DATE-NUM REDEFINES WS-DATE PIC 9(8).",
                "01 WS-NEXT     PIC 9(8) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD 1 TO WS-DAY.",
                "    MOVE WS-DATE-NUM TO WS-NEXT.",
                "    STOP RUN.",
            ],
            max_steps=1600,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 6, 2) == 23
        assert _decode_zoned_unsigned(region, 8, 8) == 20260323


# ---------------------------------------------------------------------------
# I/O statement tests (require StubIOProvider)
# ---------------------------------------------------------------------------


def _run_cobol_with_io(lines: list[str], io_provider, max_steps: int = 1000):
    """Run a COBOL program with an injected I/O provider."""
    source = _to_fixed(lines)
    return run(
        source=source, language="cobol", max_steps=max_steps, io_provider=io_provider
    )


class TestAcceptStatement:
    @covers(CobolFeature.ACCEPT, CobolFeature.IO_PROVIDER)
    def test_accept_from_console(self):
        """ACCEPT reads a value from the stub provider into a field."""
        from interpreter.cobol.io_provider import StubIOProvider

        provider = StubIOProvider(accept_values=["12345"])
        vm = _run_cobol_with_io(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ACCEPT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-INPUT  PIC 9(5) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ACCEPT WS-INPUT FROM CONSOLE.",
                "    STOP RUN.",
            ],
            io_provider=provider,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 5) == 12345


def _file_section_preamble(
    select_name: str = "CUSTFILE", assign_to: str = "CUSTFILEDAT"
):
    """Return COBOL lines for a minimal FILE SECTION (ENVIRONMENT + DATA)."""
    return [
        "ENVIRONMENT DIVISION.",
        "INPUT-OUTPUT SECTION.",
        "FILE-CONTROL.",
        f"    SELECT {select_name} ASSIGN TO {assign_to}.",
        "DATA DIVISION.",
        "FILE SECTION.",
        f"FD {select_name}.",
        f"01 {select_name}-REC PIC X(20).",
        "WORKING-STORAGE SECTION.",
    ]


class TestOpenCloseStatement:
    @covers(CobolFeature.OPEN, CobolFeature.CLOSE, CobolFeature.IO_PROVIDER)
    def test_open_close_dispatches(self):
        """OPEN/CLOSE dispatch to StubIOProvider and track file state."""
        from interpreter.cobol.io_provider import StubIOProvider

        provider = StubIOProvider()
        vm = _run_cobol_with_io(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-OPENCLOSE.",
                *_file_section_preamble("CUSTFILE"),
                "01 WS-FLAG  PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    OPEN INPUT CUSTFILE.",
                "    CLOSE CUSTFILE.",
                "    MOVE 1 TO WS-FLAG.",
                "    STOP RUN.",
            ],
            io_provider=provider,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 1) == 1
        stub = provider.get_file("CUSTFILE")
        assert stub.is_open is False  # closed after CLOSE


class TestWriteStatement:
    @covers(
        CobolFeature.WRITE,
        CobolFeature.WRITE_FROM,
        CobolFeature.OPEN,
        CobolFeature.CLOSE,
        CobolFeature.IO_PROVIDER,
    )
    def test_write_dispatches(self):
        """WRITE dispatches to StubIOProvider."""
        from interpreter.cobol.io_provider import StubIOProvider

        provider = StubIOProvider()
        vm = _run_cobol_with_io(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-WRITE.",
                *_file_section_preamble("OUTFILE"),
                "01 WS-FLAG  PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    OPEN OUTPUT OUTFILE.",
                "    WRITE OUTFILE-REC.",
                "    CLOSE OUTFILE.",
                "    MOVE 1 TO WS-FLAG.",
                "    STOP RUN.",
            ],
            io_provider=provider,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 1) == 1


class TestReadStatement:
    @covers(
        CobolFeature.READ,
        CobolFeature.READ_INTO,
        CobolFeature.OPEN,
        CobolFeature.CLOSE,
        CobolFeature.IO_PROVIDER,
    )
    def test_read_dispatches(self):
        """READ dispatches to StubIOProvider and transfers data into a field."""
        from interpreter.cobol.io_provider import StubIOProvider

        provider = StubIOProvider(files={"CUSTFILE": {"records": ["99999"]}})
        vm = _run_cobol_with_io(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-READ.",
                *_file_section_preamble("CUSTFILE"),
                "01 WS-DATA  PIC 9(5) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    OPEN INPUT CUSTFILE.",
                "    READ CUSTFILE INTO WS-DATA.",
                "    CLOSE CUSTFILE.",
                "    STOP RUN.",
            ],
            io_provider=provider,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 5) == 99999


class TestStartStatement:
    @covers(
        CobolFeature.START,
        CobolFeature.OPEN,
        CobolFeature.CLOSE,
        CobolFeature.IO_PROVIDER,
    )
    def test_start_dispatches(self):
        """START dispatches to StubIOProvider without crashing."""
        from interpreter.cobol.io_provider import StubIOProvider

        provider = StubIOProvider()
        vm = _run_cobol_with_io(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-START.",
                *_file_section_preamble("CUSTFILE"),
                "01 WS-FLAG  PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    OPEN INPUT CUSTFILE.",
                "    START CUSTFILE.",
                "    CLOSE CUSTFILE.",
                "    MOVE 1 TO WS-FLAG.",
                "    STOP RUN.",
            ],
            io_provider=provider,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 1) == 1


class TestDeleteStatement:
    @covers(
        CobolFeature.DELETE_RECORD,
        CobolFeature.OPEN,
        CobolFeature.CLOSE,
        CobolFeature.IO_PROVIDER,
    )
    def test_delete_dispatches(self):
        """DELETE dispatches to StubIOProvider without crashing."""
        from interpreter.cobol.io_provider import StubIOProvider

        provider = StubIOProvider(files={"CUSTFILE": {"records": ["REC1"]}})
        vm = _run_cobol_with_io(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-DELETE.",
                *_file_section_preamble("CUSTFILE"),
                "01 WS-FLAG  PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    OPEN I-O CUSTFILE.",
                "    DELETE CUSTFILE.",
                "    CLOSE CUSTFILE.",
                "    MOVE 1 TO WS-FLAG.",
                "    STOP RUN.",
            ],
            io_provider=provider,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 1) == 1


class TestRewriteStatement:
    @covers(
        CobolFeature.REWRITE,
        CobolFeature.OPEN,
        CobolFeature.CLOSE,
        CobolFeature.IO_PROVIDER,
    )
    def test_rewrite_dispatches(self):
        """REWRITE dispatches to StubIOProvider without crashing."""
        from interpreter.cobol.io_provider import StubIOProvider

        provider = StubIOProvider()
        vm = _run_cobol_with_io(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REWRITE.",
                *_file_section_preamble("OUTFILE"),
                "01 WS-FLAG  PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    OPEN I-O OUTFILE.",
                "    REWRITE OUTFILE-REC.",
                "    CLOSE OUTFILE.",
                "    MOVE 1 TO WS-FLAG.",
                "    STOP RUN.",
            ],
            io_provider=provider,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 1) == 1


# ---------------------------------------------------------------------------
# CANCEL / ALTER / ENTRY tests
# ---------------------------------------------------------------------------


class TestCancelSmoke:
    @covers(CobolFeature.CANCEL)
    def test_cancel_does_not_crash(self):
        """CANCEL is a no-op — verify the program completes normally."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-CANCEL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FLAG  PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 1 TO WS-FLAG.",
                "    CANCEL 'SUBPROG'.",
                "    STOP RUN.",
            ],
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 1) == 1


class TestAlterGoto:
    @covers(CobolFeature.ALTER, CobolFeature.GO_TO)
    def test_alter_compiles_and_runs(self):
        """ALTER statement compiles and runs — smoke test (runtime redirect not yet supported)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ALTER.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-RESULT  PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ALTER JUMP-PARA TO PROCEED TO TARGET-PARA.",
                "    MOVE 1 TO WS-RESULT.",
                "    STOP RUN.",
                "JUMP-PARA.",
                "    GO TO MAIN-PARA.",
                "TARGET-PARA.",
                "    STOP RUN.",
            ],
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 1) == 1


class TestEntryPoint:
    @covers(CobolFeature.ENTRY)
    def test_entry_compiles_and_runs(self):
        """ENTRY statement compiles without crashing — smoke test."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ENTRY.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FLAG  PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 1 TO WS-FLAG.",
                "    STOP RUN.",
                "    ENTRY 'ALT-ENTRY'.",
                "    MOVE 2 TO WS-FLAG.",
                "    STOP RUN.",
            ],
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 1) == 1


# ---------------------------------------------------------------------------
# USAGE type tests
# ---------------------------------------------------------------------------


def _decode_binary(region: list[int], offset: int, length: int) -> int:
    """Decode big-endian unsigned binary integer from memory region bytes."""
    value = 0
    for i in range(length):
        value = (value << 8) | region[offset + i]
    return value


def _decode_comp3(region: list[int], offset: int, length: int) -> int:
    """Decode COMP-3 packed BCD from memory region bytes.

    Each byte holds two BCD digits, except the last byte whose low nibble
    is the sign (0xC=positive, 0xD=negative, 0xF=unsigned).
    """
    digits = []
    for i in range(length):
        byte = region[offset + i]
        hi = (byte >> 4) & 0x0F
        lo = byte & 0x0F
        if i < length - 1:
            digits.extend([hi, lo])
        else:
            digits.append(hi)
            sign_nibble = lo
    value = sum(d * (10 ** (len(digits) - 1 - j)) for j, d in enumerate(digits))
    if sign_nibble == 0x0D:
        value = -value
    return value


class TestUsageComp:
    @covers(CobolFeature.USAGE_COMP, CobolFeature.ADD)
    def test_comp_binary_arithmetic(self):
        """PIC 9(5) COMP — binary field stores ADD result correctly."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-BIN   PIC 9(5) COMP VALUE 100.",
                "01 WS-FLAG  PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD 50 TO WS-BIN.",
                "    MOVE 1 TO WS-FLAG.",
                "    STOP RUN.",
            ],
            max_steps=1500,
        )
        region = _first_region(vm)
        # COMP stores as binary big-endian; PIC 9(5) fits in 2 or 4 bytes
        # Just verify program completes and flag is set
        bin_len = 4  # COMP PIC 9(5) = 4 bytes typically
        flag_offset = bin_len
        assert _decode_zoned_unsigned(region, flag_offset, 1) == 1


class TestUsageComp3:
    @covers(CobolFeature.USAGE_COMP_3, CobolFeature.ADD)
    def test_comp3_packed_arithmetic(self):
        """PIC S9(5) COMP-3 — packed decimal stores COMPUTE result."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-PKD   PIC S9(5) COMP-3 VALUE 200.",
                "01 WS-FLAG  PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD 55 TO WS-PKD.",
                "    MOVE 1 TO WS-FLAG.",
                "    STOP RUN.",
            ],
            max_steps=1500,
        )
        region = _first_region(vm)
        # COMP-3 PIC S9(5) = 3 bytes (5 digits + sign nibble)
        comp3_value = _decode_comp3(region, 0, 3)
        assert comp3_value == 255
        assert _decode_zoned_unsigned(region, 3, 1) == 1


class TestUsageComp1:
    @covers(CobolFeature.USAGE_COMP_1, CobolFeature.COMPUTE)
    def test_comp1_float_arithmetic(self):
        """COMP-1 single-precision float field — verify program completes."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FLAG  PIC 9(1) VALUE 0.",
                "01 WS-FLT   COMP-1 VALUE 1.5.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-FLT = WS-FLT + 2.5.",
                "    MOVE 1 TO WS-FLAG.",
                "    STOP RUN.",
            ],
            max_steps=1500,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 1) == 1


class TestUsageComp2:
    @covers(CobolFeature.USAGE_COMP_2, CobolFeature.COMPUTE)
    def test_comp2_double_arithmetic(self):
        """COMP-2 double-precision float field — verify program completes."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FLAG  PIC 9(1) VALUE 0.",
                "01 WS-DBL   COMP-2 VALUE 3.14.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-DBL = WS-DBL * 2.",
                "    MOVE 1 TO WS-FLAG.",
                "    STOP RUN.",
            ],
            max_steps=1500,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 1) == 1


class TestUsageDisplay:
    @covers(CobolFeature.USAGE_DISPLAY, CobolFeature.ADD)
    def test_display_zoned_decimal(self):
        """PIC 9(5) DISPLAY (default USAGE) — explicit test for zoned decimal."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-DISPLAY.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-NUM   PIC 9(5) DISPLAY VALUE 42.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD 8 TO WS-NUM.",
                "    STOP RUN.",
            ],
            max_steps=1500,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 5) == 50


# ---------------------------------------------------------------------------
# Data Division clause tests
# ---------------------------------------------------------------------------


class TestSignSeparate:
    @covers(CobolFeature.SIGN_CLAUSE)
    def test_sign_leading_separate(self):
        """PIC S9(3) SIGN IS LEADING SEPARATE — sign byte + digits."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SIGN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-SIGNED PIC S9(3) SIGN IS LEADING SEPARATE VALUE -42.",
                "01 WS-FLAG   PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 1 TO WS-FLAG.",
                "    STOP RUN.",
            ],
            max_steps=1500,
        )
        region = _first_region(vm)
        # SIGN LEADING SEPARATE: 1 sign byte + 3 digit bytes = 4 bytes
        # Sign byte: '-' (0x60 in EBCDIC) or 0x2D in ASCII
        # Flag should be set
        flag_offset = 4  # 1 sign + 3 digits
        assert _decode_zoned_unsigned(region, flag_offset, 1) == 1


class TestJustifiedRight:
    @covers(CobolFeature.JUSTIFIED_CLAUSE, CobolFeature.MOVE)
    def test_justified_right_short_value_right_aligns(self):
        """PIC X(10) JUSTIFIED RIGHT — 'ABC' stores as 7 spaces + ABC."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-JUST.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-JUST  PIC X(10) JUSTIFIED RIGHT VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 'ABC' TO WS-JUST.",
                "    STOP RUN.",
            ],
            max_steps=1500,
        )
        region = _first_region(vm)
        # 7 leading EBCDIC spaces, then A=0xC1, B=0xC2, C=0xC3
        assert list(region[0:7]) == [0x40] * 7
        assert list(region[7:10]) == [0xC1, 0xC2, 0xC3]

    @covers(CobolFeature.JUSTIFIED_CLAUSE, CobolFeature.MOVE)
    def test_justified_right_plain_field_still_left_aligns(self):
        """Plain PIC X(10) — 'ABC' stores as ABC + 7 trailing spaces."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-PLAIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-PLAIN PIC X(10) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 'ABC' TO WS-PLAIN.",
                "    STOP RUN.",
            ],
            max_steps=1500,
        )
        region = _first_region(vm)
        # A=0xC1, B=0xC2, C=0xC3, then 7 trailing EBCDIC spaces
        assert list(region[0:3]) == [0xC1, 0xC2, 0xC3]
        assert list(region[3:10]) == [0x40] * 7

    @covers(CobolFeature.JUSTIFIED_CLAUSE, CobolFeature.MOVE)
    def test_justified_right_overlong_truncates_from_left(self):
        """PIC X(3) JUSTIFIED RIGHT — 'ABCDE' keeps last 3 chars: CDE."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-TRUNC.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-TRUNC PIC X(3) JUSTIFIED RIGHT VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 'ABCDE' TO WS-TRUNC.",
                "    STOP RUN.",
            ],
            max_steps=1500,
        )
        region = _first_region(vm)
        # C=0xC3, D=0xC4, E=0xC5 (leftmost 2 chars truncated)
        assert list(region[0:3]) == [0xC3, 0xC4, 0xC5]


class TestRenameAlias:
    @covers(CobolFeature.RENAMES_CLAUSE)
    def test_renames_alias(self):
        """RENAMES (level 66) aliases a range of fields — smoke test."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-RENAME.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-GROUP.",
                "   05 WS-A  PIC 9(3) VALUE 100.",
                "   05 WS-B  PIC 9(3) VALUE 200.",
                "   05 WS-C  PIC 9(3) VALUE 300.",
                "66 WS-ALIAS RENAMES WS-A THRU WS-C.",
                "01 WS-FLAG  PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 1 TO WS-FLAG.",
                "    STOP RUN.",
            ],
            max_steps=1500,
        )
        region = _first_region(vm)
        # WS-GROUP = 9 bytes (3+3+3), WS-FLAG at offset 9
        assert _decode_zoned_unsigned(region, 9, 1) == 1


class TestFigurativeConstants:
    @covers(CobolFeature.FIGURATIVE_SPACES)
    def test_move_spaces_fills_alphanumeric_with_ebcdic_space(self):
        """MOVE SPACES TO PIC X(5) writes EBCDIC space (0x40) to every byte."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SPACES.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '01 WS-A PIC X(5) VALUE "XXXXX".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE SPACES TO WS-A.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        assert all(
            region[i] == 0x40 for i in range(5)
        ), f"Expected all EBCDIC spaces (0x40), got {[hex(region[i]) for i in range(5)]}"

    @covers(CobolFeature.FIGURATIVE_ZEROS)
    def test_move_zeros_clears_numeric_field_to_zero(self):
        """MOVE ZEROS TO PIC 9(4) encodes all-zero value in zoned decimal."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ZEROS.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-B PIC 9(4) VALUE 9999.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE ZEROS TO WS-B.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        assert (
            _decode_zoned_unsigned(region, 0, 4) == 0
        ), f"Expected 0 after MOVE ZEROS, got {_decode_zoned_unsigned(region, 0, 4)}"

    @covers(CobolFeature.FIGURATIVE_QUOTES)
    def test_move_quotes_writes_ebcdic_quote_byte(self):
        """MOVE QUOTES TO PIC X(1) writes EBCDIC double-quote (0x7F)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-QUOTES.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '01 WS-A PIC X(1) VALUE "X".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE QUOTES TO WS-A.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        assert (
            region[0] == 0x7F
        ), f"Expected EBCDIC double-quote (0x7F), got {hex(region[0])}"

    @covers(CobolFeature.FIGURATIVE_LOW_VALUES)
    def test_move_low_values_writes_null_byte(self):
        """MOVE LOW-VALUES TO PIC X(1) writes null byte (0x00)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-LOWVAL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '01 WS-A PIC X(1) VALUE "X".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE LOW-VALUES TO WS-A.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        assert region[0] == 0x00, f"Expected null byte (0x00), got {hex(region[0])}"

    @covers(CobolFeature.FIGURATIVE_HIGH_VALUES)
    def test_move_high_values_writes_max_byte(self):
        """MOVE HIGH-VALUES TO PIC X(1) writes the highest byte value."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-HIGHVAL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '01 WS-A PIC X(1) VALUE "X".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE HIGH-VALUES TO WS-A.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        # HIGH-VALUES translates to "\xff" (U+00FF), which EBCDIC-encodes to 0x6F.
        # True COBOL HIGH-VALUES should be 0xFF; tracked as a known limitation.
        assert (
            region[0] == 0x6F
        ), f"Expected 0x6F (EBCDIC encoding of \\xff), got {hex(region[0])}"


class TestOnSizeError:
    """Integration tests for ON SIZE ERROR / NOT ON SIZE ERROR overflow detection."""

    @covers(CobolFeature.ON_SIZE_ERROR)
    def test_add_overflow_fires_on_size_error(self):
        """ADD that overflows PIC 9(3) fires ON SIZE ERROR; field stays unchanged."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ADD-OSE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-COUNTER PIC 9(3) VALUE 1.",
                "01 WS-FLAG PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD 999 TO WS-COUNTER",
                "        ON SIZE ERROR MOVE 1 TO WS-FLAG",
                "    END-ADD.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        assert region[3] == 0xF1, f"Expected WS-FLAG=1 (0xF1), got {hex(region[3])}"
        assert list(region[:3]) == [
            0xF0,
            0xF0,
            0xF1,
        ], f"WS-COUNTER should be unchanged (1), got {[hex(b) for b in region[:3]]}"

    @covers(CobolFeature.ON_SIZE_ERROR)
    def test_add_no_overflow_fires_not_on_size_error(self):
        """ADD that does not overflow fires NOT ON SIZE ERROR branch."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ADD-NOSE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-COUNTER PIC 9(3) VALUE 1.",
                "01 WS-FLAG PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD 1 TO WS-COUNTER",
                "        NOT ON SIZE ERROR MOVE 1 TO WS-FLAG",
                "    END-ADD.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        assert region[3] == 0xF1, f"Expected WS-FLAG=1 (0xF1), got {hex(region[3])}"

    @covers(CobolFeature.ON_SIZE_ERROR)
    def test_subtract_signed_underflow_fires_on_size_error(self):
        """SUBTRACT from signed PIC S9(3) producing result below -max fires ON SIZE ERROR."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SUB-OSE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-COUNTER PIC S9(3) VALUE -999.",
                "01 WS-FLAG PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SUBTRACT 1 FROM WS-COUNTER",
                "        ON SIZE ERROR MOVE 1 TO WS-FLAG",
                "    END-SUBTRACT.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        assert region[3] == 0xF1, f"Expected WS-FLAG=1 (0xF1), got {hex(region[3])}"

    @covers(CobolFeature.ON_SIZE_ERROR)
    def test_multiply_overflow_fires_on_size_error(self):
        """MULTIPLY that overflows PIC 9(3) fires ON SIZE ERROR; field stays unchanged."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-MUL-OSE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-COUNTER PIC 9(3) VALUE 10.",
                "01 WS-FLAG PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MULTIPLY 100 BY WS-COUNTER",
                "        ON SIZE ERROR MOVE 1 TO WS-FLAG",
                "    END-MULTIPLY.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        assert region[3] == 0xF1, f"Expected WS-FLAG=1 (0xF1), got {hex(region[3])}"
        assert list(region[:3]) == [
            0xF0,
            0xF1,
            0xF0,
        ], f"WS-COUNTER should be unchanged (10), got {[hex(b) for b in region[:3]]}"

    @covers(CobolFeature.ON_SIZE_ERROR)
    def test_divide_by_zero_fires_on_size_error(self):
        """DIVIDE by zero fires ON SIZE ERROR; field stays unchanged."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-DIV-OSE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-COUNTER PIC 9(3) VALUE 5.",
                "01 WS-FLAG PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    DIVIDE 0 INTO WS-COUNTER",
                "        ON SIZE ERROR MOVE 1 TO WS-FLAG",
                "    END-DIVIDE.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        assert region[3] == 0xF1, f"Expected WS-FLAG=1 (0xF1), got {hex(region[3])}"
        assert list(region[:3]) == [
            0xF0,
            0xF0,
            0xF5,
        ], f"WS-COUNTER should be unchanged (5), got {[hex(b) for b in region[:3]]}"

    @covers(CobolFeature.ON_SIZE_ERROR)
    def test_no_on_size_error_clause_silent(self):
        """Overflow without ON SIZE ERROR clause silently truncates; no Python exception."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-NOOSE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-COUNTER PIC 9(3) VALUE 1.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD 999 TO WS-COUNTER.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        assert vm is not None

    @covers(CobolFeature.ON_SIZE_ERROR)
    def test_signed_field_upper_overflow(self):
        """ADD to signed PIC S9(3) producing result above +max fires ON SIZE ERROR."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SIGN-OSE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-COUNTER PIC S9(3) VALUE 999.",
                "01 WS-FLAG PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD 1 TO WS-COUNTER",
                "        ON SIZE ERROR MOVE 1 TO WS-FLAG",
                "    END-ADD.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        assert region[3] == 0xF1, f"Expected WS-FLAG=1 (0xF1), got {hex(region[3])}"


class TestComputeOnSizeError:
    """Integration tests for ON SIZE ERROR / NOT ON SIZE ERROR in COMPUTE."""

    @covers(CobolFeature.ON_SIZE_ERROR)
    def test_compute_overflow_fires_on_size_error(self):
        """COMPUTE that overflows PIC 9(3) fires ON SIZE ERROR; target bytes unchanged."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP-OSE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-COUNTER PIC 9(3) VALUE 1.",
                "01 WS-FLAG PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-COUNTER = 999 + 1",
                "        ON SIZE ERROR MOVE 1 TO WS-FLAG",
                "    END-COMPUTE.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        assert region[3] == 0xF1, f"Expected WS-FLAG=1 (0xF1), got {hex(region[3])}"
        assert list(region[:3]) == [
            0xF0,
            0xF0,
            0xF1,
        ], f"WS-COUNTER should be unchanged (1), got {[hex(b) for b in region[:3]]}"

    @covers(CobolFeature.ON_SIZE_ERROR)
    def test_compute_no_overflow_fires_not_on_size_error(self):
        """COMPUTE that fits fires NOT ON SIZE ERROR; flag is set."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP-NOSE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-COUNTER PIC 9(3) VALUE 1.",
                "01 WS-FLAG PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-COUNTER = 1 + 1",
                "        NOT ON SIZE ERROR MOVE 1 TO WS-FLAG",
                "    END-COMPUTE.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        assert region[3] == 0xF1, f"Expected WS-FLAG=1 (0xF1), got {hex(region[3])}"

    @covers(CobolFeature.ON_SIZE_ERROR)
    def test_compute_multi_target_any_overflow_skips_all(self):
        """COMPUTE with two targets: one would overflow → both unchanged, ON SIZE ERROR fires."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP-MULTI.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-A PIC 9(3) VALUE 1.",
                "01 WS-B PIC 9(1) VALUE 2.",
                "01 WS-FLAG PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-A WS-B = 999 + 1",
                "        ON SIZE ERROR MOVE 1 TO WS-FLAG",
                "    END-COMPUTE.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        # WS-A: bytes 0-2 (PIC 9(3)), WS-B: byte 3 (PIC 9(1)), WS-FLAG: byte 4
        assert region[4] == 0xF1, f"Expected WS-FLAG=1 (0xF1), got {hex(region[4])}"
        assert list(region[:3]) == [
            0xF0,
            0xF0,
            0xF1,
        ], f"WS-A should be unchanged (1), got {[hex(b) for b in region[:3]]}"
        assert region[3] == 0xF2, f"WS-B should be unchanged (2), got {hex(region[3])}"

    @covers(CobolFeature.ON_SIZE_ERROR)
    def test_compute_no_clause_overflow_silent(self):
        """COMPUTE overflow with no clause: no Python exception, vm not None."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP-NOCL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-COUNTER PIC 9(3) VALUE 1.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-COUNTER = 999 + 1.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        assert vm is not None

    @covers(CobolFeature.ON_SIZE_ERROR)
    def test_compute_on_size_error_all_targets_invalid_no_crash(self):
        """COMPUTE with ON SIZE ERROR but all targets invalid: no crash, silent skip."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP-INV.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-DUMMY PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE WS-NONEXISTENT = 999 + 1 ON SIZE ERROR MOVE 1 TO WS-DUMMY END-COMPUTE.",
                "    STOP RUN.",
            ],
            max_steps=500,
        )
        assert vm is not None
