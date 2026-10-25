# pyright: standard
"""A reference-modified CALL operand hands the callee its substring, in every argument mode."""

import pytest

from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.cobol_statements import CallStatement, CallUsingParam
from cobol_asg.ref_mod import RefModLiteral, RefModOperand, RefModReference
from interpreter.cobol.by_value_operand_error import ByValueOperandError
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import run_cobol_programs, to_fixed, ws_region

_MAIN = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. RMMAIN.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-X PIC X(8) VALUE 'ABCDEFGH'.",
    "01 WS-Y PIC X(8) VALUE 'STUVWXYZ'.",
    "01 WS-S PIC 9(2) VALUE 3.",
    "01 WS-L PIC 9(2) VALUE 2.",
    "PROCEDURE DIVISION.",
    "    CALL 'RMSUB' USING BY REFERENCE WS-X(2:3)",
    "        BY CONTENT WS-X(WS-S:WS-L)",
    "        BY VALUE WS-X(8:1)",
    "        BY REFERENCE WS-Y(WS-S:WS-L)",
    "        BY CONTENT WS-Y(7:).",
    "    STOP RUN.",
]

_SUB = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. RMSUB.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-SEEN PIC X(10).",
    "LINKAGE SECTION.",
    "01 LK-A PIC X(3).",
    "01 LK-B PIC X(2).",
    "01 LK-C PIC X.",
    "01 LK-D PIC X(2).",
    "01 LK-E PIC X(2).",
    "PROCEDURE DIVISION USING LK-A LK-B BY VALUE LK-C",
    "    BY REFERENCE LK-D LK-E.",
    "    STRING LK-A LK-B LK-C LK-D LK-E DELIMITED BY SIZE",
    "        INTO WS-SEEN.",
    "    MOVE 'xyz' TO LK-A.",
    "    MOVE 'qq' TO LK-B.",
    "    MOVE '12' TO LK-D.",
    "    MOVE 'rr' TO LK-E.",
    "    GOBACK.",
]


def _sliced(name: str, start: str, length: str = "") -> RefModOperand:
    return RefModOperand(
        name=name,
        ref_mod_start=_bound(start),
        ref_mod_length=_bound(length) if length else None,
    )


def _bound(text: str) -> RefModLiteral | RefModReference:
    return RefModLiteral(text) if text.isdigit() else RefModReference(text)


@covers(CobolFeature.CALL_USING)
def test_the_bridge_keeps_each_operand_reference_modification() -> None:
    program = make_cobol_parser().parse(to_fixed(_MAIN).encode()).first_program
    statement = program.statements[0]
    assert isinstance(statement, CallStatement)

    assert statement.using == [
        CallUsingParam(name=name, param_type=mode, ref_mod=_sliced(name, *bounds))
        for name, mode, bounds in (
            ("WS-X", "REFERENCE", ("2", "3")),
            ("WS-X", "CONTENT", ("WS-S", "WS-L")),
            ("WS-X", "VALUE", ("8", "1")),
            ("WS-Y", "REFERENCE", ("WS-S", "WS-L")),
            ("WS-Y", "CONTENT", ("7",)),
        )
    ]


@covers(CobolFeature.CALL_USING, CobolFeature.USING_BY_VALUE)
def test_the_callee_sees_each_substring_and_writes_back_only_by_reference() -> None:
    vm = run_cobol_programs(_MAIN, {"RMSUB": _SUB})

    assert (
        bytes(ws_region(vm, "RMSUB"))[:10].decode("cp037"),
        bytes(ws_region(vm, "RMMAIN"))[:16].decode("cp037"),
    ) == ("BCDCDHUVYZ", "AxyzEFGHST12WXYZ")


@covers(CobolFeature.USING_BY_VALUE)
def test_by_value_refuses_a_reference_modification_not_of_length_one() -> None:
    def refusal(operand: str) -> str:
        main = [line.replace("WS-X(8:1)", operand) for line in _MAIN]
        with pytest.raises(ByValueOperandError) as refused:
            run_cobol_programs(main, {"RMSUB": _SUB})
        return str(refused.value)

    assert [refusal(operand) for operand in ("WS-X(7:2)", "WS-X(1:WS-L)")] == [
        "line 10: CALL BY VALUE WS-X: IBM Enterprise COBOL passes BY VALUE only an"
        " elementary binary, COMP-1, COMP-2 or pointer item, or a single"
        " alphanumeric character"
    ] * 2
