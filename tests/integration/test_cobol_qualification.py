"""End-to-end: a data reference qualified by OF/IN denotes the one item its qualifiers select."""

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
    accepted: Sequence[str] = (),
) -> str:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. QUALIF.",
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
        max_steps=5000,
        io_provider=StubIOProvider(accept_values=list(accepted)),
    )
    return capsys.readouterr().out


class TestQualifiedReferenceResolution:
    @covers(CobolFeature.MOVE)
    def test_every_qualifier_selects_and_subscripts_stride_the_selected_item(
        self, capsys
    ):
        shown = _shown(
            capsys,
            [
                "01 R1 PIC X.",
                "01 R2 PIC X.",
                "01 R3 PIC X.",
                "01 R4 PIC XX.",
                "01 R5 PIC X.",
                "01 REC.",
                "   02 L2A.",
                '      03 L1A. 04 T PIC X VALUE "1".',
                '      03 L1B. 04 T PIC X VALUE "2".',
                "   02 L2B.",
                '      03 L1A. 04 T PIC X VALUE "3".',
                '      03 L1B. 04 T PIC X VALUE "4".',
                "01 G10.",
                '   02 D3. 03 D3A PIC X VALUE "A". 03 D3B PIC X VALUE "B".',
                "01 G20.",
                "   02 D3 PIC 99 VALUE 45.",
                "01 H1.",
                '   02 L2. 03 L3 OCCURS 2. 04 ITM PIC X VALUE "-".',
                "01 G1.",
                "   02 L2 OCCURS 2.",
                "      03 L3 OCCURS 3. 04 ITM PIC X.",
                "01 CX.",
                "   02 CX-SUB PIC 9 VALUE 3.",
                "01 DX.",
                "   02 CX-SUB PIC 9 VALUE 1.",
            ],
            [
                "    MOVE T OF L1A OF L2B TO R1.",
                "    MOVE T OF L1B IN L2A TO R2.",
                "    MOVE T IN L1B OF L2B OF REC TO R3.",
                "    MOVE D3 IN G10 TO R4.",
                '    MOVE "------" TO G1.',
                '    MOVE "Z" TO ITM OF L3 OF L2 OF G1 (2, CX-SUB OF CX).',
                "    MOVE ITM OF G1 (2, 3) TO R5.",
                "    DISPLAY R1 R2 R3 R4 R5 G1.",
            ],
        )
        assert shown == "324ABZ-----Z"


