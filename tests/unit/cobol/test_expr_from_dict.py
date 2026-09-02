# pyright: standard
import pytest

from cobol_asg.cobol_expression import (
    BinOpNode,
    DfhRespNode,
    FieldRefNode,
    FigurativeNode,
    FunctionNode,
    LengthOfNode,
    LiteralNode,
    RefModNode,
    expr_from_dict,
    expr_to_dict,
)
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


class TestExprFromDict:
    @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
    def test_literal_node(self) -> None:
        result = expr_from_dict({"kind": "lit", "value": "42"})
        assert isinstance(result, LiteralNode)
        assert result.value == "42"

    @covers(CobolFeature.COMPUTE)
    def test_field_ref_node(self) -> None:
        result = expr_from_dict({"kind": "ref", "name": "WS-FIELD"})
        assert isinstance(result, FieldRefNode)
        assert result.name == "WS-FIELD"

    @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
    def test_ref_mod_node_with_length(self) -> None:
        result = expr_from_dict(
            {
                "kind": "ref",
                "name": "WS-FIELD",
                "ref_mod_start": {"kind": "lit", "value": "1"},
                "ref_mod_length": {"kind": "lit", "value": "3"},
            }
        )
        assert isinstance(result, RefModNode)
        assert result.name == "WS-FIELD"
        assert result.ref_mod_start == LiteralNode(value="1")
        assert result.ref_mod_length == LiteralNode(value="3")

    @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
    def test_ref_mod_node_without_length(self) -> None:
        result = expr_from_dict(
            {
                "kind": "ref",
                "name": "WS-FIELD",
                "ref_mod_start": {"kind": "lit", "value": "2"},
            }
        )
        assert isinstance(result, RefModNode)
        assert result.ref_mod_length is None

    @covers(CobolFeature.COMPUTE)
    def test_binop_node(self) -> None:
        result = expr_from_dict(
            {
                "kind": "binop",
                "op": "+",
                "left": {"kind": "lit", "value": "10"},
                "right": {"kind": "ref", "name": "WS-B"},
            }
        )
        assert isinstance(result, BinOpNode)
        assert result.op == "+"
        assert result.left == LiteralNode(value="10")
        assert result.right == FieldRefNode(name="WS-B")

    @covers(CobolFeature.COMPUTE)
    def test_neg_node_folds_to_binop(self) -> None:
        result = expr_from_dict({"kind": "neg", "expr": {"kind": "lit", "value": "5"}})
        assert isinstance(result, BinOpNode)
        assert result.op == "*"
        assert result.left == LiteralNode(value="-1")
        assert result.right == LiteralNode(value="5")

    @covers(CobolFeature.COMPUTE, CobolFeature.REFERENCE_MODIFICATION)
    def test_nested_ref_mod_in_binop(self) -> None:
        result = expr_from_dict(
            {
                "kind": "binop",
                "op": "+",
                "left": {
                    "kind": "ref",
                    "name": "WS-FIELD",
                    "ref_mod_start": {"kind": "lit", "value": "1"},
                    "ref_mod_length": {"kind": "lit", "value": "3"},
                },
                "right": {"kind": "lit", "value": "5"},
            }
        )
        assert isinstance(result, BinOpNode)
        assert isinstance(result.left, RefModNode)
        assert result.left.name == "WS-FIELD"
        assert result.left.ref_mod_start == LiteralNode(value="1")
        assert result.left.ref_mod_length == LiteralNode(value="3")
        assert result.right == LiteralNode(value="5")

    @covers(CobolFeature.COMPUTE, CobolFeature.INTRINSIC_FUNCTION)
    def test_function_node_with_ref_arg(self) -> None:
        """An intrinsic FUNCTION operand (red-dragon-ge72) deserializes to a
        FunctionNode carrying its name + structured args, not a bare ref."""
        result = expr_from_dict(
            {
                "kind": "function",
                "name": "UPPER-CASE",
                "args": [{"kind": "ref", "name": "WS-A"}],
            }
        )
        assert isinstance(result, FunctionNode)
        assert result.name == "UPPER-CASE"
        assert result.args == (FieldRefNode(name="WS-A"),)

    @covers(CobolFeature.COMPUTE, CobolFeature.INTRINSIC_FUNCTION)
    def test_nested_function_node(self) -> None:
        """FUNCTION UPPER-CASE(FUNCTION TRIM(WS-A)) deserializes to nested
        FunctionNodes — the inner call + arg survive (red-dragon-ge72)."""
        result = expr_from_dict(
            {
                "kind": "function",
                "name": "UPPER-CASE",
                "args": [
                    {
                        "kind": "function",
                        "name": "TRIM",
                        "args": [{"kind": "ref", "name": "WS-A"}],
                    }
                ],
            }
        )
        assert isinstance(result, FunctionNode)
        assert result.name == "UPPER-CASE"
        inner = result.args[0]
        assert isinstance(inner, FunctionNode)
        assert inner.name == "TRIM"
        assert inner.args == (FieldRefNode(name="WS-A"),)

    @covers(CobolFeature.COMPUTE, CobolFeature.FIGURATIVE_ZEROS)
    def test_figurative_operand_deserializes(self) -> None:
        """``COMPUTE WS-PCT = ZEROES``. The bridge writes the canonical spelling
        it normalises to, so ZERO/ZEROS/ZEROES all arrive as ZEROS."""
        result = expr_from_dict({"kind": "figurative", "value": "ZEROS"})
        assert isinstance(result, FigurativeNode)
        assert result.value == "ZEROS"

    @covers(CobolFeature.COMPUTE, CobolFeature.ARITHMETIC_EXPRESSION)
    def test_length_of_operand_deserializes(self) -> None:
        """LENGTH OF is the field's byte length, a compile-time constant -- not a
        read of the field, so it is not a FieldRefNode."""
        result = expr_from_dict({"kind": "length_of", "name": "WS-A"})
        assert isinstance(result, LengthOfNode)
        assert result.name == "WS-A"

    @covers(CobolFeature.EXEC_CICS)
    def test_dfhresp_operand_deserializes(self) -> None:
        """DFHRESP(NOTFND) keeps the condition NAME: the number the CICS
        translator would substitute is release-dependent."""
        result = expr_from_dict({"kind": "dfhresp", "condition": "NOTFND"})
        assert isinstance(result, DfhRespNode)
        assert result.condition == "NOTFND"

    @covers(CobolFeature.COMPUTE, CobolFeature.FIGURATIVE_ZEROS)
    def test_a_figurative_operand_inside_a_binop_survives(self) -> None:
        """The kind the bridge emits reaches expr_from_dict nested, not just at
        the root -- and one unknown operand costs the whole enclosing member."""
        result = expr_from_dict(
            {
                "kind": "binop",
                "op": "+",
                "left": {"kind": "ref", "name": "WS-A"},
                "right": {"kind": "figurative", "value": "ZEROS"},
            }
        )
        assert isinstance(result, BinOpNode)
        assert result.right == FigurativeNode(value="ZEROS")

    @covers(CobolFeature.EXEC_CICS)
    def test_unknown_kind_raises(self) -> None:
        """An unrecognised kind tag raises ValueError."""
        with pytest.raises(ValueError, match="nonesuch"):
            expr_from_dict({"kind": "nonesuch", "value": "x"})

    @covers(CobolFeature.COMPUTE, CobolFeature.FIGURATIVE_ZEROS)
    def test_the_new_kinds_round_trip_back_to_their_json(self) -> None:
        """expr_to_dict is the inverse, and subscript interiors round-trip
        through it -- a node it cannot write raises just as far up as one
        expr_from_dict cannot read."""
        for d in (
            {"kind": "figurative", "value": "ZEROS"},
            {"kind": "length_of", "name": "WS-A"},
            {"kind": "dfhresp", "condition": "NOTFND"},
        ):
            assert expr_to_dict(expr_from_dict(d)) == d
