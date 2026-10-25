# pyright: standard
"""CALL ... LENGTH OF hands the callee the item's length as a binary fullword, BY CONTENT or BY VALUE only."""

import pytest

from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.cobol_statements import CallStatement, CallUsingParam
from cobol_asg.operand_kind import OperandKind
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.length_of_by_reference_error import LengthOfByReferenceError
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, to_fixed, ws_region

_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. LENMAIN.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-X PIC X(5).",
    "01 WS-G.",
    "   05 WS-G-A PIC X(3).",
    "   05 WS-G-B PIC S9(9) COMP.",
    "01 WS-T.",
    "   05 WS-E PIC X(6) OCCURS 3.",
    "PROCEDURE DIVISION.",
    "    CALL 'LENSUB' USING BY CONTENT LENGTH OF WS-X",
    "        BY VALUE LENGTH OF WS-G",
    "        BY CONTENT LENGTH OF WS-E",
    "        BY VALUE LENGTH OF WS-X.",
    "    STOP RUN.",
]

_SUB = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. LENSUB.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-OUT.",
    "   05 WS-A PIC 9(4).",
    "   05 WS-B PIC 9(4).",
    "   05 WS-C PIC 9(4).",
    "   05 WS-D PIC 9(4).",
    "LINKAGE SECTION.",
    "01 LK-A PIC 9(9) BINARY.",
    "01 LK-B PIC 9(9) BINARY.",
    "01 LK-C PIC 9(9) BINARY.",
    "01 LK-D PIC 9(9) BINARY.",
    "PROCEDURE DIVISION USING LK-A BY VALUE LK-B BY REFERENCE LK-C",
    "    BY VALUE LK-D.",
    "    MOVE LK-A TO WS-A.",
    "    MOVE LK-B TO WS-B.",
    "    MOVE LK-C TO WS-C.",
    "    MOVE LK-D TO WS-D.",
    "    GOBACK.",
]


@covers(CobolFeature.CALL_USING, CobolFeature.USING_BY_VALUE)
def test_the_bridge_marks_each_length_of_operand() -> None:
    call = make_cobol_parser().parse(to_fixed(_MAIN).encode()).first_program
    statement = call.statements[0]
    assert isinstance(statement, CallStatement)

    assert statement.using == [
        CallUsingParam(name=name, param_type=mode, kind=OperandKind.LENGTH_OF)
        for name, mode in (
            ("WS-X", "CONTENT"),
            ("WS-G", "VALUE"),
            ("WS-E", "CONTENT"),
            ("WS-X", "VALUE"),
        )
    ]


@covers(CobolFeature.CALL_USING, CobolFeature.USING_BY_VALUE)
def test_the_callee_receives_each_length_as_a_binary_fullword() -> None:
    ws = bytes(ws_region(run_cobol_programs(_MAIN, {"LENSUB": _SUB}), "LENSUB"))

    assert ws[:16].decode("cp037") == "0005000700060005"


@covers(CobolFeature.CALL_USING)
def test_length_of_by_reference_is_refused() -> None:
    main = [
        line.replace("BY CONTENT LENGTH OF WS-X", "BY REFERENCE LENGTH OF WS-X")
        for line in _MAIN
    ]

    with pytest.raises(LengthOfByReferenceError) as refused:
        run_cobol_programs(main, {"LENSUB": _SUB})

    assert str(refused.value) == (
        "line 12: CALL BY REFERENCE LENGTH OF WS-X: IBM Enterprise COBOL passes"
        " the LENGTH OF special register only BY CONTENT or BY VALUE"
    )
