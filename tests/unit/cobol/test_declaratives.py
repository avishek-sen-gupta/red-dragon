# pyright: standard
"""Tests for COBOL DECLARATIVES handling (red-dragon-m0oa.3)."""

from __future__ import annotations

from interpreter.cobol.asg_types import CobolASG
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


def _asg_with_declaratives() -> dict:
    """A minimal bridge-shaped dict: one declaratives section + one real section."""
    return {
        "program_id": "DECLTEST",
        "declaratives": [
            {
                "name": "ERR-SECTION",
                "paragraphs": [{"name": "ERR-PARA", "statements": []}],
            }
        ],
        "sections": [
            {
                "name": "MAIN",
                "paragraphs": [{"name": "MAIN-PARA", "statements": []}],
            }
        ],
    }


class TestDeclarativesModel:
    @covers(CobolFeature.DECLARATIVES)
    def test_from_dict_populates_declaratives(self):
        asg = CobolASG.from_dict(_asg_with_declaratives())
        assert len(asg.declaratives) == 1
        assert asg.declaratives[0].name == "ERR-SECTION"
        assert asg.declaratives[0].paragraphs[0].name == "ERR-PARA"

    @covers(CobolFeature.DECLARATIVES)
    def test_declaratives_roundtrip_to_dict(self):
        asg = CobolASG.from_dict(_asg_with_declaratives())
        out = asg.to_dict()
        assert out["declaratives"][0]["name"] == "ERR-SECTION"

    @covers(CobolFeature.DECLARATIVES)
    def test_no_declaratives_is_empty_list(self):
        asg = CobolASG.from_dict({"program_id": "X"})
        assert asg.declaratives == []
