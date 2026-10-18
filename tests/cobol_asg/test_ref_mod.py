# pyright: standard
"""Tests for COBOL reference modification structures."""

from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_ref_mod_operand_importable():
    from cobol_asg.ref_mod import RefModOperand  # noqa: F401


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_operand_keeps_the_kind_the_bridge_stated():
    from cobol_asg.cobol_statements import CallUsingParam
    from cobol_asg.operand_kind import OperandKind
    from cobol_asg.ref_mod import RefModOperand

    written = [
        {"kind": "ref", "name": "W"},
        {"kind": "lit", "name": "'AB'"},
        {"kind": "lit", "name": "'*'", "all": True},
        {"kind": "figurative", "name": "SPACES"},
        {"kind": "length_of", "name": "W"},
    ]
    operands = [RefModOperand.from_dict(d) for d in written]
    param = CallUsingParam.from_dict(
        {"type": "VALUE", "kind": "lit", "name": "5", "numeric": True}
    )

    assert [(o.kind, o.names_data) for o in operands] == [
        (OperandKind.REF, True),
        (OperandKind.LIT, False),
        (OperandKind.LIT, False),
        (OperandKind.FIGURATIVE, False),
        (OperandKind.LENGTH_OF, False),
    ]
    assert [RefModOperand.from_dict(o.to_dict()) for o in operands] == operands
    assert RefModOperand(name="").names_data is False
    assert (param.kind, param.numeric, CallUsingParam.from_dict(param.to_dict())) == (
        OperandKind.LIT,
        True,
        param,
    )
