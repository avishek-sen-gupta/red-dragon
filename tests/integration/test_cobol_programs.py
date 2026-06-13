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
from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.project.compiler import compile_directory
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run, run_linked
from interpreter.var_name import VarName
from interpreter.vm.vm_types import Pointer
from tests.covers import covers, NotLanguageFeature
from tests.integration.cobol_helpers import (
    JAR_AVAILABLE as _JAR_AVAILABLE,
    JAR_PATH,
    decode_zoned_unsigned as _decode_zoned_unsigned,
    to_fixed as _to_fixed,
)

pytestmark = pytest.mark.skipif(
    not _JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
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


def _run_cobol(lines: list[str], max_steps: int = 1000):
    """Run a COBOL program through the full pipeline and return VMState."""
    source = _to_fixed(lines)
    return run(source=source, language="cobol", max_steps=max_steps)


def _first_region(vm) -> bytearray:
    """Return the first memory region from the VM state."""
    region = vm.region_get(list(vm.region_keys())[0])
    assert region is not None
    return region


def _decode_alpha(region: bytearray, offset: int, length: int) -> str:
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


class TestValueClauseHexLiteralInit:
    """Hex literal VALUE X'nn' stores RAW bytes, not EBCDIC-translated chars."""

    @covers(CobolFeature.VALUE_CLAUSE, CobolFeature.SECTION_WORKING_STORAGE)
    def test_pic_x_hex_literal_stores_raw_byte(self):
        """01 WS-AID PIC X VALUE X'7D' — byte 0 must be raw 0x7D, not 0xE7 ('X')."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. HEXVAL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-AID   PIC X VALUE X'7D'.",
                "01 WS-OUT   PIC X.",
                "PROCEDURE DIVISION.",
                "    MOVE WS-AID TO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert region[0] == 0x7D


class TestMoveFigurativeRawBytes:
    """MOVE HIGH-VALUES / LOW-VALUES store RAW 0xFF / 0x00, not EBCDIC-translated chars.

    HIGH-VALUES is the highest collating byte (0xFF) and LOW-VALUES the lowest
    (0x00) in every position of the receiver — they must NOT pass through the
    ASCII→EBCDIC alphanumeric encoder (which would turn \\xff into 0x6F). CardDemo
    COTRN02C ADD-TRANSACTION relies on MOVE HIGH-VALUES TO TRAN-ID + STARTBR +
    READPREV to find the highest existing key (red-dragon-raxa).
    """

    @covers(CobolFeature.FIGURATIVE_HIGH_VALUES, CobolFeature.MOVE)
    def test_move_high_values_stores_raw_ff(self):
        """01 F PIC X(4); MOVE HIGH-VALUES TO F — bytes 0-3 must be raw 0xFF."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. HIVAL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 F PIC X(4).",
                "PROCEDURE DIVISION.",
                "    MOVE HIGH-VALUES TO F.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert bytes(region[0:4]) == b"\xff\xff\xff\xff"

    @covers(CobolFeature.FIGURATIVE_LOW_VALUES, CobolFeature.MOVE)
    def test_move_low_values_stores_raw_00(self):
        """01 F PIC X(4); MOVE LOW-VALUES TO F — bytes 0-3 must be raw 0x00."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. LOVAL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 F PIC X(4).",
                "PROCEDURE DIVISION.",
                "    MOVE LOW-VALUES TO F.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert bytes(region[0:4]) == b"\x00\x00\x00\x00"

    @covers(CobolFeature.FIGURATIVE_SPACES, CobolFeature.MOVE)
    def test_move_spaces_stores_ebcdic_space(self):
        """01 F PIC X(4); MOVE SPACES TO F — bytes 0-3 must be EBCDIC space 0x40."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. SPVAL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 F PIC X(4).",
                "PROCEDURE DIVISION.",
                "    MOVE SPACES TO F.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert bytes(region[0:4]) == b"\x40\x40\x40\x40"

    @covers(CobolFeature.FIGURATIVE_ZEROS, CobolFeature.MOVE)
    def test_move_zeros_to_numeric_unchanged(self):
        """01 N PIC 9(4); MOVE ZEROS TO N — decodes to numeric 0 (zoned 0xF0)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. ZEROVAL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 N PIC 9(4).",
                "PROCEDURE DIVISION.",
                "    MOVE ZEROS TO N.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 0


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


class TestMoveNumericDisplayToAlphanumeric:
    """MOVE of a USAGE DISPLAY (zoned) numeric field to an alphanumeric field
    moves the sending field's zoned digit characters, left-justified and
    width-preserving (leading zeros kept) — NOT the int->str form (red-dragon-0fqr).
    """

    @covers(CobolFeature.MOVE, CobolFeature.PIC_CLAUSE)
    def test_move_pic9_11_value_11_to_x11_preserves_leading_zeros(self):
        """MOVE WS-N (PIC 9(11) VALUE 11) TO WS-A (PIC X(11)) -> '00000000011'."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MOVZA1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-N PIC 9(11) VALUE 11.",
                "77 WS-A PIC X(11).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-N TO WS-A.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 11, 11) == "00000000011"

    @covers(CobolFeature.MOVE, CobolFeature.PIC_CLAUSE)
    def test_move_pic9_5_value_42_to_x5_preserves_leading_zeros(self):
        """MOVE WS-N (PIC 9(5) VALUE 42) TO WS-A (PIC X(5)) -> '00042'."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MOVZA2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-N PIC 9(5) VALUE 42.",
                "77 WS-A PIC X(5).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-N TO WS-A.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 5, 5) == "00042"

    @covers(CobolFeature.MOVE, CobolFeature.PIC_CLAUSE)
    def test_move_pic9_5_value_42_to_x3_left_justified_truncates(self):
        """MOVE WS-N (PIC 9(5) VALUE 42) TO WS-A (PIC X(3)): sending zoned chars
        '00042' move left-justified into the 3-char receiver -> '000'."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MOVZA3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-N PIC 9(5) VALUE 42.",
                "77 WS-A PIC X(3).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-N TO WS-A.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 5, 3) == "000"

    @covers(CobolFeature.MOVE, CobolFeature.PIC_CLAUSE)
    def test_move_numeric_to_numeric_unchanged(self):
        """Regression: numeric->numeric is a value move (target-width zero-pad).
        MOVE WS-N (PIC 9(5) VALUE 42) TO WS-M (PIC 9(3)) keeps low-order -> 042."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MOVZN1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-N PIC 9(5) VALUE 42.",
                "77 WS-M PIC 9(3).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-N TO WS-M.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 5, 3) == 42


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

    @covers(CobolFeature.MOVE)
    def test_move_multi_target(self):
        """MOVE x TO A B C distributes the source to every receiving field."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-MMOVE.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A PIC 9(4) VALUE 0.",
                "77 WS-B PIC 9(4) VALUE 0.",
                "77 WS-C PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 42 TO WS-A WS-B WS-C.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 42
        assert _decode_zoned_unsigned(region, 4, 4) == 42
        assert _decode_zoned_unsigned(region, 8, 4) == 42


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

    def _eval_blank(self, when_clause: str) -> str:
        """Run EVALUATE over a space-valued X(1) field with the given WHEN
        clause; return the 4-char WS-R result (HIT if the clause matched)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-EVALBLANK.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-C PIC X(1) VALUE SPACE.",
                "77 WS-R PIC X(4) VALUE 'NONE'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    EVALUATE WS-C",
                f"        WHEN {when_clause}",
                "            MOVE 'HIT ' TO WS-R",
                "        WHEN OTHER",
                "            MOVE 'OTH ' TO WS-R",
                "    END-EVALUATE.",
                "    STOP RUN.",
            ]
        )
        return bytes(_first_region(vm)[1:5]).decode("cp037")

    @covers(CobolFeature.EVALUATE)
    def test_evaluate_when_spaces_matches_blank_field(self):
        """EVALUATE <alpha> WHEN SPACES matches a space-valued field. The old
        string-based WHEN lowering treated SPACES as literal text, so it never
        matched a blank field (red-dragon-z6ad)."""
        assert self._eval_blank("SPACES") == "HIT "

    @covers(CobolFeature.EVALUATE)
    def test_evaluate_when_low_values_matches_blank_field(self):
        # A space field is not LOW-VALUES, so this must NOT match (control).
        assert self._eval_blank("LOW-VALUES") == "OTH "

    @covers(CobolFeature.EVALUATE)
    def test_evaluate_when_literal_space_matches_blank_field(self):
        """A quoted-space WHEN must match a space field; the old split() path
        destroyed the quoted space token."""
        assert self._eval_blank("' '") == "HIT "

    def _eval_stacked(self, value_clause: str) -> str:
        """EVALUATE over WS-C with stacked WHENs:
            WHEN 'Y' WHEN 'y'        -> 'ISY'
            WHEN SPACES WHEN LOW-VALUES -> 'BLK'
            WHEN OTHER               -> 'OTH'
        Returns the 4-char WS-R result for the given WS-C VALUE clause."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-EVALSTACK.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                f"77 WS-C PIC X(1) VALUE {value_clause}.",
                "77 WS-R PIC X(4) VALUE 'NONE'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    EVALUATE WS-C",
                "        WHEN 'Y'",
                "        WHEN 'y'",
                "            MOVE 'ISY ' TO WS-R",
                "        WHEN SPACES",
                "        WHEN LOW-VALUES",
                "            MOVE 'BLK ' TO WS-R",
                "        WHEN OTHER",
                "            MOVE 'OTH ' TO WS-R",
                "    END-EVALUATE.",
                "    STOP RUN.",
            ]
        )
        return bytes(_first_region(vm)[1:5]).decode("cp037")

    @covers(CobolFeature.EVALUATE)
    def test_evaluate_stacked_when_first_value_matches(self):
        """A stacked WHEN matches on its FIRST value."""
        assert self._eval_stacked("'Y'") == "ISY "
        assert self._eval_stacked("SPACE") == "BLK "

    @covers(CobolFeature.EVALUATE)
    def test_evaluate_stacked_when_later_value_matches(self):
        """A stacked WHEN must also match on a NON-first value. The bridge
        previously serialized only whens.get(0), dropping later stacked values
        (here LOW-VALUES), so a 0x00 field fell through to WHEN OTHER."""
        assert self._eval_stacked("LOW-VALUES") == "BLK "

    @covers(CobolFeature.EVALUATE)
    def test_evaluate_stacked_when_no_match_is_other(self):
        assert self._eval_stacked("'Z'") == "OTH "

    @covers(CobolFeature.EVALUATE)
    def test_evaluate_when_literal_char_still_matches(self):
        """Regression guard: a normal char WHEN still matches (the value path
        was already working for non-blank literals)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-EVALCHAR.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-C PIC X(1) VALUE 'Y'.",
                "77 WS-R PIC X(4) VALUE 'NONE'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    EVALUATE WS-C",
                "        WHEN 'Y'",
                "            MOVE 'HIT ' TO WS-R",
                "        WHEN OTHER",
                "            MOVE 'OTH ' TO WS-R",
                "    END-EVALUATE.",
                "    STOP RUN.",
            ]
        )
        assert bytes(_first_region(vm)[1:5]).decode("cp037") == "HIT "


class TestNumericFigurativeComparison:
    """A numeric field compared to the ZERO/ZEROS figurative must compare by
    VALUE (integer 0), not as a zero-filled character string."""

    def _cmp(self, relation: str) -> str:
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-NUMFIG.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-BAL PIC S9(10)V99 VALUE 1000.00.",
                "77 WS-R   PIC X(4) VALUE 'NONE'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                f"    IF {relation}",
                "        MOVE 'YES ' TO WS-R",
                "    ELSE",
                "        MOVE 'NO  ' TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        return bytes(_first_region(vm)[12:16]).decode("cp037")

    @covers(CobolFeature.COMPARISON_OPERATORS)
    def test_positive_not_le_zeros(self):
        # 1000.00 <= ZEROS must be false (matches <= 0 literal behaviour).
        assert self._cmp("WS-BAL <= ZEROS") == "NO  "
        assert self._cmp("WS-BAL <= ZERO") == "NO  "

    @covers(CobolFeature.COMPARISON_OPERATORS)
    def test_positive_gt_zeros(self):
        assert self._cmp("WS-BAL > ZEROS") == "YES "

    @covers(CobolFeature.COMPARISON_OPERATORS)
    def test_equal_zeros(self):
        assert self._cmp("WS-BAL = ZEROS") == "NO  "


class TestSubscriptedConditionName:
    """A level-88 condition name on an OCCURS element, referenced WITH a
    subscript, must evaluate against that element (red-dragon-b02t)."""

    def _sel(self, idx: int) -> str:
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SUB88.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FLAGS PIC X(7) VALUE 'SU     '.",
                "01 WS-ARR REDEFINES WS-FLAGS.",
                "   05 WS-SEL PIC X(1) OCCURS 7 TIMES.",
                "      88 SEL-OK VALUES 'S', 'U'.",
                "01 WS-IDX PIC 9(1) VALUE 1.",
                "01 WS-R   PIC X(4) VALUE 'NONE'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                f"    MOVE {idx} TO WS-IDX.",
                "    EVALUATE TRUE",
                "        WHEN SEL-OK(WS-IDX)",
                "            MOVE 'HIT ' TO WS-R",
                "        WHEN OTHER",
                "            MOVE 'OTH ' TO WS-R",
                "    END-EVALUATE.",
                "    STOP RUN.",
            ]
        )
        # WS-FLAGS/WS-ARR @0 (7), WS-IDX @7 (1), WS-R @8 (4).
        return bytes(_first_region(vm)[8:12]).decode("cp037")

    @covers(CobolFeature.EVALUATE)
    def test_subscripted_88_matches_selected_element(self):
        assert self._sel(1) == "HIT "  # WS-SEL(1) = 'S' -> SEL-OK
        assert self._sel(2) == "HIT "  # WS-SEL(2) = 'U' -> SEL-OK

    @covers(CobolFeature.EVALUATE)
    def test_subscripted_88_no_match_on_blank_element(self):
        assert self._sel(3) == "OTH "  # WS-SEL(3) = ' ' -> not SEL-OK


class TestLevel88AlphanumericValue:
    """A level-88 VALUE shorter than its alphanumeric parent must compare with
    the value space-padded to the parent width (red-dragon-b02t follow-on)."""

    def _run(self, set_msg_line: str) -> str:
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-L88A.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-MSG PIC X(40).",
                "   88 MSG-OK VALUE 'Hello'.",
                "01 WS-R   PIC X(4) VALUE 'NONE'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                f"    {set_msg_line}",
                "    IF MSG-OK",
                "        MOVE 'HIT ' TO WS-R",
                "    ELSE",
                "        MOVE 'OTH ' TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        return bytes(_first_region(vm)[40:44]).decode("cp037")

    @covers(CobolFeature.PIC_CLAUSE)
    def test_88_short_value_matches_padded_parent(self):
        # SET MSG-OK writes 'Hello' + spaces; IF MSG-OK must read TRUE.
        assert self._run("SET MSG-OK TO TRUE.") == "HIT "

    @covers(CobolFeature.PIC_CLAUSE)
    def test_88_no_match_on_different_value(self):
        assert self._run("MOVE 'Goodbye' TO WS-MSG.") == "OTH "


class TestNumericVsAlphanumericField:
    """Comparing a numeric USAGE DISPLAY field to an alphanumeric FIELD compares
    by the numeric's zoned-character form, not its decoded integer
    (COCRDUPC optimistic-lock CVV check: PIC 9(3) vs PIC X(3))."""

    def _cmp(self, num_value: str, alpha_value: str) -> str:
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-NAF.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                f"01 WS-NUM   PIC 9(3) VALUE {num_value}.",
                f"01 WS-ALPHA PIC X(3) VALUE '{alpha_value}'.",
                "01 WS-R     PIC X(4) VALUE 'NONE'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-NUM = WS-ALPHA",
                "        MOVE 'HIT ' TO WS-R",
                "    ELSE",
                "        MOVE 'OTH ' TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        # WS-NUM @0 (3), WS-ALPHA @3 (3), WS-R @6 (4).
        return bytes(_first_region(vm)[6:10]).decode("cp037")

    @covers(CobolFeature.COMPARISON_OPERATORS)
    def test_zoned_numeric_equals_alphanumeric_field(self):
        assert self._cmp("123", "123") == "HIT "

    @covers(CobolFeature.COMPARISON_OPERATORS)
    def test_zoned_numeric_differs_from_alphanumeric_field(self):
        assert self._cmp("123", "456") == "OTH "


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


class TestPerformVaryingAfter:
    """Integration tests for PERFORM VARYING … AFTER … multi-index nested loops."""

    @covers(CobolFeature.PERFORM_VARYING_AFTER)
    def test_perform_varying_after_test_before_2x3(self):
        """PERFORM VARYING I AFTER J (TEST BEFORE) runs body 2×3=6 times.

        WS-I varies 1..2, WS-J varies 1..3 — 6 body executions, each adds 1
        to WS-CNT, so WS-CNT must equal 6 at program exit.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-PVAFTER.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-CNT PIC 9(4) VALUE 0.",
                "01 WS-I   PIC 9(4) VALUE 0.",
                "01 WS-J   PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 2",
                "        AFTER WS-J FROM 1 BY 1 UNTIL WS-J > 3",
                "            ADD 1 TO WS-CNT",
                "    END-PERFORM.",
                "    STOP RUN.",
            ],
            max_steps=5000,
        )
        region = _first_region(vm)
        # WS-CNT at offset 0 (first field, PIC 9(4))
        assert _decode_zoned_unsigned(region, 0, 4) == 6

    @covers(CobolFeature.PERFORM_VARYING_AFTER)
    def test_perform_varying_after_test_before_3_levels(self):
        """PERFORM VARYING I AFTER J AFTER K (TEST BEFORE) runs body 2×2×2=8 times."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-PV3LVL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-CNT PIC 9(4) VALUE 0.",
                "01 WS-I   PIC 9(4) VALUE 0.",
                "01 WS-J   PIC 9(4) VALUE 0.",
                "01 WS-K   PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 2",
                "        AFTER WS-J FROM 1 BY 1 UNTIL WS-J > 2",
                "        AFTER WS-K FROM 1 BY 1 UNTIL WS-K > 2",
                "            ADD 1 TO WS-CNT",
                "    END-PERFORM.",
                "    STOP RUN.",
            ],
            max_steps=10000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 8

    @covers(CobolFeature.PERFORM_VARYING_AFTER, CobolFeature.PERFORM_TEST_AFTER)
    def test_perform_varying_after_test_after_2x3(self):
        """PERFORM VARYING I AFTER J TEST AFTER runs body 2×3=6 times.

        TEST AFTER executes the body before checking UNTIL, so with I ranging
        1..2 and J ranging 1..3 the body still runs 6 times and WS-CNT == 6.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-PVTA.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-CNT PIC 9(4) VALUE 0.",
                "01 WS-I   PIC 9(4) VALUE 0.",
                "01 WS-J   PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 2",
                "        AFTER WS-J FROM 1 BY 1 UNTIL WS-J > 3",
                "        TEST AFTER",
                "            ADD 1 TO WS-CNT",
                "    END-PERFORM.",
                "    STOP RUN.",
            ],
            max_steps=5000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 6


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


