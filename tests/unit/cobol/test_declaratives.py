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


from interpreter.cobol.asg_types import CobolParagraph, CobolSection
from interpreter.instructions import Label_


def _labels(instructions) -> list[str]:
    return [str(i.label) for i in instructions if isinstance(i, Label_)]


class TestDeclarativesLoweringOrder:
    @covers(CobolFeature.DECLARATIVES)
    def test_declaratives_section_emitted_after_real_section(self):
        from interpreter.cobol.lower_procedure import lower_procedure_division

        asg = CobolASG(
            program_id="DECLTEST",
            sections=[
                CobolSection(name="MAIN", paragraphs=[CobolParagraph(name="MAIN-PARA")])
            ],
            declaratives=[
                CobolSection(
                    name="ERR-SECTION", paragraphs=[CobolParagraph(name="ERR-PARA")]
                )
            ],
        )
        # Minimal EmitContext stub: only the attributes lower_procedure_division touches.
        emitted: list = []

        class _Ctx:
            extension_strategies = []
            section_paragraphs: dict = {}

            def emit_inst(self, inst):
                emitted.append(inst)

            def lower_statement(self, stmt, materialised):
                pass

        ctx = _Ctx()
        lower_procedure_division(ctx, asg, materialised=None)
        labels = _labels(emitted)
        # The real section label must appear before the declaratives section label.
        assert labels.index("section_MAIN") < labels.index("section_ERR-SECTION")
        # Declaratives paragraphs registered for PERFORM THRU resolution.
        assert ctx.section_paragraphs["ERR-SECTION"] == ["ERR-PARA"]
