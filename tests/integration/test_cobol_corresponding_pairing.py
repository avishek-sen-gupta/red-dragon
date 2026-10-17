"""End-to-end: which items a CORRESPONDING phrase pairs, at every depth, and the subscripts on its operands."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.io_provider import StubIOProvider
from interpreter.run import run
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    to_fixed,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


def _shown(
    capsys: pytest.CaptureFixture[str],
    working_storage: Sequence[str],
    procedure: Sequence[str],
) -> str:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. CORRPAIR.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            *working_storage,
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            *procedure,
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=20000,
        io_provider=StubIOProvider(accept_values=[]),
    )
    return capsys.readouterr().out


class TestCorrespondingPairing:
    @covers(CobolFeature.MOVE_CORRESPONDING, CobolFeature.GROUP_ITEM)
    def test_move_pairs_like_qualified_items_with_one_elementary(self, capsys):
        """ANSI X3.23-1985 VI-6.4.3 / ISO 1989 CORRESPONDING: items pair when
        their names and every qualifier below the operands agree and at least
        one of the two is elementary; a subordinate item with OCCURS or
        REDEFINES, everything under it, and FILLER are ignored; a subscripted
        operand selects its occurrence."""
        shown = _shown(
            capsys,
            [
                "01 S1.",
                "   02 GA. 03 N PIC 9 VALUE 1.",
                "   02 GB. 03 N PIC 9 VALUE 2.",
                '   02 A PIC XXX VALUE "XYZ".',
                "   02 B PIC 99 VALUE 12.",
                '   02 K. 03 SUBK. 04 C1 PIC X VALUE "S".',
                '   02 R PIC X VALUE "R".',
                '   02 Q PIC X VALUE "Q".',
                '   02 GR. 03 GRC PIC X VALUE "G".',
                '   02 FILLER PIC X VALUE "F".',
                '   02 GE. 03 GE1 PIC X VALUE "E". 03 GE2 PIC X VALUE "F".',
                "01 D1.",
                "   02 GA. 03 N PIC 9.",
                "   02 GB. 03 N PIC 9.",
                "   02 A. 03 FILLER PIC 999. 03 FILLER PIC XXX.",
                "   02 B PIC 99 OCCURS 2.",
                "   02 K. 03 C1 PIC X.",
                "   02 R PIC X.",
                "   02 Q REDEFINES R PIC X.",
                "   02 GX PIC XX.",
                "   02 GR REDEFINES GX. 03 GRC PIC X.",
                "   02 FILLER PIC X.",
                "   02 GE PIC XXX.",
                '01 TS VALUE "ABCD". 02 TE OCCURS 2. 03 TA PIC X. 03 TB PIC X.',
                '01 TD VALUE "------". 02 TF OCCURS 3. 03 TA PIC X. 03 TB PIC X.',
            ],
            [
                '    MOVE "--------------------" TO D1.',
                "    MOVE CORRESPONDING S1 TO D1.",
                "    MOVE CORRESPONDING TE(2) TO TF(3).",
                "    DISPLAY D1 TD.",
            ],
        )
        assert shown == "12XYZ   -----R---EF ----CD\n"

    @covers(CobolFeature.ADD, CobolFeature.SUBTRACT, CobolFeature.GROUP_ITEM)
    def test_add_and_subtract_pair_only_elementary_numeric_items(self, capsys):
        """ANSI X3.23-1985 VI-6.4.3 / ISO 1989 CORRESPONDING: ADD and SUBTRACT
        pair only items that are both elementary numeric, at any depth, skip a
        subordinate OCCURS item, and apply the operands' subscripts."""
        shown = _shown(
            capsys,
            [
                '01 T1 VALUE "060102071122053".',
                "   02 R1 PIC 99. 02 R2 PIC 99 OCCURS 2. 02 R3 PIC 99.",
                "   02 SUBG. 03 C1 PIC 99. 03 C2 PIC 99.",
                "   02 X1 PIC 99. 02 G1. 03 G1A PIC 9.",
                '01 T2 VALUE "080304090102AB44".',
                "   02 R1 PIC 99. 02 R2 PIC 99 OCCURS 2. 02 R3 PIC 99.",
                "   02 SUBG. 03 C1 PIC 99. 03 C2 PIC 99.",
                "   02 X1 PIC XX. 02 G1 PIC 99.",
                '01 U1 VALUE "01020304". 02 UE OCCURS 2. 03 V PIC 99. 03 W PIC 99.',
                '01 U2 VALUE "10101010". 02 UF OCCURS 2. 03 V PIC 99. 03 W PIC 99.',
            ],
            [
                "    ADD CORRESPONDING T1 TO T2.",
                "    SUBTRACT CORRESPONDING T1 FROM T2.",
                "    ADD CORRESPONDING T1 TO T2.",
                "    ADD CORRESPONDING UE(2) TO UF(1).",
                "    SUBTRACT CORR UE(1) FROM UF(2).",
                "    DISPLAY T2 U2.",
            ],
        )
        assert shown == "140304161224AB4413140908\n"