class TestInspectRefMod:
    @covers(CobolFeature.INSPECT_REF_MOD, CobolFeature.INSPECT_TALLYING)
    def test_inspect_tallying_ref_mod_start_offset(self):
        """INSPECT TALLYING on a sliced subject with start > 1 verifies 1→0 index conversion.

        WS-DATA(3:3) = 'AAA' (3 A's). Full field has 5 A's. Wrong conversion
        (no -1) would give 0-indexed start=3 → 'AAB' → 2 A's, not 3.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-INSP-RM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-DATA PIC X(8) VALUE "XXAAABBB".',
                "77 WS-COUNT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INSPECT WS-DATA(3:3) TALLYING WS-COUNT",
                '        FOR ALL "A".',
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-DATA(3:3) 1-indexed = 0-indexed[2:5] = "AAA" → 3 A's
        # If index not adjusted: 0-indexed[3:6] = "AAB" → 2 A's
        assert _decode_zoned_unsigned(region, 8, 4) == 3

    @covers(CobolFeature.INSPECT_REF_MOD, CobolFeature.INSPECT_TALLYING)
    def test_inspect_tallying_ref_mod_excludes_outside(self):
        """INSPECT TALLYING counts only within the ref_mod window, not outside.

        WS-DATA(4:4) on 'AAXAAAXX': correct 0-indexed[3:7]='AAAX'→3 A's.
        Wrong conversion (no -1) gives 0-indexed[4:8]='AAXX'→2 A's.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-INSP-RM2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-DATA PIC X(8) VALUE "AAXAAAXX".',
                "77 WS-COUNT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INSPECT WS-DATA(4:4) TALLYING WS-COUNT",
                '        FOR ALL "A".',
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-DATA(4:4) 1-indexed = 0-indexed[3:7] = "AAAX" → 3 A's
        # Wrong (no -1): 0-indexed[4:8] = "AAXX" → 2 A's
        assert _decode_zoned_unsigned(region, 8, 4) == 3

    @covers(CobolFeature.INSPECT_REF_MOD, CobolFeature.INSPECT_REPLACING)
    def test_inspect_replacing_ref_mod_applies_to_slice(self):
        """INSPECT REPLACING with ref_mod replaces only within the sliced region.

        WS-DATA = 'XAAXX' (PIC X(5)). INSPECT WS-DATA(2:3) replaces 'A' by 'B'
        in 0-indexed[1:4] = 'AAX' → 'BBX'. Wrong conversion (no -1) would act
        on 0-indexed[2:5] = 'AXX' → 'BXX', giving byte[1] = X not B.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-INSP-RM3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-DATA PIC X(5) VALUE "XAAXX".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                '    INSPECT WS-DATA(2:3) REPLACING ALL "A" BY "B".',
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # 0-indexed[1:4] = "AAX" → replaced → "BBX"
        # Written back to PIC X(5) field → bytes [B, B, X, ...]
        # EBCDIC: B=0xC2, X=0xE7
        assert region[0] == 0xC2, f"byte[0] should be B (0xC2), got {hex(region[0])}"
        assert region[1] == 0xC2, f"byte[1] should be B (0xC2), got {hex(region[1])}"
        assert region[2] == 0xE7, f"byte[2] should be X (0xE7), got {hex(region[2])}"

    @covers(CobolFeature.INSPECT_TALLYING)
    def test_inspect_tallying_no_ref_mod_unchanged(self):
        """INSPECT TALLYING without ref_mod produces the same result as before."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-INSP-NRML.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-DATA PIC X(5) VALUE "AABAA".',
                "77 WS-COUNT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INSPECT WS-DATA TALLYING WS-COUNT",
                '        FOR ALL "A".',
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 5, 4) == 4


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


def _decode_binary(region: bytearray, offset: int, length: int) -> int:
    """Decode big-endian unsigned binary integer from memory region bytes."""
    value = 0
    for i in range(length):
        value = (value << 8) | region[offset + i]
    return value


def _decode_comp3(region: bytearray, offset: int, length: int) -> int:
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

    @covers(CobolFeature.USAGE_COMP)
    def test_comp_binary_unsigned_stores_value_above_signed_max(self):
        """PIC 9(4) COMP can store 50000 (> signed 2-byte max 32767) without corruption."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP-U.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-UBIN  PIC 9(4) COMP VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 50000 TO WS-UBIN.",
                "    STOP RUN.",
            ],
            max_steps=1500,
        )
        region = _first_region(vm)
        raw = int.from_bytes(region[0:2], "big", signed=False)
        assert raw == 50000


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


class TestSignClause:
    @covers(CobolFeature.SIGN_CLAUSE)
    def test_sign_leading_embedded_places_sign_nibble_in_first_byte(self):
        """PIC S9(3) SIGN IS LEADING: sign zone nibble is in byte 0, not byte 2."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. SGNL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-N PIC S9(3) SIGN IS LEADING.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE -123 TO WS-N.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # SIGN LEADING: sign nibble in high nibble of byte 0 (0xD = negative).
        assert (
            region[0] & 0xF0 == 0xD0
        ), f"expected sign in byte 0, got {region[0:3].hex()}"
        assert (
            region[2] & 0xF0 == 0xF0
        ), f"expected neutral zone in byte 2, got {region[0:3].hex()}"

    @covers(CobolFeature.SIGN_CLAUSE)
    def test_sign_trailing_places_sign_nibble_in_last_byte(self):
        """PIC S9(3) SIGN IS TRAILING (default): sign zone nibble is in byte 2."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. SGNT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-N PIC S9(3).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE -123 TO WS-N.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # SIGN TRAILING (default): sign nibble in high nibble of last byte (0xD = negative).
        assert (
            region[0] & 0xF0 == 0xF0
        ), f"expected neutral zone in byte 0, got {region[0:3].hex()}"
        assert (
            region[2] & 0xF0 == 0xD0
        ), f"expected sign in byte 2, got {region[0:3].hex()}"

    @covers(CobolFeature.SIGN_CLAUSE)
    def test_sign_leading_roundtrip(self):
        """MOVE -123 to SIGN IS LEADING field then MOVE to plain field preserves value."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. SGNLRT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-SRC PIC S9(3) SIGN IS LEADING.",
                "01 WS-DST PIC S9(3).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE -123 TO WS-SRC.",
                "    MOVE WS-SRC TO WS-DST.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-DST at offset 3 (after WS-SRC 3 bytes); sign trailing by default.
        assert region[3] & 0xF0 == 0xF0
        assert region[5] & 0xF0 == 0xD0

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
        # HIGH-VALUES is the raw highest byte (0xFF) in every receiver position —
        # it bypasses ASCII→EBCDIC translation of the figurative fill
        # (red-dragon-raxa).
        assert (
            region[0] == 0xFF
        ), f"Expected raw HIGH-VALUES byte (0xFF), got {hex(region[0])}"


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


