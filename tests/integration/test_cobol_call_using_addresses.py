"""Each callee LINKAGE 01 is bound to its own argument's address.

SHIFT declares LK-FIRST (8 bytes), LK-REC (11), a REDEFINES of LK-REC, and LK-OUT
(7), so their static starts are 0, 8, 8 and 19. The caller passes fields at offsets
13, 2 and 21, so every parameter runs at a non-zero shift (+13, -6, +2): a site
that adds no shift touches the wrong bytes.

Caller WORKING-STORAGE offsets:
- WS-HEAD 0-1;
- WS-REC 2-12 (WS-NUM 2-4, WS-TXT 5-8, WS-TAB 9-12);
- WS-FIRST 13-20;
- WS-OUT 21-27 (WS-NUM 21-23, WS-TXT 24-27);
- WS-SPARE 28-30.
"""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. ADDRS.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-HEAD   PIC X(2)  VALUE 'HH'.",
    "01 WS-REC.",
    "   05 WS-NUM  PIC 9(3) VALUE 5.",
    "   05 WS-TXT  PIC X(4) VALUE 'ABCD'.",
    "   05 WS-TAB  PIC X(2) OCCURS 2 VALUE 'TT'.",
    "01 WS-FIRST  PIC X(8)  VALUE 'FFFFFFFF'.",
    "01 WS-OUT.",
    "   05 WS-NUM  PIC 9(3) VALUE 0.",
    "   05 WS-TXT  PIC X(4) VALUE SPACES.",
    "01 WS-SPARE  PIC X(3)  VALUE 'SSS'.",
    "PROCEDURE DIVISION.",
    "    CALL 'SHIFT' USING WS-FIRST WS-REC WS-OUT.",
    "    CALL 'FEWER' USING WS-SPARE.",
    "    STOP RUN.",
]

_SHIFT = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. SHIFT.",
    "DATA DIVISION.",
    "LINKAGE SECTION.",
    "01 LK-FIRST  PIC X(8).",
    "01 LK-REC.",
    "   05 LK-NUM  PIC 9(3).",
    "   05 LK-TXT  PIC X(4).",
    "   05 LK-TAB  PIC X(2) OCCURS 2.",
    "01 LK-ALIAS REDEFINES LK-REC PIC X(11).",
    "01 LK-OUT.",
    "   05 LK-NUM  PIC 9(3).",
    "   05 LK-OTXT PIC X(4).",
    "PROCEDURE DIVISION USING LK-FIRST LK-REC LK-OUT.",
    "    IF LK-TXT = 'ABCD'",
    "        MOVE 'WXYZ' TO LK-TXT",
    "    END-IF.",
    "    MOVE 'QQ' TO LK-TAB(2).",
    "    ADD CORRESPONDING LK-REC TO LK-OUT.",
    "    MOVE 'R' TO LK-ALIAS(11:1).",
    "    STRING 'ABCDEFGH' DELIMITED BY SIZE INTO LK-FIRST.",
    "    CALL 'PASSDN' USING LK-REC.",
    "    GOBACK.",
]

_DOWN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. PASSDN.",
    "DATA DIVISION.",
    "LINKAGE SECTION.",
    "01 LK-PASSED PIC X(11).",
    "PROCEDURE DIVISION USING LK-PASSED.",
    "    MOVE 'D' TO LK-PASSED(10:1).",
    "    GOBACK.",
]

_FEWER = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. FEWER.",
    "DATA DIVISION.",
    "LINKAGE SECTION.",
    "01 LK-GOT     PIC X(3).",
    "01 LK-NOTHING PIC X(3).",
    "PROCEDURE DIVISION USING LK-GOT LK-NOTHING.",
    "    MOVE LK-NOTHING TO LK-GOT.",
    "    GOBACK.",
]


def _ws() -> str:
    subs = {"SHIFT": _SHIFT, "PASSDN": _DOWN, "FEWER": _FEWER}
    return bytes(ws_region(run_cobol_programs(_MAIN, subs), "ADDRS")).decode("cp037")


@covers(CobolFeature.CALL_USING)
def test_a_shifted_parameter_works_in_every_statement_kind() -> None:
    ws = _ws()

    assert (ws[0:2], ws[2:5], ws[5:9], ws[13:21], ws[21:28]) == (
        "HH",
        "005",
        "WXYZ",
        "ABCDEFGH",
        "005    ",
    )


@covers(CobolFeature.CALL_USING)
def test_a_parameter_passed_down_is_the_original_storage() -> None:
    assert _ws()[9:13] == "TTDR"


