"""An intrinsic function's arithmetic-expression argument is lowered with its
enclosing statement's precision, not as a bare integer Binop."""

from __future__ import annotations

from cobol_asg.asg_types import CobolASG
from cobol_asg.cobol_expression import BinOpNode, FunctionNode, LiteralNode
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.condition_lowering import lower_expr_node
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.func_name import FuncName
from interpreter.instructions import Binop, CallFunction, Const
from interpreter.register import Register

_DIVISION = BinOpNode(op="/", left=LiteralNode("3"), right=LiteralNode("2"))


def _lowered(node: FunctionNode, receiver_decimals: int) -> EmitContext:
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    materialised = lower_sectioned_data_division(
        ctx, build_sectioned_layout(CobolASG(data_fields=[])), "T"
    )
    lower_expr_node(ctx, node, materialised, receiver_decimals=receiver_decimals)
    return ctx


def _divide_decimals(ctx: EmitContext) -> list[int]:
    consts = {i.result_reg: i.value for i in ctx.instructions if isinstance(i, Const)}
    return [
        consts[i.args[2]]
        for i in ctx.instructions
        if isinstance(i, CallFunction)
        and i.func_name == FuncName(BuiltinName.COBOL_DIVIDE)
        and isinstance(i.args[2], Register)
    ]


def test_fixed_point_argument_divides_with_the_statement_dmax():
    ctx = _lowered(FunctionNode(name="REM", args=(_DIVISION, LiteralNode("2"))), 6)
    assert _divide_decimals(ctx) == [6]


def test_floating_point_function_argument_divides_in_floating_point():
    ctx = _lowered(FunctionNode(name="SQRT", args=(_DIVISION,)), 0)
    assert (
        _divide_decimals(ctx),
        [i.operator.value for i in ctx.instructions if isinstance(i, Binop)],
    ) == ([], ["/"])
