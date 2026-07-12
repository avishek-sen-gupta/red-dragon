"""Regression: subscripted field access on non-first OCCURS occurrences.

red-dragon-9cxh: a relational/condition operand load dropped the
``(subscript - 1) * stride`` term, so ``IF XNUM(n) ...`` read occurrence 1
regardless of ``n``. A loop that increments ``XNUM(n)`` and exits on
``IF XNUM(n) ...`` therefore never terminated for ``n >= 2`` (the comparison
read a different occurrence than the increment wrote). It was invisible for
``n == 1`` because ``(1 - 1) * stride == 0``.

These tests increment ``XNUM(n)`` in a GO TO loop until it reaches 5, then read
the value back from the correct occurrence's offset and assert it is exactly 5.
For ``n >= 2`` this only holds once the comparison resolves the same occurrence
the increment writes; before the fix the loop ran away and the value never
settled at 5.
"""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    run_cobol,
)
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned as _decode,
)
from tests.integration.cobol_helpers import (
    first_region as _first_region,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR (fails loudly if unset)."""


# Each OCCURS element (GRP) is P1 = 34 + 6 + 80 = 120 bytes; XNUM sits at
# offset 34 within the element, so occurrence n (1-based) is at (n-1)*120 + 34.
_ELEMENT_STRIDE = 120
_XNUM_OFFSET_IN_ELEMENT = 34
_XNUM_LEN = 6


def _program(sub: int) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. SUBOCC.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01  REC.",
        "    03  GRP OCCURS 10 TIMES.",
        "        05  P1.",
        "            07  FILLER PIC X(34).",
        "            07  XNUM   PIC 9(6).",
        "            07  FILLER PIC X(80).",
        "PROCEDURE DIVISION.",
        "MAIN.",
        f"    MOVE ZERO TO XNUM ({sub}).",
        "LP.",
        f"    ADD 1 TO XNUM ({sub}).",
        f"    IF XNUM ({sub}) LESS THAN 5 GO TO LP.",
        "    STOP RUN.",
    ]


class TestSubscriptedOccurrenceIncrement:
    @pytest.mark.parametrize("sub", [1, 2, 3])
    @covers(CobolFeature.OCCURS_FIXED)
    def test_increment_loop_terminates_at_correct_occurrence(self, sub: int):
        # max_steps bounds the run: if the comparison read the wrong occurrence
        # the loop would not settle at 5 within this budget (the regression).
        vm = run_cobol(_program(sub), max_steps=5000)
        region = _first_region(vm)
        offset = (sub - 1) * _ELEMENT_STRIDE + _XNUM_OFFSET_IN_ELEMENT
        assert _decode(region, offset, _XNUM_LEN) == 5


# A 3-occurrence table whose element is 10 bytes; a sibling RESULT digit sits at
# offset 30 (3 * 10) so it can be read back from the single REC region. Each
# program sets occurrence 1 and 2 to *different* content, then compares
# occurrence 2; RESULT=1 means the comparison read occurrence 2 (correct),
# RESULT=9 means it read occurrence 1 (the subscript-dropping bug).
_RESULT_OFFSET = 30


def _relation_operand_program() -> list[str]:
    # red-dragon-9cxh, L540: numeric USAGE-DISPLAY operand compared to an
    # alphanumeric (char-literal) sibling takes the zoned-display branch of
    # _lower_relation_operand, which dropped the subscript.
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. RELOCC.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01  REC.",
        "    03  GRP OCCURS 3 TIMES.",
        "        05  P1.",
        "            07  FILLER PIC X(2).",
        "            07  N      PIC 9(3).",
        "            07  FILLER PIC X(5).",
        "    03  RESULT PIC 9(1).",
        "PROCEDURE DIVISION.",
        "MAIN.",
        "    MOVE 100 TO N (1).",
        "    MOVE 200 TO N (2).",
        '    IF N (2) = "200" MOVE 1 TO RESULT ELSE MOVE 9 TO RESULT.',
        "    STOP RUN.",
    ]


def _ref_mod_operand_program() -> list[str]:
    # red-dragon-9cxh, L668: a reference-modified operand FIELD(n)(s:l) in a
    # condition went through _lower_ref_mod_operand, which dropped the subscript.
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. RMOCC.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01  REC.",
        "    03  GRP OCCURS 3 TIMES.",
        "        05  P1.",
        "            07  FILLER PIC X(2).",
        "            07  S      PIC X(5).",
        "            07  FILLER PIC X(3).",
        "    03  RESULT PIC 9(1).",
        "PROCEDURE DIVISION.",
        "MAIN.",
        '    MOVE "AAAAA" TO S (1).',
        '    MOVE "BBBBB" TO S (2).',
        '    IF S (2) (1:1) = "B" MOVE 1 TO RESULT ELSE MOVE 9 TO RESULT.',
        "    STOP RUN.",
    ]


class TestSubscriptedOccurrenceConditionOperands:
    @covers(CobolFeature.OCCURS_FIXED)
    def test_numeric_display_operand_vs_char_literal_reads_correct_occurrence(self):
        region = _first_region(run_cobol(_relation_operand_program(), max_steps=4000))
        assert _decode(region, _RESULT_OFFSET, 1) == 1

    @covers(CobolFeature.OCCURS_FIXED)
    def test_ref_mod_operand_reads_correct_occurrence(self):
        region = _first_region(run_cobol(_ref_mod_operand_program(), max_steps=4000))
        assert _decode(region, _RESULT_OFFSET, 1) == 1


# ── 2-D OCCURS (red-dragon-1wy3) ──────────────────────────────────────────────
#
# Layout:  01 GRID.
#            03 GRID-ROW OCCURS 4 TIMES.   element_size = 3 × 2 = 6 bytes
#               05 GRID-CELL PIC 99 OCCURS 3 TIMES.  element_size = 2 bytes
#          RESULT PIC 99 follows at offset 4*6 = 24.
#
# GRID-CELL(r, c) byte offset = (r-1)*6 + (c-1)*2
# The test writes distinct values to GRID-CELL(1,1), GRID-CELL(2,3),
# GRID-CELL(4,2) then reads them back via RESULT and verifies each.

_2D_GRID_ROW_STRIDE = 6  # 3 cells * 2 bytes
_2D_RESULT_OFFSET = 4 * _2D_GRID_ROW_STRIDE  # = 24


def _2d_grid_program(row: int, col: int, write_val: int) -> list[str]:
    """Write write_val to GRID-CELL(row, col), copy to RESULT, STOP RUN."""
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. GRID2D.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01  GRID.",
        "    03  GRID-ROW OCCURS 4 TIMES.",
        "        05  GRID-CELL PIC 99 OCCURS 3 TIMES.",
        "01  RESULT PIC 99.",
        "PROCEDURE DIVISION.",
        "MAIN.",
        f"    MOVE {write_val} TO GRID-CELL ({row}, {col}).",
        f"    MOVE GRID-CELL ({row}, {col}) TO RESULT.",
        "    STOP RUN.",
    ]


class TestTwoDimensionalSubscript:
    @pytest.fixture(autouse=True)
    def _require_bridge_jar(self, bridge_jar):
        """Enforce the required PROLEAP_BRIDGE_JAR."""

    @pytest.mark.parametrize(
        "row, col, val",
        [(1, 1, 11), (2, 3, 23), (4, 2, 42)],
    )
    @covers(CobolFeature.OCCURS_FIXED)
    def test_2d_subscript_reads_and_writes_correct_cell(
        self, row: int, col: int, val: int
    ):
        vm = run_cobol(_2d_grid_program(row, col, val), max_steps=2000)
        region = _first_region(vm)
        result = _decode(region, _2D_RESULT_OFFSET, 2)
        assert (
            result == val
        ), f"GRID-CELL({row},{col}) wrote {val} but RESULT decoded as {result}"


# ── Nested-leaf stride: GROUP element_size, not leaf width (red-dragon-592s) ──
#
# A leaf nested inside an OCCURS group must be subscripted with the *enclosing
# group's* element_size as the stride, NOT the leaf's own byte_length. This is
# the CardDemo COMEN02Y shape: CDEMO-MENU-OPT-PGMNAME(WS-OPTION) — an 8-char
# program-name leaf preceded by a 2-char option field inside the OCCURS element.
#
#     01 REC.
#        03 MENU-OPT OCCURS 3 TIMES.     element_size = 2 + 8 = 10
#           05 OPT-NUM PIC X(2).
#           05 OPT-PGM PIC X(8).         offset 2 within element (width 8)
#        03 RESULT    PIC X(8).          offset 3 * 10 = 30
#
# OPT-PGM(2) sits at (2-1)*10 + 2 = 12. The bug strode by the leaf width (8),
# computing (2-1)*8 + 2 = 10 — reading occurrence-1's tail + occurrence-2's
# head (the reported "offset 45 'U02Accou' vs 83 'COACTUPC'" mojibake). The
# program MOVEs distinct names into each occurrence, copies OPT-PGM(2) into a
# top-level RESULT, and the test EBCDIC-decodes RESULT and asserts it is exactly
# the occurrence-2 name — not a cross-occurrence smear.
_NESTED_RESULT_OFFSET = 30
_NESTED_RESULT_LEN = 8


def _nested_leaf_program() -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. NESTOCC.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01  REC.",
        "    03  MENU-OPT OCCURS 3 TIMES.",
        "        05  OPT-NUM PIC X(2).",
        "        05  OPT-PGM PIC X(8).",
        "    03  RESULT PIC X(8).",
        "PROCEDURE DIVISION.",
        "MAIN.",
        '    MOVE "01" TO OPT-NUM (1).',
        '    MOVE "PROG0001" TO OPT-PGM (1).',
        '    MOVE "02" TO OPT-NUM (2).',
        '    MOVE "PROG0002" TO OPT-PGM (2).',
        '    MOVE "03" TO OPT-NUM (3).',
        '    MOVE "PROG0003" TO OPT-PGM (3).',
        "    MOVE OPT-PGM (2) TO RESULT.",
        "    STOP RUN.",
    ]


class TestNestedLeafSubscriptStride:
    @pytest.fixture(autouse=True)
    def _require_bridge_jar(self, bridge_jar):
        """Enforce the required PROLEAP_BRIDGE_JAR."""

    @covers(CobolFeature.OCCURS_FIXED)
    def test_nested_leaf_strides_by_group_element_size(self):
        from interpreter.cobol.ebcdic_table import EbcdicTable

        vm = run_cobol(_nested_leaf_program(), max_steps=2000)
        region = _first_region(vm)
        raw = bytes(
            region[_NESTED_RESULT_OFFSET : _NESTED_RESULT_OFFSET + _NESTED_RESULT_LEN]
        )
        decoded = EbcdicTable.ebcdic_to_ascii(raw).decode("ascii")
        assert decoded == "PROG0002", (
            f"OPT-PGM(2) should stride by the group element_size (10) to read "
            f"'PROG0002'; got {decoded!r} (leaf-width stride reads a "
            f"cross-occurrence smear — red-dragon-592s)"
        )
