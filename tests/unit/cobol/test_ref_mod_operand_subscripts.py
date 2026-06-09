from __future__ import annotations
from interpreter.cobol.ref_mod import RefModOperand
from tests.covers import covers
from interpreter.cobol.features import CobolFeature


@covers(CobolFeature.OCCURS_FIXED)
def test_refmodoperand_reads_structured_subscripts():
    op = RefModOperand.from_dict({"name": "WS-ELEM", "subscripts": ["WS-IDX"]})
    assert op.name == "WS-ELEM"
    assert op.subscripts == ("WS-IDX",)


@covers(CobolFeature.OCCURS_FIXED)
def test_refmodoperand_defaults_empty_subscripts():
    op = RefModOperand.from_dict({"name": "WS-A"})
    assert op.subscripts == ()


@covers(CobolFeature.OCCURS_FIXED)
def test_refmodoperand_roundtrips_subscripts():
    op = RefModOperand.from_dict({"name": "T", "subscripts": ["I", "J"]})
    assert op.to_dict()["subscripts"] == ["I", "J"]