class TestComputeRefMod:
    """Integration tests for COMPUTE with reference modification (substring in expressions)."""

    @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
    def test_compute_ref_mod_simple(self):
        """WS-FIELD(1:3) extracts first 3 chars and assigns to result."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP-RM1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD    PIC X(6) VALUE '123ABC'.",
                "01 WS-RESULT   PIC 9(5).",
                "PROCEDURE DIVISION.",
                "    COMPUTE WS-RESULT = WS-FIELD(1:3).",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD: 6 bytes at offset 0; WS-RESULT: 5 bytes at offset 6
        # WS-FIELD(1:3) extracts '123' → 123
        assert _decode_zoned_unsigned(region, 6, 5) == 123

    @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
    def test_compute_ref_mod_offset(self):
        """WS-FIELD(4:3) extracts 3 chars starting at position 4."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP-RM2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD    PIC X(6) VALUE 'XXX456'.",
                "01 WS-RESULT   PIC 9(5).",
                "PROCEDURE DIVISION.",
                "    COMPUTE WS-RESULT = WS-FIELD(4:3).",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD: 6 bytes at offset 0; WS-RESULT: 5 bytes at offset 6
        # WS-FIELD(4:3) extracts '456' → 456
        assert _decode_zoned_unsigned(region, 6, 5) == 456

    @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
    def test_compute_ref_mod_in_expression(self):
        """WS-FIELD(1:3) + 5 adds 5 to the extracted numeric substring."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP-RM3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD    PIC X(5) VALUE '010XY'.",
                "01 WS-RESULT   PIC 9(5).",
                "PROCEDURE DIVISION.",
                "    COMPUTE WS-RESULT = WS-FIELD(1:3) + 5.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD: 5 bytes at offset 0; WS-RESULT: 5 bytes at offset 5
        # WS-FIELD(1:3) extracts '010' → 10, +5 = 15
        assert _decode_zoned_unsigned(region, 5, 5) == 15

    @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
    def test_compute_ref_mod_multiply(self):
        """WS-FIELD(1:3) * 4 multiplies extracted numeric substring."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP-RM4.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD    PIC X(5) VALUE '003XY'.",
                "01 WS-RESULT   PIC 9(5).",
                "PROCEDURE DIVISION.",
                "    COMPUTE WS-RESULT = WS-FIELD(1:3) * 4.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD: 5 bytes at offset 0; WS-RESULT: 5 bytes at offset 5
        # WS-FIELD(1:3) extracts '003' → 3, *4 = 12
        assert _decode_zoned_unsigned(region, 5, 5) == 12

    @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
    def test_compute_no_ref_mod_regression(self):
        """Plain COMPUTE with no ref_mod still works correctly."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-COMP-RM5.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-A        PIC 9(3) VALUE 10.",
                "01 WS-B        PIC 9(3) VALUE 3.",
                "01 WS-RESULT   PIC 9(5).",
                "PROCEDURE DIVISION.",
                "    COMPUTE WS-RESULT = WS-A + WS-B.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A: 3 bytes at offset 0; WS-B: 3 bytes at offset 3; WS-RESULT: 5 bytes at offset 6
        # 10 + 3 = 13
        assert _decode_zoned_unsigned(region, 6, 5) == 13


class TestReferenceModification:
    """Integration tests for COBOL reference modification (substring extraction/replacement).

    Covers MOVE operands with reference modification syntax: WS-FIELD(start:length)
    where start and length can be literals, field references, or arithmetic expressions.
    """

    @covers(
        CobolFeature.MOVE,
        CobolFeature.REFERENCE_MODIFICATION,
    )
    def test_ref_mod_literal_start_length(self):
        """MOVE WS-FIELD(2:3) TO WS-OUT extracts 3 bytes starting at position 2 (1-indexed)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REFMOD-LIT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD PIC X(10) VALUE 'ABCDEFGHIJ'.",
                "01 WS-OUT   PIC X(3).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-FIELD(2:3) TO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD is at offset 0 (10 bytes), WS-OUT is at offset 10 (3 bytes)
        # WS-FIELD(2:3) extracts bytes at indices 1-3 (1-indexed) = "BCD"
        assert _decode_alpha(region, 10, 3) == "BCD"

    @covers(
        CobolFeature.MOVE,
        CobolFeature.REFERENCE_MODIFICATION,
    )
    def test_ref_mod_dataname_start_length(self):
        """MOVE WS-FIELD(WS-A:WS-B) TO WS-OUT uses field values for start and length."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REFMOD-DN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD PIC X(10) VALUE 'ABCDEFGHIJ'.",
                "01 WS-OUT   PIC X(3).",
                "01 WS-A     PIC 9 VALUE 3.",
                "01 WS-B     PIC 9 VALUE 2.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-FIELD(WS-A:WS-B) TO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A=3, WS-B=2; WS-FIELD(3:2) extracts 2 bytes at offset 2 (1-indexed) = "CD"
        # WS-OUT is at offset 10 (after WS-FIELD which is 10 bytes)
        assert _decode_alpha(region, 10, 2) == "CD"

    @covers(
        CobolFeature.MOVE,
        CobolFeature.REFERENCE_MODIFICATION,
        CobolFeature.ARITHMETIC_EXPRESSION,
    )
    def test_ref_mod_add_subtract_expr(self):
        """MOVE WS-FIELD(WS-A + 1:WS-B - 1) TO WS-OUT uses arithmetic expressions."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REFMOD-EXPR.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD PIC X(10) VALUE 'ABCDEFGHIJ'.",
                "01 WS-OUT   PIC X(2).",
                "01 WS-A     PIC 9 VALUE 2.",
                "01 WS-B     PIC 9 VALUE 3.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-FIELD(WS-A + 1:WS-B - 1) TO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A=2, WS-B=3; WS-FIELD(2+1:3-1) = WS-FIELD(3:2) = "CD"
        # WS-OUT is at offset 10 (after WS-FIELD which is 10 bytes)
        assert _decode_alpha(region, 10, 2) == "CD"

    @covers(
        CobolFeature.MOVE,
        CobolFeature.REFERENCE_MODIFICATION,
        CobolFeature.ARITHMETIC_EXPRESSION,
    )
    def test_ref_mod_multiply_expr(self):
        """MOVE WS-FIELD(WS-A * WS-B:WS-C) TO WS-OUT uses multiply in start expression."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REFMOD-MUL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD PIC X(10) VALUE 'ABCDEFGHIJ'.",
                "01 WS-OUT   PIC X(3).",
                "01 WS-A     PIC 9 VALUE 2.",
                "01 WS-B     PIC 9 VALUE 1.",
                "01 WS-C     PIC 9 VALUE 3.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-FIELD(WS-A * WS-B:WS-C) TO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A=2, WS-B=1, WS-C=3; WS-FIELD(2*1:3) = WS-FIELD(2:3) = "BCD"
        # WS-OUT is at offset 10 (after WS-FIELD which is 10 bytes)
        assert _decode_alpha(region, 10, 3) == "BCD"

    @covers(
        CobolFeature.MOVE,
        CobolFeature.REFERENCE_MODIFICATION,
        CobolFeature.ARITHMETIC_EXPRESSION,
    )
    def test_ref_mod_parenthesised_expr(self):
        """MOVE WS-FIELD((WS-A + 1) * 2:WS-B) TO WS-OUT handles parenthesised expressions."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REFMOD-PAREN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD PIC X(10) VALUE 'ABCDEFGHIJ'.",
                "01 WS-OUT   PIC X(3).",
                "01 WS-A     PIC 9 VALUE 1.",
                "01 WS-B     PIC 9 VALUE 3.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-FIELD((WS-A + 1) * 2:WS-B) TO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A=1, WS-B=3; WS-FIELD((1+1)*2:3) = WS-FIELD(4:3) = "DEF"
        # WS-OUT is at offset 10 (after WS-FIELD which is 10 bytes)
        assert _decode_alpha(region, 10, 3) == "DEF"

    @covers(
        CobolFeature.MOVE,
        CobolFeature.REFERENCE_MODIFICATION,
    )
    def test_ref_mod_omitted_length(self):
        """MOVE WS-FIELD(3:) TO WS-OUT (omitted length) extracts from position 3 to end."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REFMOD-OMIT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD PIC X(10) VALUE 'ABCDEFGHIJ'.",
                "01 WS-OUT   PIC X(20).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-FIELD(3:) TO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD(3:) extracts from position 3 to end = "CDEFGHIJ"
        assert _decode_alpha(region, 10, 8) == "CDEFGHIJ"

    @covers(
        CobolFeature.MOVE,
        CobolFeature.REFERENCE_MODIFICATION,
        CobolFeature.ARITHMETIC_EXPRESSION,
    )
    def test_ref_mod_deeply_nested_expr(self):
        """MOVE WS-FIELD((WS-A + WS-B) * (WS-C - WS-A):3) handles deeply nested expressions."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REFMOD-NEST.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD PIC X(10) VALUE 'ABCDEFGHIJ'.",
                "01 WS-OUT   PIC X(3).",
                "01 WS-A     PIC 9 VALUE 1.",
                "01 WS-B     PIC 9 VALUE 1.",
                "01 WS-C     PIC 9 VALUE 3.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-FIELD((WS-A + WS-B) * (WS-C - WS-A):3) TO WS-OUT.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A=1, WS-B=1, WS-C=3; WS-FIELD((1+1)*(3-1):3) = WS-FIELD(4:3) = "DEF"
        # WS-OUT is at offset 10 (after WS-FIELD which is 10 bytes)
        assert _decode_alpha(region, 10, 3) == "DEF"

    @covers(
        CobolFeature.MOVE,
        CobolFeature.REFERENCE_MODIFICATION,
    )
    def test_ref_mod_multiple_in_sequence(self):
        """Multiple MOVE statements with reference modification execute correctly in sequence."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REFMOD-SEQ.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD PIC X(10) VALUE 'ABCDEFGHIJ'.",
                "01 WS-OUT1  PIC X(3).",
                "01 WS-OUT2  PIC X(2).",
                "01 WS-OUT3  PIC X(4).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-FIELD(1:3) TO WS-OUT1.",
                "    MOVE WS-FIELD(5:2) TO WS-OUT2.",
                "    MOVE WS-FIELD(7:4) TO WS-OUT3.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-OUT1: offset 10 (after WS-FIELD's 10 bytes)
        assert _decode_alpha(region, 10, 3) == "ABC"
        # WS-OUT2: offset 13
        assert _decode_alpha(region, 13, 2) == "EF"
        # WS-OUT3: offset 15
        assert _decode_alpha(region, 15, 4) == "GHIJ"

    @covers(
        CobolFeature.MOVE,
        CobolFeature.REFERENCE_MODIFICATION,
    )
    def test_ref_mod_target(self):
        """MOVE WS-SRC TO WS-FIELD(2:3) replaces 3 bytes starting at position 2 (1-indexed)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REFMOD-TGT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD PIC X(10) VALUE 'ABCDEFGHIJ'.",
                "01 WS-SRC   PIC X(3)  VALUE 'XYZ'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE WS-SRC TO WS-FIELD(2:3).",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD starts at offset 0 (10 bytes)
        # MOVE WS-SRC TO WS-FIELD(2:3) replaces positions 2,3,4 with "XYZ"
        # Result: "AXYZEFGHIJ"
        assert _decode_alpha(region, 0, 10) == "AXYZEFGHIJ"

    @covers(
        CobolFeature.MOVE,
        CobolFeature.REFERENCE_MODIFICATION,
    )
    def test_ref_mod_target_literal_source(self):
        """MOVE literal TO WS-FIELD(start:length) replaces substring with literal value."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REFMOD-TGTLIT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FIELD PIC X(10) VALUE 'AAAAAAAAAA'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 'BB' TO WS-FIELD(4:2).",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD starts at offset 0 (10 bytes)
        # MOVE 'BB' TO WS-FIELD(4:2) replaces positions 4 and 5 (1-indexed) with "BB"
        # Result: "AAABBAAAAA"
        assert _decode_alpha(region, 0, 10) == "AAABBAAAAA"


class TestStringRefMod:
    @covers(
        CobolFeature.STRING_VERB,
        CobolFeature.REFERENCE_MODIFICATION,
        CobolFeature.STRING_REF_MOD,
    )
    def test_string_field_ref_mod_basic(self):
        """STRING WS-SRC(2:3) DELIMITED BY SIZE INTO WS-DST — extracts substring BCD."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-STR-RM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-SRC PIC X(5) VALUE 'ABCDE'.",
                "01 WS-DST PIC X(10) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STRING WS-SRC(2:3) DELIMITED BY SIZE",
                "           INTO WS-DST.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-SRC 5 bytes at offset 0, WS-DST 10 bytes at offset 5
        # WS-SRC(2:3) = "BCD" (1-indexed start=2, length=3)
        assert _decode_alpha(region, 5, 3) == "BCD"

    @covers(
        CobolFeature.STRING_VERB,
        CobolFeature.REFERENCE_MODIFICATION,
        CobolFeature.STRING_REF_MOD,
    )
    def test_string_multiple_sendings_one_has_ref_mod(self):
        """Two sendings: first has ref_mod, second does not; concat is correct."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-STR-RM2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-A PIC X(5) VALUE 'ABCDE'.",
                "01 WS-B PIC X(3) VALUE 'XYZ'.",
                "01 WS-DST PIC X(10) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STRING WS-A(2:3) DELIMITED BY SIZE",
                "           WS-B     DELIMITED BY SIZE",
                "           INTO WS-DST.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A 5 bytes at 0, WS-B 3 bytes at 5, WS-DST 10 bytes at 8
        # WS-A(2:3)="BCD", WS-B="XYZ" → concat "BCDXYZ"
        assert _decode_alpha(region, 8, 6) == "BCDXYZ"

    @covers(CobolFeature.STRING_VERB, CobolFeature.STRING_REF_MOD)
    def test_string_no_ref_mod_unchanged(self):
        """STRING without ref_mod still works correctly."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-STR-NORM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-A PIC X(3) VALUE 'ABC'.",
                "01 WS-B PIC X(3) VALUE 'DEF'.",
                "01 WS-DST PIC X(6) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STRING WS-A DELIMITED BY SIZE",
                "           WS-B DELIMITED BY SIZE",
                "           INTO WS-DST.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A 3 bytes at 0, WS-B 3 bytes at 3, WS-DST 6 bytes at 6
        assert _decode_alpha(region, 6, 6) == "ABCDEF"


class TestUnstringRefMod:
    @covers(
        CobolFeature.UNSTRING_VERB,
        CobolFeature.REFERENCE_MODIFICATION,
        CobolFeature.UNSTRING_REF_MOD,
    )
    def test_unstring_source_ref_mod_basic(self):
        """UNSTRING WS-SRC(3:7) splits the substring, not the full field."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-UNSTR-RM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-SRC  PIC X(11) VALUE 'XXABC DEYYY'.",
                "01 WS-A    PIC X(5)  VALUE SPACES.",
                "01 WS-B    PIC X(5)  VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    UNSTRING WS-SRC(3:7) DELIMITED BY SPACES",
                "        INTO WS-A WS-B.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-SRC 11 bytes at offset 0, WS-A 5 bytes at offset 11, WS-B 5 bytes at offset 16
        # WS-SRC(3:7) = "ABC DE" (1-indexed start=3, length=7) → split by SPACES → "ABC", "DE"
        assert _decode_alpha(region, 11, 3) == "ABC"
        assert _decode_alpha(region, 16, 2) == "DE"

    @covers(CobolFeature.UNSTRING_VERB, CobolFeature.UNSTRING_REF_MOD)
    def test_unstring_no_ref_mod_unchanged(self):
        """UNSTRING without ref_mod still works correctly."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-UNSTR-NORM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FULL  PIC X(11) VALUE 'HELLO WORLD'.",
                "01 WS-FIRST PIC X(5)  VALUE SPACES.",
                "01 WS-LAST  PIC X(5)  VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    UNSTRING WS-FULL DELIMITED BY SPACES",
                "        INTO WS-FIRST WS-LAST.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FULL 11 bytes at 0, WS-FIRST 5 at 11, WS-LAST 5 at 16
        assert _decode_alpha(region, 11, 5) == "HELLO"
        assert _decode_alpha(region, 16, 5) == "WORLD"


