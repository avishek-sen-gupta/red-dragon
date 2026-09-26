# pyright: standard
"""Tests for COBOL DECLARATIVES handling (red-dragon-m0oa.3)."""

from __future__ import annotations

from cobol_asg.asg_types import CobolASG
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


from cobol_asg.asg_types import CobolParagraph, CobolSection
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
        # A real EmitContext and layout rather than a stub: the implicit program
        # exit reads RETURN-CODE out of the special-register region, so lowering
        # a procedure division now needs a materialised layout to exist.
        from interpreter.cobol.emit_context import EmitContext
        from interpreter.cobol.lower_data_division import (
            lower_sectioned_data_division,
        )
        from interpreter.cobol.sectioned_layout import build_sectioned_layout
        from interpreter.cobol.statement_dispatch import dispatch_statement

        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(
            ctx, build_sectioned_layout(asg), "DECLTEST"
        )

        lower_procedure_division(ctx, asg, materialised)
        labels = _labels(ctx.instructions)
        # The real section label must appear before the declaratives section label.
        assert labels.index("section_MAIN") < labels.index("section_ERR-SECTION")
        # Declaratives paragraphs registered for PERFORM THRU resolution.
        assert ctx.section_paragraphs["ERR-SECTION"] == ["ERR-PARA"]