@covers(CobolFeature.CALL_USING)
def test_a_redefining_01_reads_through_the_same_argument() -> None:
    assert _ws()[12] == "R"


@covers(CobolFeature.CALL_USING)
def test_a_parameter_the_caller_did_not_pass_reads_zeros() -> None:
    assert _ws()[28:31].encode("cp037") == b"\x00\x00\x00"


_WIDE_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. WIDEM.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-A      PIC X(2)  VALUE 'AB'.",
    "01 WS-B      PIC X(2)  VALUE 'CD'.",
    "PROCEDURE DIVISION.",
    "    CALL 'WIDER' USING WS-A.",
    "    CALL 'NOUSE'.",
    "    STOP RUN.",
]

_WIDER = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. WIDER.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-COPY   PIC X(4)  VALUE 'XXXX'.",
    "LINKAGE SECTION.",
    "01 LK-WIDE   PIC X(4).",
    "PROCEDURE DIVISION USING LK-WIDE.",
    "    MOVE LK-WIDE TO WS-COPY.",
    "    GOBACK.",
]

_NOUSE = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. NOUSE.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-COPY   PIC X(2)  VALUE 'XX'.",
    "LINKAGE SECTION.",
    "01 LK-NONE   PIC X(2).",
    "PROCEDURE DIVISION USING LK-NONE.",
    "    MOVE LK-NONE TO WS-COPY.",
    "    GOBACK.",
]


@covers(CobolFeature.CALL_USING)
def test_a_wider_parameter_reads_the_callers_next_bytes_and_no_using_binds_nothing() -> (
    None
):
    """A parameter declared wider than its argument reads on into the caller's
    following storage, as on a real system; a CALL with no USING passes nothing,
    so the callee's parameter reads zeros, never the caller's WORKING-STORAGE."""
    vm = run_cobol_programs(_WIDE_MAIN, {"WIDER": _WIDER, "NOUSE": _NOUSE})

    assert (
        bytes(ws_region(vm, "WIDER")).decode("cp037"),
        bytes(ws_region(vm, "NOUSE")),
    ) == ("ABCD", b"\x00\x00")


_OVERLAY_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. OVERM.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-A      PIC X(8)  VALUE 'AAAABBBB'.",
    "01 WS-C      PIC X(4)  VALUE 'CCCC'.",
    "01 WS-OUT    PIC X(4)  VALUE SPACES.",
    "01 WS-TAIL   PIC X(8)  VALUE 'TTTTTTTT'.",
    "PROCEDURE DIVISION.",
    "    CALL 'OVERLAY' USING WS-A WS-C WS-OUT.",
    "    CALL 'OVERLAST' USING WS-TAIL.",
    "    STOP RUN.",
]

_OVERLAY = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. OVERLAY.",
    "DATA DIVISION.",
    "LINKAGE SECTION.",
    "01 LK-A      PIC X(4).",
    "01 LK-B REDEFINES LK-A.",
    "   05 LK-B1  PIC X(4).",
    "   05 LK-B2  PIC X(4).",
    "01 LK-C      PIC X(4).",
    "01 LK-OUT    PIC X(4).",
    "PROCEDURE DIVISION USING LK-A LK-C LK-OUT.",
    "    MOVE LK-B2 TO LK-OUT.",
    "    MOVE 'ZZZZ' TO LK-B2.",
    "    GOBACK.",
]

_OVERLAST = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. OVERLAST.",
    "DATA DIVISION.",
    "LINKAGE SECTION.",
    "01 LK-SHORT  PIC X(4).",
    "01 LK-LONG REDEFINES LK-SHORT PIC X(8).",
    "PROCEDURE DIVISION USING LK-SHORT.",
    "    MOVE 'Q' TO LK-LONG(8:1).",
    "    GOBACK.",
]


@covers(CobolFeature.CALL_USING)
def test_a_longer_redefining_01_addresses_through_its_targets_argument() -> None:
    """A REDEFINES 01 longer than the 01 it redefines overlays the caller's
    argument past that 01's own length -- it does not reach into the next
    parameter, and as the last 01 it still lowers."""
    vm = run_cobol_programs(_OVERLAY_MAIN, {"OVERLAY": _OVERLAY, "OVERLAST": _OVERLAST})

    assert bytes(ws_region(vm, "OVERM")).decode("cp037") == (
        "AAAAZZZZ" "CCCC" "BBBB" "TTTTTTTQ"
    )
