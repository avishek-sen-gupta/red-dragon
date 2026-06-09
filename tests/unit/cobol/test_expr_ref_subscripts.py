from __future__ import annotations
from interpreter.cobol.cobol_expression import expr_from_dict, FieldRefNode
from tests.covers import covers
from interpreter.cobol.features import CobolFeature


@covers(CobolFeature.OCCURS_FIXED)
def test_ref_node_reads_subscripts():
    node = expr_from_dict({"kind": "ref", "name": "WS-ELEM", "subscripts": ["WS-IDX"]})
    assert isinstance(node, FieldRefNode)
    assert node.name == "WS-ELEM"
    assert node.subscripts == ("WS-IDX",)


@covers(CobolFeature.OCCURS_FIXED)
def test_ref_node_defaults_empty_subscripts():
    node = expr_from_dict({"kind": "ref", "name": "WS-A"})
    assert isinstance(node, FieldRefNode)
    assert node.subscripts == ()
