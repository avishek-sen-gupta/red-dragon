"""CALL USING passes one address per argument, by position.

Each case below is one way packing the arguments into a single buffer, at the
caller's sizes, departs from that: a literal or OMITTED argument that takes no
slot, a parameter declared shorter than its argument, and one field passed twice.
"""

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. SLOTS.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-X     PIC X(2) VALUE 'ZZ'.",
    "01 WS-Y     PIC X(2) VALUE 'ZZ'.",
    "01 WS-L     PIC X(6) VALUE 'LLLLLL'.",
    "01 WS-M     PIC X(2) VALUE 'ZZ'.",
    "01 WS-P     PIC X(2) VALUE 'ZZ'.",
    "01 WS-R     PIC X(2) VALUE 'ZZ'.",
    "PROCEDURE DIVISION.",
    "    CALL 'LITSUB' USING BY CONTENT 'AB' BY REFERENCE WS-X.",
    "    CALL 'OMITSUB' USING OMITTED WS-Y.",
    "    CALL 'SIZESUB' USING WS-L WS-M.",
    "    CALL 'TWICESUB' USING WS-P WS-P WS-R.",
    "    STOP RUN.",
]


def _sub(name: str, linkage: list[str], using: str, body: list[str]) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        f"PROGRAM-ID. {name}.",
        "DATA DIVISION.",
        "LINKAGE SECTION.",
        *linkage,
        f"PROCEDURE DIVISION USING {using}.",
        *body,
        "    GOBACK.",
    ]


_SUBS = {
    "LITSUB": _sub(
        "LITSUB",
        ["01 LK-1 PIC X(2).", "01 LK-2 PIC X(2)."],
        "LK-1 LK-2",
        ["    MOVE LK-1 TO LK-2."],
    ),
    "OMITSUB": _sub(
        "OMITSUB",
        ["01 LK-1 PIC X(2).", "01 LK-2 PIC X(2)."],
        "LK-1 LK-2",
        ["    MOVE LK-1 TO LK-2."],
    ),
    "SIZESUB": _sub(
        "SIZESUB",
        ["01 LK-A PIC X(4).", "01 LK-B PIC X(2)."],
        "LK-A LK-B",
        ["    MOVE 'OK' TO LK-B."],
    ),
    "TWICESUB": _sub(
        "TWICESUB",
        ["01 LK-1 PIC X(2).", "01 LK-2 PIC X(2).", "01 LK-3 PIC X(2)."],
        "LK-1 LK-2 LK-3",
        ["    MOVE 'AA' TO LK-1.", "    MOVE LK-2 TO LK-3."],
    ),
}


def _fields() -> dict[str, str]:
    ws = ws_region(run_cobol_programs(_MAIN, _SUBS), "SLOTS")
    text = bytes(ws).decode("cp037")
    return {
        "WS-X": text[0:2],
        "WS-Y": text[2:4],
        "WS-L": text[4:10],
        "WS-M": text[10:12],
        "WS-P": text[12:14],
        "WS-R": text[14:16],
    }


@covers(CobolFeature.CALL_USING_LITERAL)
def test_a_literal_argument_takes_its_slot() -> None:
    assert _fields()["WS-X"] == "AB"


@covers(CobolFeature.CALL_USING_OMITTED)
def test_an_omitted_argument_takes_its_slot() -> None:
    """The callee copies its OMITTED first parameter into its second: the
    second is the caller's WS-Y, and the first reads as zeros."""
    assert _fields()["WS-Y"].encode("cp037") == b"\x00\x00"


@covers(CobolFeature.CALL_USING)
def test_a_shorter_parameter_does_not_shift_the_next() -> None:
    assert (_fields()["WS-L"], _fields()["WS-M"]) == ("LLLLLL", "OK")


@covers(CobolFeature.CALL_USING)
def test_a_field_passed_twice_is_one_storage() -> None:
    assert (_fields()["WS-P"], _fields()["WS-R"]) == ("AA", "AA")
