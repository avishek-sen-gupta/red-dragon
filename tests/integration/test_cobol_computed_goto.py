"""End-to-end: GO TO ... DEPENDING ON selects the idx-th paragraph (1-based);
out-of-range falls through."""

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


def _pgm(idx: int) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. CGOTO.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        f"01 WS-IDX PIC 9 VALUE {idx}.",
        "01 WS-R   PIC 9 VALUE 0.",
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        "    GO TO P1 P2 P3 DEPENDING ON WS-IDX.",
        "    MOVE 9 TO WS-R.",
        "    STOP RUN.",
        "P1.",
        "    MOVE 1 TO WS-R.",
        "    STOP RUN.",
        "P2.",
        "    MOVE 2 TO WS-R.",
        "    STOP RUN.",
        "P3.",
        "    MOVE 3 TO WS-R.",
        "    STOP RUN.",
    ]


class TestComputedGoto:
    @pytest.mark.parametrize("idx,expected", [(1, 1), (2, 2), (3, 3), (4, 9), (0, 9)])
    @covers(CobolFeature.GOTO_DEPENDING_ON)
    def test_depending_on_selects_target_or_falls_through(
        self, idx: int, expected: int
    ):
        vm = run_cobol(_pgm(idx), max_steps=2000)
        # WS-R is the second 1-digit field: WS-IDX at offset 0, WS-R at offset 1.
        assert _decode(_first_region(vm), 1, 1) == expected

    @covers(CobolFeature.GOTO_DEPENDING_ON)
    def test_depending_on_qualified_index(self):
        """The index is a qualified data item (SEL-IX OF CTL-GRP)."""
        vm = run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. CGOTOQ.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 CTL-GRP.",
                "   05 SEL-IX PIC 9 VALUE 2.",
                "01 WS-R PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    GO TO Q1 Q2 DEPENDING ON SEL-IX OF CTL-GRP.",
                "    MOVE 9 TO WS-R.",
                "    STOP RUN.",
                "Q1.",
                "    MOVE 1 TO WS-R.",
                "    STOP RUN.",
                "Q2.",
                "    MOVE 2 TO WS-R.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        # CTL-GRP/SEL-IX occupy offset 0; WS-R at offset 1.
        assert _decode(_first_region(vm), 1, 1) == 2

    @covers(CobolFeature.GOTO_DEPENDING_ON)
    def test_depending_on_subscripted_index(self):
        """The index is a subscripted table element (IDX-ELEM(2)); the subscript is
        threaded through resolve_field_ref to select the 2nd target."""
        vm = run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. CGOTOX.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 IDX-TBL.",
                "   05 IDX-ELEM PIC 9 OCCURS 3 TIMES.",
                "01 WS-R PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 2 TO IDX-ELEM (2).",
                "    GO TO X1 X2 DEPENDING ON IDX-ELEM (2).",
                "    MOVE 9 TO WS-R.",
                "    STOP RUN.",
                "X1.",
                "    MOVE 1 TO WS-R.",
                "    STOP RUN.",
                "X2.",
                "    MOVE 2 TO WS-R.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        # IDX-ELEM occupies offsets 0..2 (3 occurrences); WS-R at offset 3.
        # IDX-ELEM(2)=2 selects the 2nd target X2, which sets WS-R=2.
        assert _decode(_first_region(vm), 3, 1) == 2

    @covers(CobolFeature.GOTO_DEPENDING_ON)
    def test_depending_on_section_qualified_target(self):
        """A target paragraph living inside a section still resolves and lands."""
        vm = run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. CGOTOS.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-IDX PIC 9 VALUE 1.",
                "01 WS-R   PIC 9 VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    GO TO TGT-PARA DEPENDING ON WS-IDX.",
                "    MOVE 9 TO WS-R.",
                "    STOP RUN.",
                "WORK-SECTION SECTION.",
                "TGT-PARA.",
                "    MOVE 1 TO WS-R.",
                "    STOP RUN.",
            ],
            max_steps=2000,
        )
        assert _decode(_first_region(vm), 1, 1) == 1
