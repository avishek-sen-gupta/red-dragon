# pyright: standard
from interpreter.cobol.cobol_expression import (
    BinOpNode,
    FieldRefNode,
    FunctionNode,
    LiteralNode,
    RefModNode,
    expr_from_dict,
)
from tests.covers import covers
from interpreter.cobol.features import CobolFeature


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

    @covers(CobolFeature.EXEC_CICS)
    def test_unknown_kind_raises(self) -> None:
        """An unrecognised kind tag raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="dfhresp"):
            expr_from_dict({"kind": "dfhresp", "condition": "NOTFND"})
