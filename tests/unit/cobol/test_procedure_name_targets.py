"""A procedure-name that names a section resolves to the section's entry label."""

from __future__ import annotations

from collections.abc import Sequence

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.features import CobolFeature
from interpreter.instructions import Branch, Const, InstructionBase
from interpreter.ir import CodeLabel
from tests.covers import covers


def _lower() -> list[InstructionBase]:
    data = {
        "program_id": "TGTS",
        "data_fields": [
            {
                "name": "WS-IDX",
                "level": 77,
                "pic": "9",
                "usage": "DISPLAY",
                "offset": 0,
                "value": "1",
            },
        ],
        "sections": [
            {
                "name": "MAIN",
                "paragraphs": [
                    {
                        "name": "M1",
                        "statements": [
                            {
                                "type": "ALTER",
                                "proceed_tos": [{"source": "G1", "target": "SEC2"}],
                            },
                            {
                                "type": "GOTO",
                                "form": "computed",
                                "targets": [
                                    {"paragraph": "SEC2", "section": ""},
                                    {"paragraph": "S1", "section": ""},
                                ],
                                "index": {"name": "WS-IDX"},
                            },
                            {
                                "type": "GOTO",
                                "form": "simple",
                                "target": {"paragraph": "SEC2", "section": ""},
                            },
                            {
                                "type": "GOTO",
                                "form": "simple",
                                "target": {"paragraph": "S1", "section": ""},
                            },
                        ],
                    },
                ],
            },
            {
                "name": "SEC2",
                "paragraphs": [
                    {"name": "S1", "statements": [{"type": "STOP_RUN"}]},
                ],
            },
        ],
    }
    return CobolFrontend(make_cobol_parser()).lower_from_ast_dict(data)


def _procedure_branches(instructions: Sequence[InstructionBase]) -> list[CodeLabel]:
    return [
        i.label
        for i in instructions
        if isinstance(i, Branch)
        and (i.label.starts_with("section_") or i.label.starts_with("para_"))
    ]


class TestProcedureNameTargets:
    @covers(CobolFeature.GO_TO, CobolFeature.GOTO_DEPENDING_ON, CobolFeature.ALTER)
    def test_section_names_resolve_to_section_labels(self):
        instructions = _lower()

        assert _procedure_branches(instructions) == [
            CodeLabel("section_SEC2"),
            CodeLabel("para_S1"),
            CodeLabel("section_SEC2"),
            CodeLabel("para_S1"),
        ]
        assert [
            i.value
            for i in instructions
            if isinstance(i, Const) and i.value in ("section_SEC2", "para_SEC2")
        ] == ["section_SEC2"]
