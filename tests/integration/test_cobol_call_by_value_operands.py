# pyright: standard
"""CALL BY VALUE refuses at lowering, naming it and its line, an operand IBM Enterprise COBOL refuses."""

import pytest

from interpreter.cobol.by_value_operand_error import ByValueOperandError
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs

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
        f"line 8: CALL BY VALUE {name}: IBM Enterprise COBOL passes BY VALUE only"
        " an elementary binary, COMP-1, COMP-2 or pointer item, or a single"
        " alphanumeric character"
        for name, _ in _REFUSED
    ]
