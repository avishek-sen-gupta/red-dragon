"""An OMITTED or unsupplied parameter is NULL: ADDRESS OF it tests equal to
NULL, a supplied one does not, and under the halting strategy touching the
omitted one stops the run."""

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.vm.halt_on_null import HaltOnNull
from interpreter.vm.null_address_access import NullAddressAccess
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. OMMAIN.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-B PIC X(2) VALUE 'BB'.",
    "PROCEDURE DIVISION.",
    "    CALL 'OMSUB' USING OMITTED WS-B.",
    "    STOP RUN.",
]


def _sub(touch: bool) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. OMSUB.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-SEEN PIC X(3) VALUE '---'.",
        "LINKAGE SECTION.",
        "01 LK-A PIC X(2).",
        "01 LK-B PIC X(2).",
        "01 LK-C PIC X(2).",
        "PROCEDURE DIVISION USING LK-A LK-B LK-C.",
        "    IF ADDRESS OF LK-A = NULL MOVE 'A' TO WS-SEEN(1:1).",
        "    IF ADDRESS OF LK-B NOT = NULL MOVE 'B' TO WS-SEEN(2:1).",
        "    IF ADDRESS OF LK-C = NULL MOVE 'C' TO WS-SEEN(3:1).",
        *(["    MOVE LK-A TO WS-SEEN(1:2)."] if touch else []),
        "    GOBACK.",
    ]


@covers(CobolFeature.CALL_USING_OMITTED, CobolFeature.ADDRESS_OF)
def test_an_omitted_or_unsupplied_parameter_is_null() -> None:
    ws = bytes(ws_region(run_cobol_programs(_MAIN, {"OMSUB": _sub(False)}), "OMSUB"))

    with pytest.raises(NullAddressAccess):
        run_cobol_programs(_MAIN, {"OMSUB": _sub(True)}, null_access=HaltOnNull())
    assert ws[:3].decode("cp037") == "ABC"
