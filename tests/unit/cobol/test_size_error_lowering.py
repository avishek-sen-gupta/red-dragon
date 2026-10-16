"""ROUNDED is applied before the size error test, for the arithmetic verbs and COMPUTE alike."""

from __future__ import annotations

from collections.abc import Sequence

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_asg.cobol_expression import LiteralNode
from cobol_asg.cobol_statements import (
    ArithmeticStatement,
    CobolStatementType,
    ComputeStatement,
    ComputeTarget,
    ContinueStatement,
)
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.lower_procedure import lower_procedure_division
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.func_name import FuncName
from interpreter.instructions import CallFunction
from interpreter.register import Register
from tests.covers import covers


def _calls(statements: Sequence[CobolStatementType]) -> list[CallFunction]:
    asg = CobolASG(
        program_id="SIZEERR",
        data_fields=[
            CobolField(name="R", level=77, pic="S99", usage="DISPLAY", offset=0),
            CobolField(name="T", level=77, pic="S99", usage="DISPLAY", offset=2),
        ],
        statements=list(statements),
    )
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    materialised = lower_sectioned_data_division(
        ctx, build_sectioned_layout(asg), asg.program_id
    )
    lower_procedure_division(ctx, asg, materialised)
    return [i for i in ctx.instructions if isinstance(i, CallFunction)]


def _results_of(calls: Sequence[CallFunction], name: str) -> list[Register]:
    return [c.result_reg for c in calls if c.func_name == FuncName(name)]


def _tested_values(calls: Sequence[CallFunction]) -> list[Register]:
    return [
        argument
        for c in calls
        if c.func_name == FuncName(BuiltinName.COBOL_SIZE_ERROR)
        for argument in c.args[:1]
        if isinstance(argument, Register)
    ]


@covers(
    CobolFeature.MULTIPLY,
    CobolFeature.COMPUTE,
    CobolFeature.ROUNDED_CLAUSE,
    CobolFeature.ON_SIZE_ERROR,
)
def test_a_rounded_receiver_is_size_tested_on_its_rounded_value():
    on_size_error: list[CobolStatementType] = [ContinueStatement()]
    calls = _calls(
        [
            ArithmeticStatement(
                op="MULTIPLY",
                operands=[RefModOperand(name="99.4")],
                targets=[
                    RefModOperand(name="R", rounded=True),
                    RefModOperand(name="T"),
                ],
                on_size_error=on_size_error,
            ),
            ComputeStatement(
                expression=LiteralNode("99.4"),
                targets=[ComputeTarget(name="R", rounded=True), ComputeTarget("T")],
                on_size_error=on_size_error,
            ),
        ]
    )
    rounded = _results_of(calls, BuiltinName.COBOL_ROUND)
    tested = _tested_values(calls)
    assert len(rounded) == 2
    assert [value in rounded for value in tested] == [True, False, True, False]
