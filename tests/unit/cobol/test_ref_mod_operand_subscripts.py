from __future__ import annotations

from interpreter.cobol.cobol_expression import FieldRefNode, LiteralNode
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.ref_mod import RefModLiteral, RefModOperand, RefModReference
from tests.covers import covers


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


@covers(CobolFeature.OCCURS_FIXED)
def test_refmodoperand_combined_subscript_and_refmod_roundtrip():
    """A subscripted reference-modified field round-trips from_dict→to_dict exactly.

    Legal COBOL: WS-TABLE(I)(2:3) — subscript selects the element, ref-mod
    slices bytes within it. Both subscripts (via expr_to_dict) and ref-mod
    (via _ref_mod_expr_to_dict) must survive the round-trip unchanged.
    """
    raw = {
        "name": "WS-TABLE",
        "subscripts": [{"kind": "ref", "name": "WS-IDX"}],
        "ref_mod_start": {"kind": "lit", "value": "2"},
        "ref_mod_length": {"kind": "ref", "name": "WS-LEN"},
    }
    op = RefModOperand.from_dict(raw)

    # Structural assertions
    assert op.name == "WS-TABLE"
    assert op.subscripts == (FieldRefNode("WS-IDX"),)
    assert op.ref_mod_start == RefModLiteral("2")
    assert op.ref_mod_length == RefModReference("WS-LEN")

    # Round-trip: to_dict must reproduce the original dict exactly
    assert op.to_dict() == raw
