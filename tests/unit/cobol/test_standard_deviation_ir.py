"""Tests for FUNCTION STANDARD-DEVIATION as IR: the square root of the population variance."""

from cobol_asg.asg_types import CobolASG
from cobol_asg.cobol_expression import FunctionNode, LiteralNode
from interpreter.cobol.arithmetic_precision import ArithmeticPrecision
from interpreter.cobol.byte_builtins import BYTE_BUILTINS
from interpreter.cobol.condition_lowering import lower_expr_node
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.lowering_scope import LoweringScope
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.cobol.standard_deviation_ir import emit_standard_deviation
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.func_name import FuncName
from interpreter.instructions import CallFunction
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers
from tests.unit.cobol.emitted_ir import ParamValue, run_emitted


def _standard_deviation(*values: ParamValue) -> ParamValue:
    return run_emitted(emit_standard_deviation, values)


def _constraints(value: ParamValue) -> list[str]:
    assert isinstance(value, SymbolicValue)
    return value.constraints


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_square_root_of_the_population_variance():
    assert (
        _standard_deviation(2, 4, 4, 4, 5, 5, 7, 9),
        _standard_deviation(5),
        _constraints(_standard_deviation()),
        FuncName("__standard_deviation") in BYTE_BUILTINS,
    ) == (2, 0, ["__sqrt(__variance())"], False)


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_a_symbolic_argument_flows_through_variance_and_square_root():
    assert _constraints(_standard_deviation(SymbolicValue("x"), 3)) == [
        "__sqrt(__variance(x, 3))"
    ]


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_standard_deviation_lowers_to_variance_and_square_root():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    materialised = lower_sectioned_data_division(
        ctx, build_sectioned_layout(CobolASG(data_fields=[])), "T"
    )
    lower_expr_node(
        LoweringScope(ctx, materialised, None),
        FunctionNode(
            name="STANDARD-DEVIATION", args=(LiteralNode("2"), LiteralNode("4"))
        ),
        ArithmeticPrecision(dmax=0, floating=False),
    )
    assert [
        str(i.func_name)
        for i in ctx.instructions
        if isinstance(i, CallFunction)
        and str(i.func_name) in ("__standard_deviation", "__variance", "__sqrt")
    ] == ["__variance", "__sqrt"]
