# pyright: standard
"""Tests for COBOL reference modification structures."""

from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_ref_mod_operand_importable():
    from cobol_asg.ref_mod import RefModOperand  # noqa: F401
