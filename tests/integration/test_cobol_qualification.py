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
    run_cobol_programs,
    to_fixed,
    ws_region,
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


def _run_with_files(
    capsys: pytest.CaptureFixture[str],
    environment: Sequence[str],
    file_section: Sequence[str],
    working_storage: Sequence[str],
    procedure: Sequence[str],
    provider: StubIOProvider,
) -> str:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. QUALIO.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            *environment,
            "DATA DIVISION.",
            "FILE SECTION.",
            *file_section,
            "WORKING-STORAGE SECTION.",
            *working_storage,
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            *procedure,
            "    STOP RUN.",
        ]
    )
    run(source=source, language="cobol", max_steps=5000, io_provider=provider)
    return capsys.readouterr().out


def _ebcdic(text: str) -> str:
    return text.encode("cp037").decode("latin-1")


_TWO_RECORDS = [
    '01 R1. 02 F PIC X(4) VALUE "AAAA". 02 K PIC XX VALUE "K1".',
    '01 R2. 02 F PIC X(4) VALUE "BBBB".',
    '01 ST1. 02 FS PIC XX VALUE "S1".',
    '01 ST2. 02 FS PIC XX VALUE "S2".',
]


class TestQualifiedFileOperands:
    @covers(
        CobolFeature.READ_INTO,
        CobolFeature.WRITE_FROM,
        CobolFeature.REWRITE,
        CobolFeature.OPEN,
    )
    def test_file_statements_and_select_clauses_use_the_qualified_items(self, capsys):
        provider = StubIOProvider(
            files={
                "INF": {"records": [_ebcdic("WXYZ")]},
                "IOF": {"records": [_ebcdic("QQQQ")]},
                "KF": {"records": [_ebcdic("-ZZ-")]},
            }
        )
        shown = _run_with_files(
            capsys,
            [
                '    SELECT INF ASSIGN TO "INF" ORGANIZATION SEQUENTIAL',
                "        FILE STATUS IS FS OF ST2.",
                '    SELECT OUTF ASSIGN TO "OUTF" ORGANIZATION SEQUENTIAL.',
                '    SELECT IOF ASSIGN TO "IOF" ORGANIZATION SEQUENTIAL.',
                '    SELECT KF ASSIGN TO "KF" ORGANIZATION INDEXED',
                "        ACCESS MODE IS RANDOM RECORD KEY IS K OF KREC",
                "        FILE STATUS IS FS IN ST1.",
            ],
            [
                "FD INF. 01 INREC PIC X(4).",
                "FD OUTF. 01 OUTREC PIC X(4).",
                "FD IOF. 01 IOREC PIC X(4).",
                "FD KF. 01 KREC. 02 PAD PIC X. 02 K PIC XX. 02 TAIL PIC X.",
            ],
            _TWO_RECORDS,
            [
                "    OPEN INPUT INF KF OUTPUT OUTF I-O IOF.",
                '    MOVE "ZZ" TO K OF KREC.',
                "    READ KF KEY IS K OF KREC.",
                "    MOVE KREC TO F OF R2.",
                "    DISPLAY F OF R2.",
                "    READ INF INTO F OF R2.",
                "    WRITE OUTREC FROM F OF R1.",
                "    WRITE OUTREC FROM F OF R2.",
                "    READ IOF.",
                "    REWRITE IOREC FROM F OF R1.",
                "    DISPLAY F OF R2 FS OF ST1 FS OF ST2.",
            ],
            provider,
        )
        assert (
            shown,
            provider.get_file("OUTF").written,
            provider.get_file("IOF").written,
        ) == (
            "-ZZ-WXYZ0000",
            [_ebcdic("AAAA"), _ebcdic("WXYZ")],
            [_ebcdic("AAAA")],
        )


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
                "01 A1. 02 SUBG. 03 C1 PIC 99 VALUE 11.",
                "01 A2. 02 SUBG. 03 C1 PIC 99 VALUE 22.",
                "01 T. 02 SUBG. 03 C1 PIC 99 VALUE 1.",
            ],
            [
                "    MOVE CORRESPONDING B OF R2 TO DST.",
                "    ADD CORRESPONDING SUBG OF A2 TO SUBG IN T.",
                "    SUBTRACT CORRESPONDING SUBG OF A1 FROM SUBG OF T.",
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

    @covers(CobolFeature.OCCURS_DEPENDING_ON)
    def test_occurs_depending_on_object_is_the_qualified_item(self, capsys):
        shown = _shown(
            capsys,
            [
                "01 GRP-A.",
                "   02 VLEN PIC S9(4) BINARY VALUE 0.",
                "   02 VTEXT.",
                "      03 VCHAR PIC X OCCURS 0 TO 8 TIMES",
                "         DEPENDING ON VLEN OF GRP-A.",
                "01 GRP-B.",
                "   02 VLEN PIC S9(4) BINARY VALUE 0.",
                "   02 VTEXT.",
                "      03 VCHAR PIC X OCCURS 0 TO 8 TIMES",
                "         DEPENDING ON VLEN IN GRP-B.",
            ],
            [
                "    MOVE 3 TO VLEN OF GRP-A.",
                "    MOVE 5 TO VLEN OF GRP-B.",
                '    MOVE "ABCDEFGH" TO VTEXT OF GRP-A.',
                '    MOVE "VWXYZ" TO VTEXT OF GRP-B.',
                "    DISPLAY VTEXT OF GRP-A VTEXT OF GRP-B.",
            ],
        )
        assert shown == "ABCVWXYZ"

    @covers(
        CobolFeature.MOVE, CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION
    )
    def test_length_of_measures_the_qualified_item(self, capsys):
        shown = _shown(
            capsys,
            [
                '01 R1. 02 F PIC X(4) VALUE "AAAA".',
                '01 R2. 02 F PIC X(6) VALUE "BBBBBB".',
                "01 D1 PIC 99.",
                "01 D2 PIC 99.",
                "01 D3 PIC 99.",
            ],
            [
                "    MOVE LENGTH OF F OF R2 TO D1.",
                "    COMPUTE D2 = LENGTH OF F IN R2 + 1.",
                "    PERFORM VARYING D3 FROM LENGTH OF F OF R1 BY 1",
                "        UNTIL D3 > 4",
                "        CONTINUE",
                "    END-PERFORM.",
                "    DISPLAY D1 D2 D3 F OF R2 (1:LENGTH OF F OF R1).",
            ],
        )
        assert shown == "060705BBBB"

    @covers(CobolFeature.STRING_VERB, CobolFeature.UNSTRING_VERB)
    def test_string_and_unstring_pointer_and_tally_are_the_qualified_items(
        self, capsys
    ):
        shown = _shown(
            capsys,
            [
                "01 R1. 02 N PIC 99 VALUE 0.",
                "01 R2. 02 N PIC 99 VALUE 0.",
                "01 OUT1 PIC X(6) VALUE SPACES.",
                "01 O1 PIC XX.",
                "01 O2 PIC XX.",
                '01 SRC PIC X(5) VALUE "AB,CD".',
            ],
            [
                "    MOVE 3 TO N OF R2.",
                '    STRING "XY" DELIMITED BY SIZE INTO OUT1',
                "        WITH POINTER N OF R2.",
                "    MOVE 1 TO N OF R1.",
                '    UNSTRING SRC DELIMITED BY "," INTO O1 O2',
                "        WITH POINTER N OF R1 TALLYING IN N IN R2.",
                "    DISPLAY OUT1 N OF R1 N OF R2 O1 O2.",
            ],
        )
        assert shown == "  XY  0607ABCD"

    @covers(CobolFeature.SEARCH_LINEAR, CobolFeature.SEARCH_VARYING)
    def test_search_advances_the_qualified_tables_index_and_varying_item(self, capsys):
        shown = _shown(
            capsys,
            [
                '01 T1. 02 E PIC X OCCURS 3 INDEXED BY IX VALUE "Q".',
                '01 T2. 02 E PIC X OCCURS 3 INDEXED BY IY VALUE "Q".',
                "01 C1. 02 CNT PIC 9 VALUE 0.",
                "01 C2. 02 CNT PIC 9 VALUE 0.",
            ],
            [
                '    MOVE "Z" TO E OF T2 (2).',
                "    SET IX TO 1.",
                "    SET IY TO 1.",
                "    MOVE 5 TO CNT OF C2.",
                "    SEARCH E OF T2 VARYING CNT IN C2",
                "        AT END MOVE 9 TO CNT OF C1",
                '        WHEN E OF T2 (IY) = "Z" CONTINUE.',
                "    DISPLAY CNT OF C1 CNT OF C2.",
            ],
        )
        assert shown == "06"


_CALLER = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. MAINQ.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    '01 R1. 02 F PIC XX VALUE "AA". 02 G PIC XX VALUE "GG".',
    '01 R2. 02 F PIC XX VALUE "BB". 02 G PIC XX VALUE "HH".',
    '01 T. 02 E PIC XX OCCURS 2 VALUE "EE".',
    "PROCEDURE DIVISION.",
    "    CALL 'SUBQ' USING F OF R2 E OF T (2)",
    "        BY CONTENT G IN R1 ADDRESS OF F OF R2.",
    "    STOP RUN.",
]

_CALLEE = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. SUBQ.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 SEEN PIC XX.",
    "LINKAGE SECTION.",
    "01 LK-A PIC XX.",
    "01 LK-B PIC XX.",
    "01 LK-C PIC XX.",
    "01 LK-P POINTER.",
    "01 LK-R2. 02 LK-F PIC XX. 02 LK-G PIC XX.",
    "PROCEDURE DIVISION USING LK-A LK-B LK-C LK-P.",
    "    MOVE LK-C TO SEEN.",
    '    MOVE "XY" TO LK-A.',
    '    MOVE "ZZ" TO LK-B.',
    '    MOVE "QQ" TO LK-C.',
    "    SET ADDRESS OF LK-R2 TO LK-P.",
    '    MOVE "PP" TO LK-G.',
    "    GOBACK.",
]


class TestQualifiedCallArguments:
    @covers(CobolFeature.CALL_USING, CobolFeature.USING_BY_REFERENCE)
    def test_call_using_passes_the_qualified_and_subscripted_items(self):
        ws = bytes(
            ws_region(run_cobol_programs(_CALLER, {"SUBQ": _CALLEE}), "MAINQ")
        ).decode("cp037")
        assert ws == "AAGGXYPPEEZZ"
