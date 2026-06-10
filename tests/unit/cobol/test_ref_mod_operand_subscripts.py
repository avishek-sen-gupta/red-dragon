from __future__ import annotations
from interpreter.cobol.ref_mod import RefModOperand
from interpreter.cobol.cobol_expression import FieldRefNode, LiteralNode
from tests.covers import covers
from interpreter.cobol.features import CobolFeature


@covers(CobolFeature.OCCURS_FIXED)
def test_refmodoperand_reads_structured_subscripts_as_expr_nodes():
    """Subscripts deserialize to ExprNodes via expr_from_dict (red-dragon-l445)."""
    op = RefModOperand.from_dict(
        {"name": "WS-ELEM", "subscripts": [{"kind": "ref", "name": "WS-IDX"}]}
    )
    assert op.name == "WS-ELEM"
    assert op.subscripts == (FieldRefNode("WS-IDX"),)


@covers(CobolFeature.OCCURS_FIXED)
def test_refmodoperand_defaults_empty_subscripts():
    op = RefModOperand.from_dict({"name": "WS-A"})
    assert op.subscripts == ()


@covers(CobolFeature.OCCURS_FIXED)
def test_refmodoperand_roundtrips_subscripts():
    op = RefModOperand.from_dict(
        {
            "name": "T",
            "subscripts": [
                {"kind": "ref", "name": "I"},
                {"kind": "lit", "value": "2"},
            ],
        }
    )
    assert op.subscripts == (FieldRefNode("I"), LiteralNode("2"))
    assert op.to_dict()["subscripts"] == [
        {"kind": "ref", "name": "I"},
        {"kind": "lit", "value": "2"},
    ]
