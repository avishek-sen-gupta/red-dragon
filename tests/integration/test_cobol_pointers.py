"""COBOL pointers: ADDRESS OF, NULL, USAGE POINTER, SET ADDRESS OF, SET UP BY
and pointer relations."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. PTRMAIN.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-TABLE.",
    "   05 WS-ROW PIC X(2) OCCURS 3.",
    "01 WS-INIT PIC X(6) VALUE 'AABBCC'.",
    "PROCEDURE DIVISION.",
    "    MOVE WS-INIT TO WS-TABLE.",
    "    CALL 'PTRSUB' USING WS-TABLE.",
    "    STOP RUN.",
]

_SUB = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. PTRSUB.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-P USAGE POINTER.",
    "01 WS-Q USAGE POINTER.",
    "01 WS-SEEN PIC X(8) VALUE SPACES.",
    "01 WS-FLAGS PIC X(4) VALUE '----'.",
    "LINKAGE SECTION.",
    "01 LK-TABLE PIC X(6).",
    "01 LK-ROW PIC X(2).",
    "PROCEDURE DIVISION USING LK-TABLE.",
    "    SET WS-P TO ADDRESS OF LK-TABLE.",
    "    SET WS-P UP BY 2.",
    "    SET ADDRESS OF LK-ROW TO WS-P.",
    "    PERFORM READ-ROW.",
    "    SET WS-Q TO ADDRESS OF LK-ROW.",
    "    IF WS-Q = WS-P MOVE 'E' TO WS-FLAGS(1:1).",
    "    IF ADDRESS OF LK-ROW = WS-P MOVE 'A' TO WS-FLAGS(2:1).",
    "    SET WS-Q TO NULL.",
    "    IF WS-Q = NULL MOVE 'N' TO WS-FLAGS(3:1).",
    "    IF WS-P NOT = NULL MOVE 'P' TO WS-FLAGS(4:1).",
    "    MOVE 'ZZ' TO LK-ROW.",
    "    GOBACK.",
    "READ-ROW.",
    "    MOVE LK-ROW TO WS-SEEN(1:2).",
]


@covers(CobolFeature.ADDRESS_OF, CobolFeature.USAGE_POINTER)
def test_set_address_of_rebinds_linkage_for_later_paragraphs() -> None:
    vm = run_cobol_programs(_MAIN, {"PTRSUB": _SUB})
    main = bytes(ws_region(vm, "PTRMAIN"))
    sub = bytes(ws_region(vm, "PTRSUB"))

    assert (
        main[:6].decode("cp037"),
        sub[8:10].decode("cp037"),
        sub[16:20].decode("cp037"),
    ) == ("AAZZCC", "BB", "EANP")


_REDEFINED = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. PTRNUM.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-Q USAGE POINTER.",
    "01 WS-NUM REDEFINES WS-Q PIC S9(9) COMP.",
    "01 WS-X PIC X(2) VALUE 'XY'.",
    "01 WS-DISP PIC 9(9).",
    "PROCEDURE DIVISION.",
    "    SET WS-Q TO ADDRESS OF WS-X.",
    "    SET WS-Q UP BY 1.",
    "    MOVE WS-NUM TO WS-DISP.",
    "    STOP RUN.",
]


@covers(CobolFeature.USAGE_POINTER)
def test_a_pointer_redefined_as_binary_holds_the_address() -> None:
    vm = run_cobol_programs(_REDEFINED, {})
    ws = ws_region(vm, "PTRNUM")
    base = next(
        vm.segment_of(address).base for address, data in vm.region_items() if data is ws
    )

    assert (int.from_bytes(ws[:4], "big"), bytes(ws[6:15]).decode("cp037")) == (
        base + 5,
        f"{base + 5:09d}",
    )


@covers(CobolFeature.ADDRESS_OF)
def test_set_address_of_a_subordinate_item_is_rejected() -> None:
    program = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. PTRBAD.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-P USAGE POINTER.",
        "LINKAGE SECTION.",
        "01 LK-REC.",
        "   05 LK-PART PIC X(2).",
        "PROCEDURE DIVISION USING LK-REC.",
        "    SET ADDRESS OF LK-PART TO WS-P.",
        "    GOBACK.",
    ]

    with pytest.raises(
        ValueError, match="SET ADDRESS OF LK-PART: only a LINKAGE 01 or 77"
    ):
        run_cobol_programs(program, {})


@covers(CobolFeature.ADDRESS_OF)
def test_an_address_handed_to_a_call_reaches_the_callers_item() -> None:
    main = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. ADRMAIN.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-X PIC X(2) VALUE 'AB'.",
        "PROCEDURE DIVISION.",
        "    CALL 'ADRSUB' USING BY VALUE ADDRESS OF WS-X.",
        "    STOP RUN.",
    ]
    sub = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. ADRSUB.",
        "DATA DIVISION.",
        "LINKAGE SECTION.",
        "01 LK-P USAGE POINTER.",
        "01 LK-X PIC X(2).",
        "PROCEDURE DIVISION USING LK-P.",
        "    SET ADDRESS OF LK-X TO LK-P.",
        "    MOVE 'YZ' TO LK-X.",
        "    GOBACK.",
    ]

    ws = bytes(ws_region(run_cobol_programs(main, {"ADRSUB": sub}), "ADRMAIN"))

    assert ws[:2].decode("cp037") == "YZ"
