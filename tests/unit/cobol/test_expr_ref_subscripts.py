from __future__ import annotations
from interpreter.cobol.cobol_expression import (
    expr_from_dict,
    FieldRefNode,
    LiteralNode,
    BinOpNode,
)
from tests.covers import covers
from interpreter.cobol.features import CobolFeature


@covers(CobolFeature.OCCURS_FIXED)
def test_ref_node_reads_subscripts_as_expr_nodes():
    """expr_from_dict recurses into each subscript, building ExprNodes (a ref
    subscript becomes a FieldRefNode), not raw strings (red-dragon-l445)."""
    node = expr_from_dict(
        {
            "kind": "ref",
            "name": "WS-ELEM",
            "subscripts": [{"kind": "ref", "name": "WS-IDX"}],
        }
    )
    assert isinstance(node, FieldRefNode)
    assert node.name == "WS-ELEM"
    assert node.subscripts == (FieldRefNode("WS-IDX"),)


@covers(CobolFeature.OCCURS_FIXED)
def test_ref_node_subscript_literal_is_literal_node():
    node = expr_from_dict(
        {
            "kind": "ref",
            "name": "WS-ELEM",
            "subscripts": [{"kind": "lit", "value": "5"}],
        }
    )
    assert isinstance(node, FieldRefNode)
    assert node.subscripts == (LiteralNode("5"),)


@covers(CobolFeature.OCCURS_FIXED)
def test_ref_node_subscript_binop_recurses():
    """An arithmetic subscript WS-I + 1 deserializes to a BinOpNode subtree."""
    node = expr_from_dict(
        {
            "kind": "ref",
            "name": "WS-ELEM",
            "subscripts": [
                {
                    "kind": "binop",
                    "op": "+",
                    "left": {"kind": "ref", "name": "WS-I"},
                    "right": {"kind": "lit", "value": "1"},
                }
            ],
        }
    )
    assert isinstance(node, FieldRefNode)
    assert node.subscripts == (BinOpNode("+", FieldRefNode("WS-I"), LiteralNode("1")),)


@covers(CobolFeature.OCCURS_FIXED)
def test_ref_node_defaults_empty_subscripts():
    node = expr_from_dict({"kind": "ref", "name": "WS-A"})
    assert isinstance(node, FieldRefNode)
    assert node.subscripts == ()
