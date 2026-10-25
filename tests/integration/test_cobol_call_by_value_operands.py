# pyright: standard
"""CALL BY VALUE refuses at lowering, naming it and its line, an operand IBM Enterprise COBOL refuses."""

import logging

import pytest

from interpreter.cobol.by_value_operand_error import ByValueOperandError
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, ws_region

_REFUSED = (
    ("WS-ZONED", "PIC S9(2)"),
    ("WS-PACKED", "PIC S9(3) COMP-3"),
    ("WS-TWO", "PIC X(2)"),
    ("WS-EDITED", "PIC Z9"),
    ("WS-INDEX", "USAGE INDEX"),
    ("WS-GROUP", ""),
)


def _calling(name: str, clause: str) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. BYVMAIN.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        f"01 {name} {clause}.",
        "   05 WS-PART PIC X." if not clause else "01 WS-PAD PIC X.",
        "PROCEDURE DIVISION.",
        f"    CALL 'BYVSUB' USING BY VALUE {name}.",
        "    STOP RUN.",
    ]


def _refusal(name: str, clause: str) -> str:
    with pytest.raises(ByValueOperandError) as refused:
        run_cobol_programs(_calling(name, clause), {})
    return str(refused.value)


@covers(CobolFeature.USING_BY_VALUE)
def test_by_value_refuses_an_operand_ibm_does_not_pass_by_value() -> None:
    assert [_refusal(name, clause) for name, clause in _REFUSED] == [
        f"line 8: CALL BY VALUE {name}: IBM Enterprise COBOL passes"
        " BY VALUE only an elementary binary, COMP-1, COMP-2 or pointer item, a"
        " single alphanumeric character, or a DISPLAY item reference-modified to"
        " length 1"
        for name, _ in _REFUSED
    ]


def _receiving(name: str, clause: str) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. BYVSUB.",
        "DATA DIVISION.",
        "LINKAGE SECTION.",
        f"01 {name} {clause}.",
        "   05 WS-PART PIC X." if not clause else "01 WS-PAD PIC X.",
        f"PROCEDURE DIVISION USING BY VALUE {name}.",
        "    GOBACK.",
    ]


def _receiving_refusal(name: str, clause: str) -> str:
    with pytest.raises(ByValueOperandError) as refused:
        run_cobol_programs(_receiving(name, clause), {})
    return str(refused.value)


@covers(CobolFeature.USING_BY_VALUE, CobolFeature.PROCEDURE_DIVISION_USING)
def test_procedure_division_using_by_value_refuses_the_same_operands() -> None:
    assert [_receiving_refusal(name, clause) for name, clause in _REFUSED] == [
        f"line 5: PROCEDURE DIVISION USING BY VALUE {name}: IBM Enterprise COBOL passes"
        " BY VALUE only an elementary binary, COMP-1, COMP-2 or pointer item, a"
        " single alphanumeric character, or a DISPLAY item reference-modified to"
        " length 1"
        for name, _ in _REFUSED
    ]


_CALLER = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. BYVMAIN.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-MARK PIC X(6) VALUE 'BEFORE'.",
    "01 WS-TWO PIC X(2) VALUE 'AB'.",
    "PROCEDURE DIVISION.",
    "    CALL 'BYVSUB' USING BY REFERENCE WS-TWO.",
    "    MOVE 'AFTER' TO WS-MARK.",
    "    STOP RUN.",
]


@covers(CobolFeature.USING_BY_VALUE, CobolFeature.PROCEDURE_DIVISION_USING)
def test_a_refused_subprogram_fails_the_run_unless_tolerant(caplog) -> None:
    subprograms = {"BYVSUB": _receiving("WS-TWO", "PIC X(2)")}
    with pytest.raises(ByValueOperandError) as refused:
        run_cobol_programs(_CALLER, subprograms)
    with caplog.at_level(logging.WARNING, logger="interpreter.project.cobol_compile"):
        vm = run_cobol_programs(_CALLER, subprograms, tolerant=True)
    assert (
        str(refused.value),
        [
            record.getMessage()
            for record in caplog.records
            if record.name == "interpreter.project.cobol_compile"
        ],
        bytes(ws_region(vm, "BYVMAIN"))[:6].decode("cp037"),
    ) == (
        "line 5: PROCEDURE DIVISION USING BY VALUE WS-TWO: IBM Enterprise COBOL passes"
        " BY VALUE only an elementary binary, COMP-1, COMP-2 or pointer item, a"
        " single alphanumeric character, or a DISPLAY item reference-modified to"
        " length 1",
        ["compile_cobol: BYVSUB failed to lower — skipping"],
        "AFTER ",
    )
