"""The routine CANCEL runs in the cancelled program: it closes each of the program's
open files that has an internal file connector, and nothing else (red-dragon-idkb)."""

from collections.abc import Sequence

from cobol_asg.asg_types import CobolASG, CobolParagraph
from cobol_asg.call_target import CallTarget
from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.cobol_statements import CancelStatement
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.features import CobolFeature
from interpreter.instructions import (
    CallFunction,
    CallWithMemory,
    Const,
    InstructionBase,
    Label_,
    Return_,
    StoreVar,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.var_name import VarName
from tests.covers import covers

_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FILEPGM.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT OWN-A ASSIGN TO DDA.
           SELECT OWN-B ASSIGN TO DDB.
           SELECT SHARED ASSIGN TO DDS.
       DATA DIVISION.
       FILE SECTION.
       FD  OWN-A.
       01  REC-A        PIC X(4).
       FD  OWN-B.
       01  REC-B        PIC X(4).
       FD  SHARED IS EXTERNAL.
       01  REC-S        PIC X(4).
       PROCEDURE DIVISION.
           GOBACK.
"""


def _routine(ir: Sequence[InstructionBase]) -> Sequence[InstructionBase]:
    start = next(
        n
        for n, i in enumerate(ir)
        if isinstance(i, Label_) and i.label == CodeLabel("func_cancel_filepgm_0")
    )
    end = next(n for n in range(start, len(ir)) if isinstance(ir[n], Return_))
    return ir[start : end + 1]


@covers(CobolFeature.CANCEL)
def test_the_cancel_routine_closes_only_the_internal_files():
    ir = CobolFrontend(make_cobol_parser()).lower(_SOURCE)
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    routine = _routine(ir)
    closes = [
        consts[i.args[0]]
        for i in routine
        if isinstance(i, CallFunction) and str(i.func_name) == "__cobol_close_file"
    ]
    registered = [
        consts[i.value_reg]
        for i in ir
        if isinstance(i, StoreVar) and i.name == VarName("__cancel_FILEPGM")
    ]

    assert (
        [type(i) for i in routine[1:2]],
        str(routine[1].hint),
        closes,
        routine[-1].value_reg,
        registered,
    ) == (
        [Symbolic],
        "param:__call_arguments",
        ["OWN-A", "OWN-B"],
        None,
        ["func_cancel_filepgm_0"],
    )


@covers(CobolFeature.CANCEL)
def test_cancel_calls_the_cancel_routine_the_program_name_selects():
    """The reset arm calls the variable named by '__cancel_' and the name the
    directory held, so the cancelled program's own routine closes its files."""
    ir = CobolFrontend(make_cobol_parser()).lower_from_ast_dict(
        CobolASG(
            paragraphs=[
                CobolParagraph(
                    name="MAIN",
                    statements=[
                        CancelStatement(programs=(CallTarget.of_literal("SUBPROG"),))
                    ],
                )
            ]
        ).to_dict()
    )
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    concats = {
        i.result_reg: [consts.get(a) for a in i.args]
        for i in ir
        if isinstance(i, CallFunction)
        and str(i.func_name) == BuiltinName.STRING_CONCAT_PAIR
    }

    assert [concats[i.location] for i in ir if isinstance(i, CallWithMemory)] == [
        ["__cancel_", "SUBPROG"]
    ]
