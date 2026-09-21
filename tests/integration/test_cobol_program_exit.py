"""Control returns to the caller from every way a program can end.

A PROCEDURE DIVISION need not end in GOBACK or EXIT PROGRAM: running off its last
statement is a legal program exit and must return control to the caller, exactly
as GOBACK does. Without a terminal return the callee's instruction pointer simply
runs on past the end of its own body into whatever the linker placed next.
"""

from __future__ import annotations

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_FALLS_OFF_END = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. NOGOBACK.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-RAN PIC X(4) VALUE 'NNNN'.",
    "PROCEDURE DIVISION.",
    "    MOVE 'YYYY' TO WS-RAN.",
]

_CALLER = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. EXITCLR.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-RESUMED PIC X(4) VALUE 'NNNN'.",
    "PROCEDURE DIVISION.",
    "    CALL 'NOGOBACK'.",
    "    MOVE 'YYYY' TO WS-RESUMED.",
    "    GOBACK.",
]


@covers(CobolFeature.CALL)
def test_call_to_program_without_goback_returns_to_caller():
    """A callee that runs off the end of its PROCEDURE DIVISION returns control."""
    vm = run_cobol_programs(_CALLER, {"NOGOBACK": _FALLS_OFF_END})

    assert bytes(ws_region(vm, "NOGOBACK")) == "YYYY".encode(
        "cp037"
    ), "the callee's own body should have run"
    assert bytes(ws_region(vm, "EXITCLR")) == "YYYY".encode(
        "cp037"
    ), "control should have come back to the statement after the CALL"