class TestQualifiedStatementOperands:
    @covers(CobolFeature.DISPLAY)
    def test_display_shows_the_qualified_items(self, capsys):
        shown = _shown(
            capsys,
            [
                "01 REC.",
                '   02 G1. 03 E1 PIC X VALUE "A". 03 E2 PIC X VALUE "B".',
                '   02 G2. 03 E1 PIC X VALUE "C". 03 E2 PIC X VALUE "D".',
                "01 TB.",
                '   02 G1 OCCURS 2. 03 E1 PIC X VALUE "-".',
            ],
            [
                '    MOVE "Q" TO E1 OF TB (2).',
                "    DISPLAY E1 OF G1 OF REC E2 IN G2 E1 OF TB (2) E1 IN G2 (1:1).",
            ],
        )
        assert shown == "ADQC"

    @covers(CobolFeature.ACCEPT)
    def test_accept_stores_into_the_qualified_occurrence(self, capsys):
        shown = _shown(
            capsys,
            [
                "01 R1. 02 A PIC XX VALUE SPACES.",
                "01 R2. 02 A PIC XX VALUE SPACES.",
                '01 T1. 02 A PIC X OCCURS 3 VALUE "-".',
                "01 SUB PIC 9 VALUE 3.",
            ],
            [
                '    MOVE "---" TO T1.',
                "    ACCEPT A OF R2.",
                "    ACCEPT A IN T1 (SUB).",
                "    DISPLAY R1 R2 T1.",
            ],
            ["XY", "Z"],
        )
        assert shown == "  XY--Z"

    @covers(CobolFeature.LEVEL_88_CONDITION)
    def test_condition_names_test_and_set_their_own_qualified_parent(self, capsys):
        shown = _shown(
            capsys,
            [
                "01 R.",
                "   02 G1. 03 F PIC 9 VALUE 1. 88 OK1 VALUE 1.",
                "   02 G2. 03 F PIC 9 VALUE 2.",
                "01 D32 PIC 9 VALUE 0. 88 B VALUE 3. 88 C VALUE 4.",
                "01 D33 PIC 9 VALUE 0. 88 B VALUE 5. 88 C VALUE 6.",
                '01 R1 PIC X VALUE "N".',
                '01 R2 PIC X VALUE "N".',
                '01 R3 PIC X VALUE "N".',
            ],
            [
                '    IF OK1 MOVE "Y" TO R1.',
                "    MOVE 3 TO D32.",
                '    IF B OF D32 MOVE "Y" TO R2.',
                '    IF B OF D33 OR C IN D32 MOVE "Y" TO R3.',
                "    SET C OF D33 TO TRUE.",
                "    DISPLAY R1 R2 R3 D32 D33.",
            ],
        )
        assert shown == "YYN36"

    @covers(CobolFeature.RENAMES_CLAUSE)
    def test_renames_resolves_its_operands_within_its_own_record(self, capsys):
        shown = _shown(
            capsys,
            [
                '01 R1. 02 AL PIC XX VALUE "AA". 02 BOB PIC XXX VALUE "BBB".',
                '01 R2. 02 AL PIC XX VALUE "CC".',
                '   02 MID. 03 M1 PIC X VALUE "M".',
                '   02 BOB PIC XXX VALUE "DDD".',
                "66 AL-BOB RENAMES AL OF R2 THRU BOB OF R2.",
                "66 MIDR RENAMES MID.",
                '01 R3. 02 X PIC X VALUE "X". 02 Y PIC X VALUE "Y".',
                "66 MIDR RENAMES X THRU Y.",
                '01 R4. 02 X PIC X VALUE "Q".',
                "66 XR RENAMES X.",
            ],
            ["    DISPLAY AL-BOB MIDR OF R2 MIDR IN R3 XR."],
        )
        assert shown == "CCMDDDMXYQ"

    @covers(CobolFeature.MOVE_CORRESPONDING, CobolFeature.ADD, CobolFeature.SUBTRACT)
    def test_corresponding_operands_are_the_qualified_groups(self, capsys):
        shown = _shown(
            capsys,
            [
                '01 R1. 02 B. 03 TOM PIC XXX VALUE "R1R".',
                '01 R2. 02 B. 03 TOM PIC XXX VALUE "R2R".',
                "01 DST. 02 TOM PIC XXX VALUE SPACES.",
                "01 A1. 02 SG. 03 C1 PIC 99 VALUE 11.",
                "01 A2. 02 SG. 03 C1 PIC 99 VALUE 22.",
                "01 T. 02 SG. 03 C1 PIC 99 VALUE 1.",
            ],
            [
                "    MOVE CORRESPONDING B OF R2 TO DST.",
                "    ADD CORRESPONDING SG OF A2 TO SG IN T.",
                "    SUBTRACT CORRESPONDING SG OF A1 FROM SG OF T.",
                "    DISPLAY DST T.",
            ],
        )
        assert shown == "R2R12"

    @covers(CobolFeature.INITIALIZE)
    def test_initialize_resets_only_the_qualified_group(self, capsys):
        shown = _shown(
            capsys,
            [
                '01 R1. 02 G. 03 A PIC X VALUE "X". 03 N PIC 9 VALUE 7.',
                '01 R2. 02 G. 03 A PIC X VALUE "Y". 03 N PIC 9 VALUE 8.',
                '   02 H. 03 A PIC X VALUE "Z".',
            ],
            [
                "    INITIALIZE G OF R2 A OF H.",
                "    DISPLAY R1 R2.",
            ],
        )
        assert shown == "X7 0 "

    @covers(CobolFeature.RENAMES_CLAUSE)
    def test_renames_takes_the_whole_span_or_the_renamed_item_s_attributes(
        self, capsys
    ):
        shown = _shown(
            capsys,
            [
                "01 W. 02 W1 PIC 9 VALUE 5. 02 W3 PIC XXXX. 02 W4 PIC 9(4).",
                "66 RX RENAMES W3 THRU W4.",
                "66 RN RENAMES W4.",
            ],
            [
                '    MOVE "ABCD1234" TO RX.',
                "    MOVE 77 TO RN.",
                "    DISPLAY W.",
            ],
        )
        assert shown == "5ABCD0077"
