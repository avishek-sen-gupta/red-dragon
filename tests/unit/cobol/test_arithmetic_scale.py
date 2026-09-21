"""Static IBM ARITH(COMPAT) scale analysis for COBOL expressions."""

from __future__ import annotations

from types import SimpleNamespace

from cobol_asg.cobol_expression import (
    BinOpNode,
    FieldRefNode,
    FunctionNode,
    LiteralNode,
)
from cobol_asg.cobol_types import CobolDataCategory
from cobol_numeric.scale import Scale
from interpreter.cobol.arithmetic_scale import (
    expression_is_floating,
    field_scale,
    node_scale,
    operand_dmax,
    receiver_decimals,
)
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


def _td(
    total: int, decimals: int, category=CobolDataCategory.ZONED_DECIMAL, scale: int = 0
):
    return SimpleNamespace(
        total_digits=total, decimal_digits=decimals, category=category, scale=scale
    )


_FIELDS = {
    "Y": _td(4, 0),
    "A": _td(5, 2),
    "D": _td(8, 0, CobolDataCategory.COMP2),
}


def _types(name: str, qualifiers: tuple[str, ...] = ()):
    return _FIELDS.get(name)


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_field_scale_includes_pic_p_scaling():
    assert field_scale(_td(5, 2)) == Scale(3, 2)
    assert field_scale(_td(3, 0, scale=2)) == Scale(5, 0)
    assert field_scale(_td(3, 0, scale=-3)) == Scale(1, 3)


@covers(CobolFeature.ROUNDED_CLAUSE)
def test_receiver_decimals_adds_one_for_rounded():
    assert receiver_decimals(_td(3, 0), rounded=False) == 0
    assert receiver_decimals(_td(3, 0), rounded=True) == 1
    assert receiver_decimals(_td(4, 2), rounded=True) == 3


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_mod_idiom_divides_with_zero_decimals():
    node = BinOpNode(
        "*", BinOpNode("/", FieldRefNode("Y"), LiteralNode("4")), LiteralNode("4")
    )
    dmax = max(0, operand_dmax(node, _types))
    assert dmax == 0
    assert node_scale(node.left, dmax, _types) == Scale(4, 0)


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_receiver_decimals_widen_the_quotient():
    node = BinOpNode("/", LiteralNode("7"), LiteralNode("2"))
    assert node_scale(node, 1, _types) == Scale(1, 1)


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_divisor_decimals_do_not_contribute_to_dmax():
    node = BinOpNode("/", FieldRefNode("Y"), FieldRefNode("A"))
    assert operand_dmax(node, _types) == 0
    node2 = BinOpNode("/", FieldRefNode("A"), FieldRefNode("Y"))
    assert operand_dmax(node2, _types) == 2


@covers(CobolFeature.USAGE_COMP_2)
def test_comp2_operand_makes_the_expression_floating():
    assert expression_is_floating(
        BinOpNode("*", FieldRefNode("D"), LiteralNode("2")), _types
    )
    assert not expression_is_floating(
        BinOpNode("*", FieldRefNode("A"), LiteralNode("2")), _types
    )


@covers(CobolFeature.COMPUTE)
def test_floating_point_literals_make_the_expression_floating():
    from interpreter.cobol.arithmetic_scale import is_floating_literal

    assert is_floating_literal("1.5E3")
    assert not is_floating_literal("1.5")
    assert not is_floating_literal("ABC")
    assert expression_is_floating(
        BinOpNode("*", LiteralNode("1.5E3"), LiteralNode("2")), _types
    )
    assert not expression_is_floating(
        BinOpNode("*", LiteralNode("1.5"), LiteralNode("2")), _types
    )


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_floating_intrinsics_make_the_expression_floating():
    assert expression_is_floating(FunctionNode("SQRT", (LiteralNode("2"),)), _types)
    assert not expression_is_floating(FunctionNode("MAX", (FieldRefNode("A"),)), _types)


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_argument_scaled_intrinsics_carry_their_argument_decimals():
    assert node_scale(
        FunctionNode("MAX", (FieldRefNode("A"), LiteralNode("1"))), 0, _types
    ) == Scale(18, 2)
    assert node_scale(
        FunctionNode("MOD", (FieldRefNode("A"), LiteralNode("3"))), 0, _types
    ) == Scale(18, 0)