class TestDisplayRefMod:
    @covers(CobolFeature.DISPLAY_REF_MOD, CobolFeature.DISPLAY)
    def test_display_ref_mod_start_offset(self, capsys):
        """DISPLAY WS-DATA(3:3) on 'XXAAABBB' outputs 'AAA'.

        Correct 0-indexed[2:5]='AAA'. Wrong (no -1): 0-indexed[3:6]='AAB'.
        No ref_mod at all: full field 'XXAAABBB'.
        """
        _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-DISP-RM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-DATA PIC X(8) VALUE "XXAAABBB".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    DISPLAY WS-DATA(3:3).",
                "    STOP RUN.",
            ]
        )
        out = capsys.readouterr().out
        assert out == "AAA", f"Expected 'AAA', got {out!r}"

    @covers(CobolFeature.DISPLAY_REF_MOD, CobolFeature.DISPLAY)
    def test_display_ref_mod_excludes_outside(self, capsys):
        """DISPLAY WS-DATA(4:4) on 'AAXAAAXX' outputs 'AAAX'.

        Correct 0-indexed[3:7]='AAAX'. Wrong (no -1): 0-indexed[4:8]='AAXX'.
        """
        _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-DISP-RM2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-DATA PIC X(8) VALUE "AAXAAAXX".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    DISPLAY WS-DATA(4:4).",
                "    STOP RUN.",
            ]
        )
        out = capsys.readouterr().out
        assert out == "AAAX", f"Expected 'AAAX', got {out!r}"

    @covers(CobolFeature.DISPLAY)
    def test_display_no_ref_mod_unchanged(self, capsys):
        """DISPLAY without ref_mod outputs the full field (regression)."""
        _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-DISP-NRM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                '77 WS-DATA PIC X(5) VALUE "HELLO".',
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    DISPLAY WS-DATA.",
                "    STOP RUN.",
            ]
        )
        out = capsys.readouterr().out
        assert out == "HELLO", f"Expected 'HELLO', got {out!r}"


class TestArithmeticRefMod:
    @covers(CobolFeature.ARITHMETIC_REF_MOD, CobolFeature.ADD)
    def test_add_source_ref_mod(self):
        """ADD WS-FIELD(1:3) TO WS-TOTAL where WS-FIELD='123ABC' adds 123.

        Correct (start-1=0): slice[0:3]='123' → 123.0 added.
        Wrong (no -1): slice[1:4]='23A' → not a number, or wrong value.
        No ref_mod: '123ABC' → not parseable as number.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ADD-RM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-FIELD PIC X(6) VALUE '123ABC'.",
                "77 WS-TOTAL PIC 9(5) VALUE 000.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD WS-FIELD(1:3) TO WS-TOTAL.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD: 6 bytes at offset 0; WS-TOTAL: 5 bytes at offset 6
        assert _decode_zoned_unsigned(region, 6, 5) == 123

    @covers(CobolFeature.ARITHMETIC_REF_MOD, CobolFeature.ADD)
    def test_add_source_ref_mod_offset(self):
        """ADD WS-FIELD(4:3) TO WS-TOTAL where WS-FIELD='XXX456' adds 456.

        Correct (start-1=3): slice[3:6]='456' → 456.
        Wrong (no -1): slice[4:7]='56' (only 2 chars) → 56, not 456.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ADD-RM2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-FIELD PIC X(6) VALUE 'XXX456'.",
                "77 WS-TOTAL PIC 9(5) VALUE 000.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD WS-FIELD(4:3) TO WS-TOTAL.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD: 6 bytes at offset 0; WS-TOTAL: 5 bytes at offset 6
        assert _decode_zoned_unsigned(region, 6, 5) == 456

    @covers(CobolFeature.ADD)
    def test_add_no_ref_mod_unchanged(self):
        """ADD without ref_mod still works correctly (regression)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ADD-NORM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-A    PIC 9(3) VALUE 100.",
                "77 WS-TOTAL PIC 9(5) VALUE 000.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    ADD WS-A TO WS-TOTAL.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-A: 3 bytes at 0; WS-TOTAL: 5 bytes at 3
        assert _decode_zoned_unsigned(region, 3, 5) == 100

    @covers(CobolFeature.ARITHMETIC_REF_MOD, CobolFeature.SUBTRACT)
    def test_subtract_source_ref_mod(self):
        """SUBTRACT WS-FIELD(1:3) FROM WS-TOTAL where WS-FIELD='789XYZ' subtracts 789.

        Correct (start-1=0): slice[0:3]='789' → 999-789=210.
        Wrong (no -1): slice[1:4]='89X' → not a number, or wrong value.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SUB-RM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-FIELD PIC X(6) VALUE '789XYZ'.",
                "77 WS-TOTAL PIC 9(5) VALUE 999.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SUBTRACT WS-FIELD(1:3) FROM WS-TOTAL.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD: 6 bytes at offset 0; WS-TOTAL: 5 bytes at offset 6
        assert _decode_zoned_unsigned(region, 6, 5) == 210

    @covers(CobolFeature.ARITHMETIC_REF_MOD, CobolFeature.SUBTRACT)
    def test_subtract_source_ref_mod_offset(self):
        """SUBTRACT WS-FIELD(4:3) FROM WS-TOTAL where WS-FIELD='ZZZ321' subtracts 321.

        Correct (start-1=3): slice[3:6]='321' → 500-321=179.
        Wrong (no -1): slice[4:7]='21' (only 2 chars) → 500-21=479, not 179.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SUB-RM2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-FIELD PIC X(6) VALUE 'ZZZ321'.",
                "77 WS-TOTAL PIC 9(5) VALUE 500.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SUBTRACT WS-FIELD(4:3) FROM WS-TOTAL.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD: 6 bytes at offset 0; WS-TOTAL: 5 bytes at offset 6
        assert _decode_zoned_unsigned(region, 6, 5) == 179

    @covers(CobolFeature.ARITHMETIC_REF_MOD, CobolFeature.MULTIPLY)
    def test_multiply_source_ref_mod(self):
        """MULTIPLY WS-FIELD(1:3) BY WS-TOTAL where WS-FIELD='003XYZ' multiplies by 3.

        Correct (start-1=0): slice[0:3]='003' → 50*3=150.
        Wrong (no -1): slice[1:4]='03X' → not a number, or wrong value.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-MUL-RM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-FIELD PIC X(6) VALUE '003XYZ'.",
                "77 WS-TOTAL PIC 9(5) VALUE 050.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MULTIPLY WS-FIELD(1:3) BY WS-TOTAL.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD: 6 bytes at offset 0; WS-TOTAL: 5 bytes at offset 6
        assert _decode_zoned_unsigned(region, 6, 5) == 150

    @covers(CobolFeature.ARITHMETIC_REF_MOD, CobolFeature.MULTIPLY)
    def test_multiply_source_ref_mod_offset(self):
        """MULTIPLY WS-FIELD(4:3) BY WS-TOTAL where WS-FIELD='CCC100' multiplies by 100.

        Correct (start-1=3): slice[3:6]='100' → 3*100=300.
        Wrong (no -1): slice[4:7]='00' (only 2 chars) → 3*0=0, not 300.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-MUL-RM2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-FIELD PIC X(6) VALUE 'CCC100'.",
                "77 WS-TOTAL PIC 9(5) VALUE 003.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MULTIPLY WS-FIELD(4:3) BY WS-TOTAL.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-FIELD: 6 bytes at offset 0; WS-TOTAL: 5 bytes at offset 6
        assert _decode_zoned_unsigned(region, 6, 5) == 300


class TestSectionedDataDivision:
    @covers(CobolFeature.SECTION_LINKAGE)
    def test_call_using_symbolic_callee_ws_preserved(self):
        """CALL 'SUBPROG' USING WS-NUM in a single-module program (callee unresolved).

        The subprogram does not exist in this module; the CALL is symbolic and
        the callee never executes.  Verifies that lowering a CALL USING via
        CallWithMemory does not corrupt WS: WS-NUM retains its initial value and
        execution continues past the CALL (MOVE after CALL must run).
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MAIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-NUM   PIC 9(3) VALUE 042.",
                "77 WS-AFTER PIC 9(3) VALUE 0.",
                "PROCEDURE DIVISION.",
                "    CALL 'SUBPROG' USING WS-NUM.",
                "    MOVE 99 TO WS-AFTER.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-NUM (offset 0, 3 bytes) unchanged — params-region copy-in must not clobber WS
        assert _decode_zoned_unsigned(region, 0, 3) == 42
        # MOVE after CALL executed — execution continued past the unresolved CALL
        assert _decode_zoned_unsigned(region, 3, 3) == 99

    @covers(CobolFeature.SECTION_LOCAL_STORAGE)
    def test_local_storage_section_allocates_fresh_region(self):
        """Program with LOCAL-STORAGE SECTION runs without error.

        Verifies lower_sectioned_data_division allocates both WS and LS regions
        and the VM completes without crashing. WS-OUT retains its initial VALUE.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MAIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-OUT PIC 9(2) VALUE 42.",
                "LOCAL-STORAGE SECTION.",
                "77 LS-TEMP PIC 9(3) VALUE 007.",
                "PROCEDURE DIVISION.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-OUT at offset 0, 2 bytes; initial VALUE 42 should be preserved
        assert _decode_zoned_unsigned(region, 0, 2) == 42

    @pytest.mark.skipif(not _JAR_AVAILABLE, reason="ProLeap JAR not found")
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_eighteen_digit_move_is_exact(self):
        """An 18-digit integer field survives MOVE exactly. Before integer
        fields decoded to int, MOVE went through float -> scientific-notation
        string -> COBOL_PREPARE_DIGITS, which could not parse it, leaving the
        destination = 1 instead of the original value (red-dragon-4q25.42)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. BIGT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 BIG PIC 9(18) VALUE 123456789012345678.",
                "77 OUT PIC 9(18) VALUE 0.",
                "PROCEDURE DIVISION.",
                "    MOVE BIG TO OUT.",
                "    STOP RUN.",
            ],
            max_steps=20000,
        )
        region = _first_region(vm)
        # Layout: BIG at offset 0 (18 bytes), OUT at offset 18 (18 bytes).
        assert _decode_zoned_unsigned(region, 0, 18) == 123456789012345678
        assert _decode_zoned_unsigned(region, 18, 18) == 123456789012345678


class TestSubprogramWsPersistence:
    @pytest.mark.skipif(not _JAR_AVAILABLE, reason="ProLeap JAR not found")
    @covers(CobolFeature.CALL_USING, CobolFeature.SECTION_WORKING_STORAGE)
    def test_ws_counter_survives_two_calls(self, tmp_path):
        """SUBPROG increments WS-COUNTER on each CALL; value must be 2 after two calls."""
        (tmp_path / "MAIN.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAIN.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-DUMMY PIC 9(4) VALUE 0.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'SUBPROG'.",
                    "    CALL 'SUBPROG'.",
                    "    STOP RUN.",
                ]
            )
        )

        (tmp_path / "SUBPROG.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. SUBPROG.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-COUNTER PIC 9(4) VALUE 0.",
                    "PROCEDURE DIVISION.",
                    "    ADD 1 TO WS-COUNTER.",
                    "    STOP RUN.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)

        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_main_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=500,
        )

        # Find SUBPROG's singleton and read WS-COUNTER.
        # The singleton TypedValue holds a Pointer; dereference via .base to
        # get the heap Address, then look up the ws_handle field.
        singleton_key = VarName("__prog_SUBPROG")
        singleton_ptr = None
        for frame in reversed(vm.call_stack):
            if singleton_key in frame.local_vars:
                singleton_ptr = frame.local_vars[singleton_key].value
                break
        assert (
            singleton_ptr is not None
        ), "__prog_SUBPROG singleton not found in VM state"

        assert isinstance(
            singleton_ptr, Pointer
        ), f"Expected Pointer, got {type(singleton_ptr)}"
        singleton = vm.heap_get(singleton_ptr.base)
        ws_handle_tv = singleton.fields[FieldName("ws_handle")]
        ws_addr = Address(ws_handle_tv.value)
        region = vm.region_get(ws_addr)
        assert region is not None, f"WS region not found at {ws_addr}"
        counter = _decode_zoned_unsigned(region, offset=0, length=4)
        assert (
            counter == 2
        ), f"Expected WS-COUNTER=2 after two CALL SUBPROG, got {counter}"

    @pytest.mark.skipif(not _JAR_AVAILABLE, reason="ProLeap JAR not found")
    @covers(CobolFeature.SECTION_LOCAL_STORAGE)
    def test_local_storage_reinitializes_on_each_call(self, tmp_path):
        """LOCAL-STORAGE re-initializes to VALUE on every invocation — the
        defining contrast with WORKING-STORAGE, which persists across calls
        (see test_ws_counter_survives_two_calls above).

        LSINC declares LS-COUNTER PIC 9(4) VALUE 5. Each call does
        ADD 1 TO LS-COUNTER then writes the result back through a BY REFERENCE
        linkage param. If LOCAL-STORAGE re-initialises per call, both calls
        compute 5 + 1 = 6. If it wrongly persisted like WORKING-STORAGE, the
        second call would compute 7. MAINCLR captures each call's result in a
        distinct field (WS-A, then WS-B) so both invocations are observable.
        """
        (tmp_path / "MAINCLR.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAINCLR.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-A PIC 9(4) VALUE 0.",
                    "77 WS-B PIC 9(4) VALUE 0.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'LSINC' USING BY REFERENCE WS-A.",
                    "    CALL 'LSINC' USING BY REFERENCE WS-B.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "LSINC.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. LSINC.",
                    "DATA DIVISION.",
                    "LOCAL-STORAGE SECTION.",
                    "77 LS-COUNTER PIC 9(4) VALUE 5.",
                    "LINKAGE SECTION.",
                    "01 LK-OUT PIC 9(4).",
                    "PROCEDURE DIVISION USING LK-OUT.",
                    "    ADD 1 TO LS-COUNTER.",
                    "    MOVE LS-COUNTER TO LK-OUT.",
                    "    GOBACK.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        # Two full CALL round-trips, each with zoned decode + encode (~80
        # instructions apiece) on both sides, comfortably exceed a 500-step
        # budget — a too-small budget halts mid-second-call and looks like a
        # dropped write-back. Give it ample headroom.
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_mainclr_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=5000,
        )

        key = VarName("__prog_MAINCLR")
        ptr = next(
            (f.local_vars[key] for f in reversed(vm.call_stack) if key in f.local_vars),
            None,
        )
        assert ptr is not None, "__prog_MAINCLR singleton not found in VM state"
        region = vm.region_get(
            Address(vm.heap_get(ptr.value.base).fields[FieldName("ws_handle")].value)
        )
        assert region is not None, "MAINCLR WS region not found"

        first = _decode_zoned_unsigned(region, offset=0, length=4)  # WS-A
        second = _decode_zoned_unsigned(region, offset=4, length=4)  # WS-B
        assert first == 6, f"first call: expected 5 + 1 = 6, got {first}"
        assert second == 6, (
            f"second call: expected LS reset to 5 then + 1 = 6, got {second} "
            "(LOCAL-STORAGE did not re-initialise — it behaved like WORKING-STORAGE)"
        )


class TestCallUsingByReference:
    """CALL USING BY REFERENCE: callee modifies LINKAGE field; caller sees updated WS value."""

    @covers(CobolFeature.SECTION_LINKAGE)
    def test_callee_linkage_write_propagates_to_caller_ws(self, tmp_path):
        """BY REFERENCE full round-trip: receipt, mutation, and write-back all verified.

        MAINPROG passes WS-VALUE=5 BY REFERENCE to DOUBLIT.
        DOUBLIT stores the received value in WS-RECEIVED (proves receipt of 5),
        then adds 3 to LS-VALUE (5 → 8), writing back via the shared region.
        After return, MAINPROG's WS-VALUE == 8 (proves mutation propagated back).
        """
        (tmp_path / "MAINPROG.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAINPROG.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-VALUE PIC 9(4) VALUE 5.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'DOUBLIT' USING BY REFERENCE WS-VALUE.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "DOUBLIT.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. DOUBLIT.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-RECEIVED PIC 9(4) VALUE 0.",
                    "LINKAGE SECTION.",
                    "01 LS-VALUE PIC 9(4).",
                    "PROCEDURE DIVISION.",
                    "    MOVE LS-VALUE TO WS-RECEIVED.",
                    "    ADD 3 TO LS-VALUE.",
                    "    STOP RUN.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_mainprog_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=500,
        )

        def _ws(prog_name: str) -> bytearray:
            key = VarName(f"__prog_{prog_name}")
            ptr = next(
                (
                    f.local_vars[key]
                    for f in reversed(vm.call_stack)
                    if key in f.local_vars
                ),
                None,
            )
            assert ptr is not None, f"__prog_{prog_name} not found"
            region = vm.region_get(
                Address(
                    vm.heap_get(ptr.value.base).fields[FieldName("ws_handle")].value
                )
            )
            assert region is not None, f"WS region for {prog_name} not found"
            return region

        # Callee received the correct original value
        doublit_ws = _ws("DOUBLIT")
        received = _decode_zoned_unsigned(doublit_ws, offset=0, length=4)
        assert (
            received == 5
        ), f"DOUBLIT WS-RECEIVED: expected 5 (original WS-VALUE), got {received}"

        # Mutation propagated back to caller via the shared BY REFERENCE region
        mainprog_ws = _ws("MAINPROG")
        ws_value = _decode_zoned_unsigned(mainprog_ws, offset=0, length=4)
        assert (
            ws_value == 8
        ), f"WS-VALUE: expected 8 (5 + 3 written by DOUBLIT), got {ws_value}"

    @pytest.mark.skipif(not _JAR_AVAILABLE, reason="ProLeap JAR not found")
    @covers(CobolFeature.SECTION_LINKAGE)
    def test_linkage_only_subprogram_reads_parameter(self, tmp_path):
        """Regression (red-dragon-irl8): a subprogram with a LINKAGE SECTION and
        NO WORKING-STORAGE SECTION must read its USING BY REFERENCE parameter.

        Previously the linker failed to rebase the COBOL '%rN' registers (the
        regex only matched '%N'), so MAINPROG's and CALLEE's registers collided
        in the merged IR and type inference coerced MAINPROG's byte to float —
        making MOVE 7 a symbolic no-op. CALLEE then read 0 (result 10) instead of
        7 (result 17). A WORKING-STORAGE section in the callee accidentally
        shifted the numbering and hid the bug.

        MAINPROG passes WS-VALUE=7; CALLEE (LINKAGE only) ADD 10; caller sees 17.
        """
        (tmp_path / "MAINPROG.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAINPROG.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-VALUE PIC 9(4) VALUE 7.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'ADDER' USING BY REFERENCE WS-VALUE.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "ADDER.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. ADDER.",
                    "DATA DIVISION.",
                    "LINKAGE SECTION.",
                    "01 LS-VALUE PIC 9(4).",
                    "PROCEDURE DIVISION.",
                    "    ADD 10 TO LS-VALUE.",
                    "    GOBACK.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_mainprog_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=500,
        )

        key = VarName("__prog_MAINPROG")
        ptr = next(
            (f.local_vars[key] for f in reversed(vm.call_stack) if key in f.local_vars),
            None,
        )
        assert ptr is not None, "__prog_MAINPROG not found"
        region = vm.region_get(
            Address(vm.heap_get(ptr.value.base).fields[FieldName("ws_handle")].value)
        )
        assert region is not None
        ws_value = _decode_zoned_unsigned(region, offset=0, length=4)
        assert (
            ws_value == 17
        ), f"WS-VALUE: expected 17 (7 + 10 by LINKAGE-only ADDER), got {ws_value}"


class TestCallUsingByValue:
    """CALL USING BY VALUE: callee receives a copy; caller WS is unchanged after return."""

    @pytest.mark.skipif(not _JAR_AVAILABLE, reason="ProLeap JAR not found")
    @covers(CobolFeature.USING_BY_VALUE)
    def test_by_value_caller_ws_unchanged(self, tmp_path):
        """BY VALUE: callee receives a copy of WS-DATA=5; overwrites it with 99; caller sees 5.

        Two assertions:
        - MODIFIER's WS-RECEIVED == 5: proves the callee received the correct copy.
        - MAINPROG's WS-DATA == 5: proves the overwrite did not propagate back (no copy-back).
        """
        (tmp_path / "MAINPROG.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAINPROG.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-DATA PIC 9(4) VALUE 5.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'MODIFIER' USING BY VALUE WS-DATA.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "MODIFIER.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MODIFIER.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-RECEIVED PIC 9(4) VALUE 0.",
                    "LINKAGE SECTION.",
                    "01 LS-PARAM PIC 9(4).",
                    "PROCEDURE DIVISION.",
                    "    MOVE LS-PARAM TO WS-RECEIVED.",
                    "    MOVE 99 TO LS-PARAM.",
                    "    STOP RUN.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_mainprog_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=500,
        )

        def _ws(prog_name: str) -> bytearray:
            key = VarName(f"__prog_{prog_name}")
            ptr = next(
                (
                    f.local_vars[key]
                    for f in reversed(vm.call_stack)
                    if key in f.local_vars
                ),
                None,
            )
            assert ptr is not None, f"__prog_{prog_name} not found"
            region = vm.region_get(
                Address(
                    vm.heap_get(ptr.value.base).fields[FieldName("ws_handle")].value
                )
            )
            assert region is not None, f"WS region for {prog_name} not found"
            return region

        modifier_ws = _ws("MODIFIER")
        assert modifier_ws is not None
        received = _decode_zoned_unsigned(modifier_ws, offset=0, length=4)
        assert (
            received == 5
        ), f"MODIFIER WS-RECEIVED: expected 5 (copy of WS-DATA), got {received}"

        mainprog_ws = _ws("MAINPROG")
        assert mainprog_ws is not None
        ws_data = _decode_zoned_unsigned(mainprog_ws, offset=0, length=4)
        assert (
            ws_data == 5
        ), f"WS-DATA must be unchanged after BY VALUE call, got {ws_data}"

    @pytest.mark.skipif(not _JAR_AVAILABLE, reason="ProLeap JAR not found")
    @covers(CobolFeature.USING_BY_CONTENT)
    def test_by_content_caller_ws_unchanged(self, tmp_path):
        """BY CONTENT: callee receives a copy of WS-DATA=5; overwrites it with 99; caller sees 5.

        Two assertions:
        - MODIFIER's WS-RECEIVED == 5: proves the callee received the correct copy.
        - MAINPROG's WS-DATA == 5: proves the overwrite did not propagate back (no copy-back).
        """
        (tmp_path / "MAINPROG.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAINPROG.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-DATA PIC 9(4) VALUE 5.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'MODIFIER' USING BY CONTENT WS-DATA.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "MODIFIER.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MODIFIER.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-RECEIVED PIC 9(4) VALUE 0.",
                    "LINKAGE SECTION.",
                    "01 LS-PARAM PIC 9(4).",
                    "PROCEDURE DIVISION.",
                    "    MOVE LS-PARAM TO WS-RECEIVED.",
                    "    MOVE 99 TO LS-PARAM.",
                    "    STOP RUN.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_mainprog_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=500,
        )

        def _ws(prog_name: str) -> bytearray:
            key = VarName(f"__prog_{prog_name}")
            ptr = next(
                (
                    f.local_vars[key]
                    for f in reversed(vm.call_stack)
                    if key in f.local_vars
                ),
                None,
            )
            assert ptr is not None, f"__prog_{prog_name} not found"
            region = vm.region_get(
                Address(
                    vm.heap_get(ptr.value.base).fields[FieldName("ws_handle")].value
                )
            )
            assert region is not None, f"WS region for {prog_name} not found"
            return region

        modifier_ws = _ws("MODIFIER")
        assert modifier_ws is not None
        received = _decode_zoned_unsigned(modifier_ws, offset=0, length=4)
        assert (
            received == 5
        ), f"MODIFIER WS-RECEIVED: expected 5 (copy of WS-DATA), got {received}"

        mainprog_ws = _ws("MAINPROG")
        assert mainprog_ws is not None
        ws_data = _decode_zoned_unsigned(mainprog_ws, offset=0, length=4)
        assert (
            ws_data == 5
        ), f"WS-DATA must be unchanged after BY CONTENT call, got {ws_data}"


class TestCallUsingLinkageRead:
    """Callee reads a value from LINKAGE SECTION into its own WS."""

    @pytest.mark.skipif(not _JAR_AVAILABLE, reason="ProLeap JAR not found")
    @covers(CobolFeature.SECTION_LINKAGE)
    def test_callee_reads_linkage_field_into_ws(self, tmp_path):
        """READER moves LK-INPUT into WS-COPY; MAINPROG verifies WS-COPY == 9.

        MAINPROG passes WS-INPUT=9 BY REFERENCE.
        READER does MOVE LK-INPUT TO WS-COPY.
        After return, READER's WS-COPY must equal 9 (value received via LINKAGE).
        """
        (tmp_path / "MAINPROG.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAINPROG.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-INPUT PIC 9(4) VALUE 9.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'READER' USING BY REFERENCE WS-INPUT.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "READER.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. READER.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-COPY PIC 9(4) VALUE 0.",
                    "LINKAGE SECTION.",
                    "01 LK-INPUT PIC 9(4).",
                    "PROCEDURE DIVISION.",
                    "    MOVE LK-INPUT TO WS-COPY.",
                    "    STOP RUN.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_mainprog_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=500,
        )

        singleton_ptr = None
        for frame in reversed(vm.call_stack):
            if VarName("__prog_READER") in frame.local_vars:
                singleton_ptr = frame.local_vars[VarName("__prog_READER")].value
                break
        assert singleton_ptr is not None, "__prog_READER singleton not found"
        assert isinstance(singleton_ptr, Pointer)
        singleton = vm.heap_get(singleton_ptr.base)
        ws_addr = Address(singleton.fields[FieldName("ws_handle")].value)
        region = vm.region_get(ws_addr)
        assert region is not None

        ws_copy = _decode_zoned_unsigned(region, offset=0, length=4)
        assert ws_copy == 9, f"WS-COPY: expected 9 (read from LK-INPUT), got {ws_copy}"

    @pytest.mark.skipif(not _JAR_AVAILABLE, reason="ProLeap JAR not found")
    @covers(CobolFeature.SECTION_LINKAGE, CobolFeature.CALL_USING)
    def test_callee_reads_second_linkage_field(self, tmp_path):
        """LINKAGE field at non-zero offset (LK-B, offset 4) is correctly read.

        MAINPROG passes WS-A=3 and WS-B=7 BY REFERENCE.
        READER moves LK-B (second LINKAGE field, byte offset 4) into WS-COPY.
        Expected: WS-COPY == 7, proving the non-zero LINKAGE offset is decoded.
        """
        (tmp_path / "MAINPROG.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAINPROG.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-A PIC 9(4) VALUE 3.",
                    "77 WS-B PIC 9(4) VALUE 7.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'READER' USING BY REFERENCE WS-A WS-B.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "READER.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. READER.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-COPY PIC 9(4) VALUE 0.",
                    "LINKAGE SECTION.",
                    "01 LK-A PIC 9(4).",
                    "01 LK-B PIC 9(4).",
                    "PROCEDURE DIVISION.",
                    "    MOVE LK-B TO WS-COPY.",
                    "    STOP RUN.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_mainprog_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=1000,
        )

        singleton_ptr = None
        for frame in reversed(vm.call_stack):
            if VarName("__prog_READER") in frame.local_vars:
                singleton_ptr = frame.local_vars[VarName("__prog_READER")].value
                break
        assert singleton_ptr is not None, "__prog_READER singleton not found"
        assert isinstance(singleton_ptr, Pointer)
        singleton = vm.heap_get(singleton_ptr.base)
        ws_addr = Address(singleton.fields[FieldName("ws_handle")].value)
        region = vm.region_get(ws_addr)
        assert region is not None

        ws_copy = _decode_zoned_unsigned(region, offset=0, length=4)
        assert ws_copy == 7, f"WS-COPY: expected 7 (LK-B at offset 4), got {ws_copy}"

    @pytest.mark.skipif(not _JAR_AVAILABLE, reason="ProLeap JAR not found")
    @covers(CobolFeature.SECTION_LINKAGE, CobolFeature.CALL_USING)
    def test_callee_linkage_wider_than_caller_arg_reads_zero_pad(self, tmp_path):
        """Callee LINKAGE field wider than caller's USING arg: overrun reads as zeroes.

        MAINPROG passes WS-SMALL PIC 9(2) VALUE 7 (2 bytes) BY REFERENCE.
        READER declares LK-BIG PIC 9(4) (4 bytes) — wider than the params region.
        Reading LK-BIG must not crash; the 2 overrun bytes read as zoned zeroes,
        so the decoded value is 0700 (digits 0,7 from WS-SMALL, then 0,0 padding).
        """
        (tmp_path / "MAINPROG.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAINPROG.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-SMALL PIC 9(2) VALUE 7.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'READER' USING BY REFERENCE WS-SMALL.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "READER.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. READER.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-COPY PIC 9(4) VALUE 0.",
                    "LINKAGE SECTION.",
                    "01 LK-BIG PIC 9(4).",
                    "PROCEDURE DIVISION.",
                    "    MOVE LK-BIG TO WS-COPY.",
                    "    STOP RUN.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_mainprog_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=1000,
        )

        singleton_ptr = None
        for frame in reversed(vm.call_stack):
            if VarName("__prog_READER") in frame.local_vars:
                singleton_ptr = frame.local_vars[VarName("__prog_READER")].value
                break
        assert singleton_ptr is not None, "__prog_READER singleton not found"
        assert isinstance(singleton_ptr, Pointer)
        singleton = vm.heap_get(singleton_ptr.base)
        ws_addr = Address(singleton.fields[FieldName("ws_handle")].value)
        region = vm.region_get(ws_addr)
        assert region is not None

        # WS-SMALL=7 occupies the first 2 bytes; the 2 overrun bytes read as zero,
        # so LK-BIG decodes as 0700 (no crash from the out-of-bounds read).
        ws_copy = _decode_zoned_unsigned(region, offset=0, length=4)
        assert (
            ws_copy == 700
        ), f"WS-COPY: expected 700 (zero-padded overrun), got {ws_copy}"


class TestGobackExitProgram:
    """GOBACK and EXIT PROGRAM must return control to the caller, not halt the VM."""

    @pytest.mark.skipif(not _JAR_AVAILABLE, reason="ProLeap JAR not found")
    @covers(CobolFeature.GOBACK)
    def test_goback_in_subprogram_returns_to_caller(self, tmp_path):
        """Subprogram ending with GOBACK returns; MAIN continues and sets WS-RESULT=42."""
        (tmp_path / "MAINPROG.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAINPROG.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-RESULT PIC 9(4) VALUE 0.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'HELPER'.",
                    "    MOVE 42 TO WS-RESULT.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "HELPER.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. HELPER.",
                    "PROCEDURE DIVISION.",
                    "    GOBACK.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_mainprog_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=500,
        )

        singleton_ptr = None
        for frame in reversed(vm.call_stack):
            if VarName("__prog_MAINPROG") in frame.local_vars:
                singleton_ptr = frame.local_vars[VarName("__prog_MAINPROG")].value
                break
        assert singleton_ptr is not None
        assert isinstance(singleton_ptr, Pointer)
        ws_addr = Address(
            vm.heap_get(singleton_ptr.base).fields[FieldName("ws_handle")].value
        )
        region = vm.region_get(ws_addr)
        assert region is not None
        ws_result = _decode_zoned_unsigned(region, offset=0, length=4)
        assert (
            ws_result == 42
        ), f"WS-RESULT: expected 42 (MAIN continued after GOBACK), got {ws_result}"

    @pytest.mark.skipif(not _JAR_AVAILABLE, reason="ProLeap JAR not found")
    @covers(CobolFeature.EXIT_PROGRAM)
    def test_exit_program_in_subprogram_returns_to_caller(self, tmp_path):
        """Subprogram ending with EXIT PROGRAM returns; MAIN continues and sets WS-RESULT=99."""
        (tmp_path / "MAINPROG.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAINPROG.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-RESULT PIC 9(4) VALUE 0.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'HELPER'.",
                    "    MOVE 99 TO WS-RESULT.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "HELPER.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. HELPER.",
                    "PROCEDURE DIVISION.",
                    "    EXIT PROGRAM.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_mainprog_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=500,
        )

        singleton_ptr = None
        for frame in reversed(vm.call_stack):
            if VarName("__prog_MAINPROG") in frame.local_vars:
                singleton_ptr = frame.local_vars[VarName("__prog_MAINPROG")].value
                break
        assert singleton_ptr is not None
        assert isinstance(singleton_ptr, Pointer)
        ws_addr = Address(
            vm.heap_get(singleton_ptr.base).fields[FieldName("ws_handle")].value
        )
        region = vm.region_get(ws_addr)
        assert region is not None
        ws_result = _decode_zoned_unsigned(region, offset=0, length=4)
        assert (
            ws_result == 99
        ), f"WS-RESULT: expected 99 (MAIN continued after EXIT PROGRAM), got {ws_result}"

    @pytest.mark.skipif(not _JAR_AVAILABLE, reason="ProLeap JAR not found")
    @covers(CobolFeature.GOBACK, CobolFeature.CALL_USING, CobolFeature.SECTION_LINKAGE)
    def test_goback_after_linkage_write_propagates_to_caller(self, tmp_path):
        """Callee writes to LINKAGE field then GOBACKs; caller sees the updated value.

        MAINPROG passes WS-VALUE=5 BY REFERENCE to SETTER.
        SETTER moves 88 into LK-VALUE (its LINKAGE field), then GOBACKs.
        Copy-back writes 88 into MAINPROG's WS-VALUE.
        WS-FLAG is set to 1 after the CALL, proving MAIN continued executing.
        """
        (tmp_path / "MAINPROG.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAINPROG.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-VALUE PIC 9(4) VALUE 5.",
                    "77 WS-FLAG  PIC 9(4) VALUE 0.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'SETTER' USING BY REFERENCE WS-VALUE.",
                    "    MOVE 1 TO WS-FLAG.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "SETTER.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. SETTER.",
                    "DATA DIVISION.",
                    "LINKAGE SECTION.",
                    "01 LK-VALUE PIC 9(4).",
                    "PROCEDURE DIVISION.",
                    "    MOVE 88 TO LK-VALUE.",
                    "    GOBACK.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_mainprog_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=500,
        )

        singleton_ptr = None
        for frame in reversed(vm.call_stack):
            if VarName("__prog_MAINPROG") in frame.local_vars:
                singleton_ptr = frame.local_vars[VarName("__prog_MAINPROG")].value
                break
        assert singleton_ptr is not None
        assert isinstance(singleton_ptr, Pointer)
        ws_addr = Address(
            vm.heap_get(singleton_ptr.base).fields[FieldName("ws_handle")].value
        )
        region = vm.region_get(ws_addr)
        assert region is not None
        # WS-VALUE at offset 0: SETTER wrote 88 via LK-VALUE; copy-back propagated it
        ws_value = _decode_zoned_unsigned(region, offset=0, length=4)
        assert (
            ws_value == 88
        ), f"WS-VALUE: expected 88 (set by SETTER via LINKAGE), got {ws_value}"
        # WS-FLAG at offset 4: MAIN executed MOVE 1 TO WS-FLAG after the CALL returned
        ws_flag = _decode_zoned_unsigned(region, offset=4, length=4)
        assert (
            ws_flag == 1
        ), f"WS-FLAG: expected 1 (MAIN continued after GOBACK), got {ws_flag}"


class TestEvaluateFigurativeCondition:
    @covers(
        CobolFeature.EVALUATE,
        CobolFeature.FIGURATIVE_SPACES,
        CobolFeature.FIGURATIVE_LOW_VALUES,
    )
    def test_evaluate_true_when_field_equals_spaces_or_low_values(self):
        """EVALUATE TRUE WHEN WS-X = SPACES OR LOW-VALUES fires only when blank."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-EVALFIG.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-X PIC X(8) VALUE 'AAAAAAAA'.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE SPACES TO WS-X",
                "    EVALUATE TRUE",
                "        WHEN WS-X = SPACES OR LOW-VALUES",
                "            MOVE 1 TO WS-R",
                "        WHEN OTHER",
                "            MOVE 2 TO WS-R",
                "    END-EVALUATE.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # WS-X is blank (SPACES), so the WHEN branch must fire → WS-R = 1.
        assert _decode_zoned_unsigned(region, 8, 4) == 1

    @covers(
        CobolFeature.EVALUATE,
        CobolFeature.FIGURATIVE_SPACES,
    )
    def test_evaluate_true_when_field_not_spaces_takes_other(self):
        """When WS-X holds non-blank data the figurative WHEN must NOT fire."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-EVALFIG2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-X PIC X(8) VALUE SPACES.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 'USER0001' TO WS-X",
                "    EVALUATE TRUE",
                "        WHEN WS-X = SPACES OR LOW-VALUES",
                "            MOVE 1 TO WS-R",
                "        WHEN OTHER",
                "            MOVE 2 TO WS-R",
                "    END-EVALUATE.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # WS-X holds 'USER0001' (not blank) → WHEN OTHER → WS-R = 2.
        assert _decode_zoned_unsigned(region, 8, 4) == 2


class TestIfOfQualifiedFigurative:
    @covers(
        CobolFeature.IF_ELSE,
        CobolFeature.FIGURATIVE_SPACES,
    )
    def test_if_of_qualified_field_equals_spaces(self):
        """IF USERIDI OF COSGN0AI = SPACES (OF-qualified) lowers correctly."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-OFQUAL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 COSGN0AI.",
                "   05 USERIDI PIC X(8) VALUE 'XXXXXXXX'.",
                "77 WS-R PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE SPACES TO USERIDI OF COSGN0AI",
                "    IF USERIDI OF COSGN0AI = SPACES",
                "        MOVE 1 TO WS-R",
                "    ELSE",
                "        MOVE 2 TO WS-R",
                "    END-IF.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # USERIDI is blank → IF fires → WS-R = 1. WS-R is at offset 8 (after X(8)).
        assert _decode_zoned_unsigned(region, 8, 4) == 1


class TestIntrinsicFunctionUpperCase:
    @covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.MOVE)
    def test_upper_case_single_target(self):
        """MOVE FUNCTION UPPER-CASE(WS-IN) TO WS-OUT uppercases the value."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-UC1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-IN  PIC X(6) VALUE 'abc123'.",
                "77 WS-OUT PIC X(6) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE FUNCTION UPPER-CASE(WS-IN) TO WS-OUT.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # WS-OUT is at offset 6 (after WS-IN X(6)).
        assert _decode_alpha(region, 6, 6) == "ABC123"

    @covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.MOVE)
    def test_upper_case_multiple_targets(self):
        """MOVE FUNCTION UPPER-CASE(WS-IN) TO WS-A WS-B uppercases both."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-UC2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-IN PIC X(3) VALUE 'abc'.",
                "77 WS-A  PIC X(3) VALUE SPACES.",
                "77 WS-B  PIC X(3) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE FUNCTION UPPER-CASE(WS-IN) TO WS-A WS-B.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 3, 3) == "ABC"
        assert _decode_alpha(region, 6, 3) == "ABC"

    @covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.MOVE)
    def test_upper_case_of_qualified_argument(self):
        """FUNCTION UPPER-CASE(FLD OF GRP) resolves the qualified field's VALUE.

        The OF-qualified argument must be resolved to the leaf field (FLD-A),
        not flattened to the qualified-name text.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-UCQ.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 GRP-B.",
                "   05 FLD-A PIC X(6) VALUE 'abc123'.",
                "77 WS-OUT PIC X(6) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE FUNCTION UPPER-CASE(FLD-A OF GRP-B) TO WS-OUT.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # WS-OUT is at offset 6 (after GRP-B/FLD-A X(6)).
        assert _decode_alpha(region, 6, 6) == "ABC123"


class TestIntrinsicFunctionLowerCase:
    @covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.MOVE)
    def test_lower_case_single_target(self):
        """MOVE FUNCTION LOWER-CASE(WS-IN) TO WS-OUT lowercases the value."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-LC1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-IN  PIC X(3) VALUE 'ABC'.",
                "77 WS-OUT PIC X(3) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE FUNCTION LOWER-CASE(WS-IN) TO WS-OUT.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # WS-OUT at offset 3. EBCDIC lowercase: a=0x81, b=0x82, c=0x83.
        assert region[3] == 0x81
        assert region[4] == 0x82
        assert region[5] == 0x83


class TestIntrinsicFunctionCurrentDate:
    @covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.MOVE)
    def test_current_date_format(self):
        """MOVE FUNCTION CURRENT-DATE TO a PIC X(21) field yields a 21-char timestamp."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-CD1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-DATE PIC X(21) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE FUNCTION CURRENT-DATE TO WS-DATE.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        decoded = _decode_alpha(region, 0, 21)
        # First 8 chars are the YYYYMMDD date — all digits, plausible year.
        assert decoded[:8].isdigit()
        year = int(decoded[:4])
        assert 2020 <= year <= 2100


class TestSetConditionNameToTrue:
    @covers(CobolFeature.SET_TO, CobolFeature.LEVEL_88_CONDITION)
    def test_set_88_to_true_flips_flag(self):
        """SET <88-name> TO TRUE writes the condition VALUE into its parent field."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SET88.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FLG PIC X VALUE 'N'.",
                "   88 FLG-ON  VALUE 'Y'.",
                "   88 FLG-OFF VALUE 'N'.",
                "01 WS-R PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SET FLG-ON TO TRUE.",
                "    IF FLG-ON MOVE 1 TO WS-R ELSE MOVE 2 TO WS-R END-IF.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # WS-R is one zoned digit at offset 1 (WS-FLG occupies byte 0).
        assert _decode_zoned_unsigned(region, 1, 1) == 1

    @covers(CobolFeature.SET_TO, CobolFeature.LEVEL_88_CONDITION)
    def test_set_88_off_makes_other_condition_false(self):
        """SET <88-name(OFF)> TO TRUE leaves the sibling ON condition false."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SET88B.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FLG PIC X VALUE 'Y'.",
                "   88 FLG-ON  VALUE 'Y'.",
                "   88 FLG-OFF VALUE 'N'.",
                "01 WS-R PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SET FLG-OFF TO TRUE.",
                "    IF FLG-ON MOVE 1 TO WS-R ELSE MOVE 2 TO WS-R END-IF.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # FLG-OFF set to TRUE writes 'N' → FLG-ON ('Y') is false → WS-R == 2.
        assert _decode_zoned_unsigned(region, 1, 1) == 2

    @covers(CobolFeature.SET_TO, CobolFeature.LEVEL_88_CONDITION)
    def test_set_multiple_88_targets_to_true(self):
        """SET A B TO TRUE writes each condition's VALUE into its own parent."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SET88M.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-A PIC X VALUE 'N'.",
                "   88 A-ON  VALUE 'Y'.",
                "01 WS-B PIC X VALUE 'N'.",
                "   88 B-ON  VALUE 'Y'.",
                "01 WS-R PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SET A-ON B-ON TO TRUE.",
                "    IF A-ON AND B-ON MOVE 1 TO WS-R ELSE MOVE 2 TO WS-R END-IF.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # WS-R at offset 2 (WS-A byte 0, WS-B byte 1).
        assert _decode_zoned_unsigned(region, 2, 1) == 1

    @covers(CobolFeature.SET_TO, CobolFeature.LEVEL_88_CONDITION)
    def test_set_88_on_third_adjacent_flag_writes_at_correct_offset(self):
        """SET <88-on-3rd-of-3-adjacent-X(1)-flags, multiple 88s, digit VALUEs>.

        Regression for red-dragon-0sq2 (mirrors COACTVWC WS-EDIT-ACCT-FLAG):
        three consecutive PIC X(1) flags in ONE group, each with several 88s whose
        VALUEs are digit characters ('0'/'1'). SET F3-VALID TO TRUE must write the
        character '1' into F3 (the 3rd byte), not the int 1 (which the alphanumeric
        encoder silently dropped, leaving the byte unchanged).
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SET88ADJ.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FLAGS.",
                "   05 F1 PIC X VALUE 'A'.",
                "      88 F1-NOTOK VALUE '0'.",
                "      88 F1-OK    VALUE '1'.",
                "   05 F2 PIC X VALUE 'B'.",
                "      88 F2-NOTOK VALUE '0'.",
                "      88 F2-OK    VALUE '1'.",
                "   05 F3 PIC X VALUE 'C'.",
                "      88 F3-NOTOK VALUE '0'.",
                "      88 F3-OK    VALUE '1'.",
                "      88 F3-BLANK VALUE ' '.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SET F3-OK TO TRUE.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # Group WS-FLAGS occupies bytes 0..2: F1=byte0, F2=byte1, F3=byte2.
        assert _decode_alpha(region, 0, 1) == "A"
        assert _decode_alpha(region, 1, 1) == "B"
        assert _decode_alpha(region, 2, 1) == "1"

    @covers(CobolFeature.SET_TO, CobolFeature.LEVEL_88_CONDITION)
    def test_set_88_on_first_adjacent_flag_writes_at_offset_zero(self):
        """SET <88-on-1st-flag> writes byte 0 only; siblings unchanged (regression)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-SET88ADJ1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FLAGS.",
                "   05 F1 PIC X VALUE 'A'.",
                "      88 F1-NOTOK VALUE '0'.",
                "      88 F1-OK    VALUE '1'.",
                "   05 F2 PIC X VALUE 'B'.",
                "      88 F2-NOTOK VALUE '0'.",
                "      88 F2-OK    VALUE '1'.",
                "   05 F3 PIC X VALUE 'C'.",
                "      88 F3-NOTOK VALUE '0'.",
                "      88 F3-OK    VALUE '1'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SET F1-OK TO TRUE.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 0, 1) == "1"
        assert _decode_alpha(region, 1, 1) == "B"
        assert _decode_alpha(region, 2, 1) == "C"

    @covers(CobolFeature.SET_TO, CobolFeature.LEVEL_88_CONDITION)
    def test_if_88_with_digit_char_value_on_pic_x_parent_is_true(self):
        """IF <88 with a DIGIT-CHARACTER VALUE> on a PIC X parent reads TRUE.

        Regression (read side of red-dragon-0sq2 / COACTVWC FOUND-ACCT-IN-MASTER):
        SET F-OK TO TRUE writes the CHARACTER '1' into a PIC X(1) flag. The IF-88
        test decodes that byte as the STRING "1"; the 88 VALUE '1' must therefore
        also be compared as the character "1", NOT coerced to the integer 1 (which
        made the str-vs-int compare always false, so the gated MOVEs were skipped).
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-IF88DIGIT.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FLG PIC X VALUE '0'.",
                "   88 FLG-OK VALUE '1'.",
                "01 WS-R PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    SET FLG-OK TO TRUE.",
                "    IF FLG-OK MOVE 1 TO WS-R ELSE MOVE 2 TO WS-R END-IF.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # FLG-OK set to TRUE writes '1' → IF FLG-OK must be TRUE → WS-R == 1.
        assert _decode_zoned_unsigned(region, 1, 1) == 1


class TestClassConditions:
    """IS [NOT] NUMERIC / ALPHABETIC class tests (red-dragon-pz9g.20)."""

    @covers(CobolFeature.CLASS_CONDITION, CobolFeature.IF_ELSE)
    def test_numeric_true_for_digits(self):
        """WS-X PIC X(2) = '01' IS NUMERIC → TRUE → WS-R == 1."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-CLSNUM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-X PIC X(2) VALUE '01'.",
                "01 WS-R PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-X IS NUMERIC MOVE 1 TO WS-R ELSE MOVE 2 TO WS-R END-IF.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 2, 1) == 1

    @covers(CobolFeature.CLASS_CONDITION, CobolFeature.IF_ELSE)
    def test_numeric_false_for_letters(self):
        """WS-X = 'AB' IS NUMERIC → FALSE → WS-R == 2."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-CLSNUMF.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-X PIC X(2) VALUE 'AB'.",
                "01 WS-R PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-X IS NUMERIC MOVE 1 TO WS-R ELSE MOVE 2 TO WS-R END-IF.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 2, 1) == 2

    @covers(CobolFeature.CLASS_CONDITION, CobolFeature.LOGICAL_NOT)
    def test_not_numeric_inverts(self):
        """WS-X = 'AB' IS NOT NUMERIC → TRUE → WS-R == 1."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-CLSNNUM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-X PIC X(2) VALUE 'AB'.",
                "01 WS-R PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-X IS NOT NUMERIC",
                "       MOVE 1 TO WS-R ELSE MOVE 2 TO WS-R END-IF.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 2, 1) == 1

    @covers(CobolFeature.CLASS_CONDITION, CobolFeature.IF_ELSE)
    def test_alphabetic_true_for_letters(self):
        """WS-A = 'AB' IS ALPHABETIC → TRUE → WS-R == 1."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-CLSALP.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-A PIC X(2) VALUE 'AB'.",
                "01 WS-R PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-A IS ALPHABETIC",
                "       MOVE 1 TO WS-R ELSE MOVE 2 TO WS-R END-IF.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 2, 1) == 1

    @covers(CobolFeature.CLASS_CONDITION, CobolFeature.IF_ELSE)
    def test_alphabetic_false_for_digits(self):
        """WS-A = '01' IS ALPHABETIC → FALSE → WS-R == 2."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-CLSALPF.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-A PIC X(2) VALUE '01'.",
                "01 WS-R PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-A IS ALPHABETIC",
                "       MOVE 1 TO WS-R ELSE MOVE 2 TO WS-R END-IF.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 2, 1) == 2


class TestPerformVaryingLengthOfAndRefModCondition:
    @covers(CobolFeature.PERFORM_VARYING)
    def test_perform_varying_from_length_of(self):
        """PERFORM VARYING I FROM LENGTH OF WS-S BY -1 UNTIL I < 1 iterates 4x.

        FROM LENGTH OF WS-S (PIC X(4)) must evaluate to the byte length 4 and
        the descending loop must run for I = 4,3,2,1 → WS-CNT == 4.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-PVLEN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-S PIC X(4) VALUE 'AB  '.",
                "01 WS-I PIC 9(4) VALUE 0.",
                "01 WS-CNT PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM VARYING WS-I FROM LENGTH OF WS-S BY -1",
                "        UNTIL WS-I < 1",
                "        ADD 1 TO WS-CNT",
                "    END-PERFORM.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        # WS-CNT is the third field: offset 4 (WS-S) + 4 (WS-I) = 8
        assert _decode_zoned_unsigned(region, 8, 4) == 4

    @covers(CobolFeature.REFERENCE_MODIFICATION, CobolFeature.IF_ELSE)
    def test_ref_mod_operand_in_condition(self):
        """IF WS-S(2:1) = 'B' → TRUE for 'AB  ' → WS-R == 1.

        A reference-modified operand inside a condition relation must be decoded
        and sliced (the second character of 'AB  ' is 'B').
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-RMCOND.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-S PIC X(4) VALUE 'AB  '.",
                "01 WS-R PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-S(2:1) = 'B'",
                "       MOVE 1 TO WS-R ELSE MOVE 2 TO WS-R END-IF.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        region = _first_region(vm)
        # WS-R at offset 4 (after WS-S PIC X(4))
        assert _decode_zoned_unsigned(region, 4, 1) == 1

    @covers(
        CobolFeature.PERFORM_VARYING,
        CobolFeature.REFERENCE_MODIFICATION,
    )
    def test_perform_varying_length_of_with_ref_mod_until(self):
        """Find position of last non-space char in 'AB  ' → WS-IDX == 2.

        PERFORM VARYING WS-IDX FROM LENGTH OF WS-S BY -1
            UNTIL WS-S(WS-IDX:1) NOT = SPACES OR WS-IDX = 1
        scans backwards from byte 4: positions 4,3 are spaces, position 2 is 'B'
        (non-space) so the loop stops with WS-IDX == 2.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-PVRM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-S PIC X(4) VALUE 'AB  '.",
                "01 WS-IDX PIC 9(4) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    PERFORM VARYING WS-IDX FROM LENGTH OF WS-S BY -1",
                "        UNTIL WS-S(WS-IDX:1) NOT = SPACES OR WS-IDX = 1",
                "    END-PERFORM.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 4, 4) == 2


class TestRefModLengthOf:
    """LENGTH OF <field> used inside a reference-modification start/length.

    Regression for red-dragon-oq2c: the ProLeap bridge serialized
    ``LENGTH OF X`` inside a ref-mod arithmetic expression as a bogus
    ``{"kind":"ref","name":"LENGTHOFX"}`` node (the special register text
    glued together). The frontend then resolved that unknown name to 0, so a
    target write at ``DEST(LENGTH OF G + 1 : ...)`` spliced at position 0
    instead of the intended offset and shifted every prior byte. This is the
    silent ~12-byte commarea shift that broke pseudo-conversational reenter.
    """

    @covers(CobolFeature.REFERENCE_MODIFICATION, CobolFeature.MOVE)
    def test_target_ref_mod_length_of_start_does_not_shift_prior_bytes(self):
        """MOVE INTO DEST(LENGTH OF G + 1 : LENGTH OF H) writes at the right offset.

        DEST is X(20). First MOVE G (a 10-byte group with a 'Z' marker at rel
        offset 5) into DEST, so DEST byte 5 == 'Z'. Then a target ref-mod write
        of H into DEST(LENGTH OF G + 1 : LENGTH OF H) must land at DEST bytes
        11..14 (1-indexed 11) WITHOUT disturbing DEST byte 5. If LENGTH OF G
        mis-resolves to 0 the start collapses to 1 and the splice shifts the
        leading 'Z' rightward (the oq2c bug).
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-RMLEN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 G.",
                "   05 G-A    PIC X(05) VALUE SPACES.",
                "   05 G-MARK PIC X(01) VALUE 'Z'.",
                "   05 G-B    PIC X(04) VALUE SPACES.",
                "01 H        PIC X(04) VALUE 'HHHH'.",
                "01 DEST     PIC X(20) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE G TO DEST.",
                "    MOVE H TO DEST(LENGTH OF G + 1:LENGTH OF H).",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        # G occupies bytes 0..9, H 10..13, DEST 14..33.
        dest_off = 14
        assert _decode_alpha(region, dest_off + 5, 1) == "Z", (
            "leading group marker shifted: target ref-mod start "
            "LENGTH OF G + 1 mis-resolved (oq2c)"
        )
        assert (
            _decode_alpha(region, dest_off + 10, 4) == "HHHH"
        ), "H not written at byte 11 (1-indexed) of DEST"

    @covers(CobolFeature.REFERENCE_MODIFICATION, CobolFeature.MOVE)
    def test_source_ref_mod_length_of_slice_copies_correct_bytes(self):
        """MOVE SRC(1:LENGTH OF G) TO G slices the right length from the source.

        SRC is X(20) with a marker 'Z' at byte 6 (1-indexed) i.e. rel offset 5.
        Slicing SRC(1:LENGTH OF G) where G is a 10-byte group must copy bytes
        1..10, placing the 'Z' at G rel offset 5. If LENGTH OF G resolves to 0
        the slice length collapses and the marker is lost / misplaced.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-RMSRC.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 G.",
                "   05 G-A    PIC X(05).",
                "   05 G-MARK PIC X(01).",
                "   05 G-B    PIC X(04).",
                "01 SRC.",
                "   05 S-A    PIC X(05) VALUE SPACES.",
                "   05 S-MARK PIC X(01) VALUE 'Z'.",
                "   05 S-REST PIC X(14) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE SRC(1:LENGTH OF G) TO G.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        # G occupies bytes 0..9; the marker must land at G rel offset 5.
        assert (
            _decode_alpha(region, 5, 1) == "Z"
        ), "group-slice source length LENGTH OF G mis-resolved (oq2c)"


class TestNumericDisplayVsAlphanumericRelation:
    """red-dragon-dmu8: relation compare of a numeric USAGE DISPLAY field
    (PIC 9(n), ZONED_DECIMAL) against an alphanumeric figurative (SPACES /
    LOW-VALUES) or a non-numeric character literal ('*') must compare via the
    numeric field's zoned CHARACTER (display) representation, NOT its decoded
    integer value.

    Real CardDemo COACTVWC.cbl:628-629:
        IF ACCTSIDI OF CACTVWAI = '*' OR ACCTSIDI = SPACES
    where ACCTSIDI is PIC 9(11). After RECEIVE writes ACCTSIDI='00000000011',
    this must evaluate FALSE so 9000-READ-ACCT runs.

    Scope: ZONED DISPLAY numerics only (COMP/COMP-3 untouched). Signed handling
    is scoped to unsigned-effective values — the display representation used is
    the raw zoned digit characters.
    """

    @covers(CobolFeature.COMPARISON_OPERATORS, CobolFeature.FIGURATIVE_SPACES)
    def test_numeric_display_with_digits_not_equal_spaces(self):
        """PIC 9(11) holding digit chars '00000000011' = SPACES is FALSE.

        The COACTVWC ENTER case: a valid account id is NOT spaces. The zoned
        DISPLAY field's character representation ('00000000011') compared to
        SPACES (11 blanks) is unequal, so the ELSE branch (R=2) runs.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-NDS.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 G.",
                "   05 N PIC 9(11).",
                "01 NA REDEFINES G PIC X(11).",
                "01 R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE '00000000011' TO NA.",
                "    IF N = SPACES",
                "        MOVE 1 TO R",
                "    ELSE",
                "        MOVE 2 TO R",
                "    END-IF.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        # G/N occupies bytes 0..10; R is byte 11.
        assert _decode_zoned_unsigned(region, 11, 1) == 2, (
            "numeric-DISPLAY field with digits compared equal to SPACES "
            "(dmu8): it must compare via zoned character representation"
        )

    @covers(CobolFeature.COMPARISON_OPERATORS, CobolFeature.FIGURATIVE_SPACES)
    def test_numeric_display_holding_spaces_equals_spaces(self):
        """PIC 9(11) whose bytes are all spaces = SPACES is TRUE (dmu8).

        A zoned DISPLAY field filled with blank characters compares EQUAL to the
        SPACES figurative when compared by its character representation. Decoding
        such a field to an integer (0) would compare unequal to the 11-blank
        figurative string, giving the wrong answer; the fix compares characters.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-NDSP.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 G.",
                "   05 N PIC 9(11).",
                "01 NA REDEFINES G PIC X(11).",
                "01 R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE SPACES TO NA.",
                "    IF N = SPACES",
                "        MOVE 1 TO R",
                "    ELSE",
                "        MOVE 2 TO R",
                "    END-IF.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 11, 1) == 1, (
            "a spaces-filled zoned DISPLAY field must compare EQUAL to SPACES "
            "via its character representation (dmu8)"
        )

    @covers(CobolFeature.COMPARISON_OPERATORS)
    def test_numeric_display_holding_placeholder_equals_char_literal(self):
        """PIC 9(11) holding the BMS placeholder '*' (left-justified, blank
        padded) = '*' is TRUE (dmu8).

        This is the exact COACTVWC.cbl:628 case before a valid id is entered:
        ``IF ACCTSIDI = '*'``. The literal '*' extends to the field's 11-char
        width ('*' + 10 blanks); the field's character representation is the
        same, so they compare EQUAL. Decoding the non-numeric zoned field to an
        integer and comparing to the string '*' gives the wrong (unequal) answer.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-NDC.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 G.",
                "   05 N PIC 9(11).",
                "01 NA REDEFINES G PIC X(11).",
                "01 R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE '*' TO NA.",
                "    IF N = '*'",
                "        MOVE 1 TO R",
                "    ELSE",
                "        MOVE 2 TO R",
                "    END-IF.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 11, 1) == 1, (
            "numeric-DISPLAY field holding '*' (blank-padded) must compare "
            "EQUAL to the char literal '*' via character representation (dmu8)"
        )

    @covers(CobolFeature.COMPARISON_OPERATORS, CobolFeature.PIC_CLAUSE)
    def test_numeric_display_field_equals_numeric_literal_regression(self):
        """Regression: numeric<->numeric-literal still compares by value.

        PIC 9(11) VALUE 11 = 11 is TRUE (R=1).
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-NDN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 N PIC 9(11) VALUE 11.",
                "01 R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF N = 11",
                "        MOVE 1 TO R",
                "    ELSE",
                "        MOVE 2 TO R",
                "    END-IF.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        assert (
            _decode_zoned_unsigned(region, 11, 1) == 1
        ), "numeric<->numeric value comparison regressed (dmu8 over-reach)"

    @covers(CobolFeature.COMPARISON_OPERATORS, CobolFeature.FIGURATIVE_SPACES)
    def test_alphanumeric_field_equals_spaces_regression(self):
        """Regression: a spaces-filled X field still compares equal to SPACES."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-AS.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 A PIC X(5).",
                "01 R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE SPACES TO A.",
                "    IF A = SPACES",
                "        MOVE 1 TO R",
                "    ELSE",
                "        MOVE 2 TO R",
                "    END-IF.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        assert (
            _decode_zoned_unsigned(region, 5, 1) == 1
        ), "alphanumeric SPACES comparison regressed (dmu8 over-reach)"

    @covers(CobolFeature.COMPARISON_OPERATORS)
    def test_alphanumeric_field_equals_char_literal_regression(self):
        """Regression: an X field holding 'XXXXX' compares equal to 'X' only
        at full width — here A='X    ' (left-justified) != 'X' padded to 5,
        so the unequal case must take the ELSE branch (R=2)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-AC.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 A PIC X(5) VALUE 'XXXXX'.",
                "01 R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF A = 'XXXXX'",
                "        MOVE 1 TO R",
                "    ELSE",
                "        MOVE 2 TO R",
                "    END-IF.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        assert (
            _decode_zoned_unsigned(region, 5, 1) == 1
        ), "alphanumeric char-literal comparison regressed (dmu8 over-reach)"


class TestIntrinsicFunctionInRelation:
    """FUNCTION intrinsic calls as operands of an IF relation (red-dragon-ge72).

    Before the bridge fix both relation operands collapsed to a bare
    {"kind":"ref","name":"UPPER-CASE"} and always compared EQUAL. The fix
    serializes a structured {"kind":"function",...} node so the call + args
    survive and lower to the computed value.
    """

    @covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.COMPARISON_OPERATORS)
    def test_upper_case_relation_unequal(self):
        """IF UPPER-CASE('n') = UPPER-CASE('Y') is FALSE (N != Y) -> ELSE, R=2."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-UCR1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF FUNCTION UPPER-CASE('n') = FUNCTION UPPER-CASE('Y')",
                "        MOVE 1 TO R",
                "    ELSE",
                "        MOVE 2 TO R",
                "    END-IF.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 1) == 2

    @covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.COMPARISON_OPERATORS)
    def test_upper_case_relation_equal(self):
        """IF UPPER-CASE('n') = UPPER-CASE('y') is TRUE (N == N... 'n'->'N', 'y'->'Y').

        Use 'n' vs 'N' so the uppercased forms match -> THEN branch, R=1.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-UCR2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF FUNCTION UPPER-CASE('n') = FUNCTION UPPER-CASE('N')",
                "        MOVE 1 TO R",
                "    ELSE",
                "        MOVE 2 TO R",
                "    END-IF.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 1) == 1

    @covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.COMPARISON_OPERATORS)
    def test_trim_relation_equal(self):
        """IF FUNCTION TRIM(' AB ') = 'AB' strips both ends -> TRUE, R=1."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-TRIM1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF FUNCTION TRIM(' AB ') = 'AB'",
                "        MOVE 1 TO R",
                "    ELSE",
                "        MOVE 2 TO R",
                "    END-IF.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 1) == 1

    @covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.COMPARISON_OPERATORS)
    def test_function_vs_ref_relation_changed_field(self):
        """Two WS fields, one differing: UPPER-CASE(A) = UPPER-CASE(B) reflects
        inequality (A='Active', B='active' uppercase equal -> equal; but here
        A='Active' B='Closed' differ -> ELSE, R=2)."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-FVR.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-A PIC X(6) VALUE 'Active'.",
                "01 WS-B PIC X(6) VALUE 'Closed'.",
                "01 R PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF FUNCTION UPPER-CASE(WS-A) = FUNCTION UPPER-CASE(WS-B)",
                "        MOVE 1 TO R",
                "    ELSE",
                "        MOVE 2 TO R",
                "    END-IF.",
                "    STOP RUN.",
            ],
            max_steps=4000,
        )
        region = _first_region(vm)
        # R is at offset 12 (after WS-A X(6) + WS-B X(6)).
        assert _decode_zoned_unsigned(region, 12, 1) == 2


class TestInspectConverting:
    """INSPECT ... CONVERTING from TO to — positional per-character translate,
    with the from/to operands resolved as runtime data items (red-dragon-zuhj).
    """

    @covers(CobolFeature.INSPECT_CONVERTING)
    def test_converting_letters_to_spaces(self):
        """INSPECT WS-T CONVERTING WS-FROM TO WS-TO turns letters into spaces."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. CONV1.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-FROM PIC X(26) VALUE 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.",
                "01 WS-TO   PIC X(26) VALUE SPACES.",
                "01 WS-T    PIC X(5)  VALUE 'AB1CD'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    INSPECT WS-T CONVERTING WS-FROM TO WS-TO",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-T at offset 52 (26 + 26): only the digit '1' (pos 3) survives.
        assert _decode_alpha(region, 52, 5) == "  1  "


class TestStringMultiOperandRefMod:
    """STRING with several sending operands sharing one DELIMITED BY phrase, one
    of them reference-modified — every operand must contribute (red-dragon-zuhj).
    """

    @covers(
        CobolFeature.STRING_VERB,
        CobolFeature.STRING_DELIMITED_BY,
        CobolFeature.STRING_REF_MOD,
    )
    def test_string_two_operands_one_ref_modded(self):
        """STRING WS-ST WS-ZIP(1:2) DELIMITED BY SIZE INTO WS-COMBO -> 'CA90'."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. STRMRM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-ST    PIC X(2)  VALUE 'CA'.",
                "01 WS-ZIP   PIC X(10) VALUE '90001'.",
                "01 WS-COMBO PIC X(4).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STRING WS-ST WS-ZIP(1:2)",
                "      DELIMITED BY SIZE INTO WS-COMBO",
                "    END-STRING",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 12, 4) == "CA90"


class TestFigurativeValueFill:
    """A figurative VALUE (e.g. PIC X(n) VALUE SPACES) fills the WHOLE field with
    its fill character, not the literal keyword text (red-dragon-zuhj)."""

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_value_spaces_fills_field_with_spaces(self):
        """01 WS-S PIC X(6) VALUE SPACES is six spaces, not 'SPACES'."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FIGVAL.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-S PIC X(6) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 0, 6) == "      "

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_quoted_literal_value_left_verbatim(self):
        """01 WS-S PIC X(6) VALUE 'SPACE' keeps the quoted literal text."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FIGVAL2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-S PIC X(6) VALUE 'SPACE'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 0, 6) == "SPACE "

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_value_zeros_on_zoned_decimal_initialises_to_zero(self):
        """01 WS-N PIC 9(4) VALUE ZEROS initialises field to numeric 0, not 'ZERO'."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FIGVZ.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-N PIC 9(4) VALUE ZEROS.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_zoned_unsigned(region, 0, 4) == 0

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_value_zeros_on_comp3_initialises_to_zero(self):
        """01 WS-N PIC 9(5) COMP-3 VALUE ZEROS initialises field to numeric 0."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FIGVC3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-N PIC 9(5) COMP-3 VALUE ZEROS.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_comp3(region, 0, 3) == 0

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_value_low_values_on_alphanumeric_fills_null_bytes(self):
        """01 WS-X PIC X(4) VALUE LOW-VALUES initialises field to 4 null bytes."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FIGLV.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-X PIC X(4) VALUE LOW-VALUES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert list(region[0:4]) == [0x00, 0x00, 0x00, 0x00]

    @covers(CobolFeature.VALUE_CLAUSE)
    def test_value_high_values_on_alphanumeric_fills_xff_bytes(self):
        """01 WS-X PIC X(4) VALUE HIGH-VALUES initialises field to 4 0xFF bytes."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. FIGHV.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-X PIC X(4) VALUE HIGH-VALUES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert list(region[0:4]) == [0xFF, 0xFF, 0xFF, 0xFF]


class TestClassConditionRefMod:
    """A class condition on a reference-modified operand tests only the slice,
    not the whole space-padded field (red-dragon-zuhj)."""

    @covers(CobolFeature.CLASS_CONDITION, CobolFeature.REFERENCE_MODIFICATION)
    def test_is_numeric_on_ref_mod_slice(self):
        """WS-F(1:3) IS NUMERIC is true for '750' even though WS-F is padded."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. CLSRM.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-F PIC X(10) VALUE '750'.",
                "01 WS-R PIC X(3)  VALUE 'NO'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-F(1:3) IS NUMERIC",
                "       MOVE 'YES' TO WS-R",
                "    ELSE",
                "       MOVE 'BAD' TO WS-R",
                "    END-IF",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        assert _decode_alpha(region, 10, 3) == "YES"


class TestStringFunctionSource:
    """STRING with a FUNCTION sending operand evaluates the call, not the literal
    function name (red-dragon-zuhj)."""

    @covers(CobolFeature.STRING_VERB, CobolFeature.INTRINSIC_FUNCTION)
    def test_string_function_trim_source(self):
        """STRING FUNCTION TRIM(WS-N) ' OK' INTO WS-M -> 'AB OK'."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. STRFN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-N PIC X(5) VALUE 'AB'.",
                "01 WS-M PIC X(8) VALUE SPACES.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    STRING FUNCTION TRIM(WS-N) ' OK'",
                "      DELIMITED BY SIZE INTO WS-M",
                "    END-STRING",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-M at offset 5 (after WS-N X(5)).
        assert _decode_alpha(region, 5, 5) == "AB OK"


class TestOccursDependingOn:
    """OCCURS 0 TO n DEPENDING ON variable-length subordinate fields (the
    CardDemo CSUTLDTC Vstring pattern: a S9(4) length field followed by a
    PIC X char that OCCURS 0 TO 256 DEPENDING ON that length). The fields are
    declared in mixed case (Vstring-length / Vstring-char) but referenced in
    upper case from the PROCEDURE DIVISION — COBOL identifiers are
    case-insensitive, so the upper-case references must resolve. red-dragon-p7qe."""

    @covers(CobolFeature.OCCURS_DEPENDING_ON)
    def test_odo_length_and_subscripted_element_resolve(self):
        """A mixed-case ODO group lowers cleanly; the length field and a
        subscripted element resolve and round-trip through MOVE.

        Layout: Vstring-length S9(4) BINARY @0 (2 bytes), then Vstring-text
        whose Vstring-char PIC X OCCURS 0 TO 256 lays out at MAX (256 bytes)
        @2. A trailing field (WS-AFTER) therefore sits at offset 2+256 = 258."""
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. ODOTEST.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-DATE-TO-TEST.",
                "   02 Vstring-length PIC S9(4) BINARY.",
                "   02 Vstring-text.",
                "      03 Vstring-char PIC X OCCURS 0 TO 256 TIMES",
                "         DEPENDING ON Vstring-length OF WS-DATE-TO-TEST.",
                "01 WS-AFTER PIC X(4) VALUE 'ZZZZ'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 5 TO VSTRING-LENGTH OF WS-DATE-TO-TEST",
                "    MOVE 'A' TO VSTRING-CHAR OF WS-DATE-TO-TEST (1)",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # Vstring-length S9(4) BINARY @0 holds 5 (big-endian 2-byte binary).
        assert int.from_bytes(region[0:2], "big", signed=True) == 5
        # Vstring-char(1) @2 (the ODO element laid out at MAX) holds 'A' (EBCDIC).
        assert _decode_alpha(region, 2, 1) == "A"
        # The trailing field sits AFTER the max-length ODO array: 2 + 256 = 258.
        assert _decode_alpha(region, 258, 4) == "ZZZZ"
