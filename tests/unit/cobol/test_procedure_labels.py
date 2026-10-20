"""ProcedureLabels: the labels that name a program's sections and paragraphs."""

from __future__ import annotations

from collections.abc import Mapping

from cobol_asg.asg_types import CobolASG, CobolParagraph, CobolSection
from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.lower_procedure import lower_procedure_division
from interpreter.cobol.procedure_labels import procedure_labels
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.continuation_name import ContinuationName
from interpreter.instructions import Branch, Label_, SetContinuation
from interpreter.ir import CodeLabel
from tests.covers import covers


def _section(name: str, *paragraphs: str) -> CobolSection:
    return CobolSection(
        name=name, paragraphs=[CobolParagraph(name=p) for p in paragraphs]
    )


class TestProcedureLabels:
    @covers(CobolFeature.PERFORM, CobolFeature.GO_TO)
    def test_procedure_names_fold_case(self):
        labels = procedure_labels([_section("Main", "Work")], [])

        assert [labels.is_section(n) for n in ("main", "MAIN", "work")] == [
            True,
            True,
            False,
        ]
        assert [labels.procedure(n, "", "main") for n in ("main", "Work", "WORK")] == [
            CodeLabel("section_MAIN"),
            CodeLabel("para_WORK"),
            CodeLabel("para_WORK"),
        ]
        assert (
            labels.section("mAIN"),
            labels.section_exit("Main"),
            labels.section_end("main"),
        ) == (
            CodeLabel("section_MAIN"),
            CodeLabel("section_MAIN_exit"),
            ContinuationName("section_MAIN_end"),
        )
        assert (
            labels.paragraph("work", "main"),
            labels.paragraph_exit("wOrk", "Main"),
            labels.paragraph_end("Work", "MAIN"),
            labels.sentence_exit("work", "main", 2),
        ) == (
            CodeLabel("para_WORK"),
            CodeLabel("para_WORK_exit"),
            ContinuationName("para_WORK_end"),
            CodeLabel("para_WORK_sentence_2_exit"),
        )

    @covers(CobolFeature.PERFORM, CobolFeature.GO_TO)
    def test_a_paragraph_name_declared_twice_is_labelled_by_its_section(self):
        labels = procedure_labels(
            [_section("S1", "INIT", "WORK"), _section("S2", "INIT", "LAST")],
            [],
        )

        assert [
            labels.paragraph(p, s) for p, s in (("init", "s1"), ("INIT", "S2"))
        ] == [
            CodeLabel("para_S1_INIT"),
            CodeLabel("para_S2_INIT"),
        ]
        assert labels.paragraph_end("init", "s2") == ContinuationName(
            "para_S2_INIT_end"
        )
        assert [
            labels.procedure(name, qualifier, current)
            for name, qualifier, current in (
                ("INIT", "", "S1"),
                ("INIT", "", "S2"),
                ("INIT", "S2", "S1"),
                ("init", "s1", "S2"),
                ("LAST", "", "S1"),
                ("WORK", "", "S2"),
                ("S2", "", "S1"),
            )
        ] == [
            CodeLabel("para_S1_INIT"),
            CodeLabel("para_S2_INIT"),
            CodeLabel("para_S2_INIT"),
            CodeLabel("para_S1_INIT"),
            CodeLabel("para_LAST"),
            CodeLabel("para_WORK"),
            CodeLabel("section_S2"),
        ]

    @covers(CobolFeature.PERFORM, CobolFeature.PERFORM_THRU)
    def test_a_procedure_ends_where_its_section_or_paragraph_resumes(self):
        labels = procedure_labels(
            [_section("S1", "INIT", "WORK"), _section("S2", "INIT")], []
        )

        assert [
            labels.procedure_end(name, qualifier, current)
            for name, qualifier, current in (
                ("s2", "", "S1"),
                ("WORK", "", "S2"),
                ("INIT", "", "S2"),
                ("INIT", "S1", "S2"),
            )
        ] == [
            ContinuationName("section_S2_end"),
            ContinuationName("para_WORK_end"),
            ContinuationName("para_S2_INIT_end"),
            ContinuationName("para_S1_INIT_end"),
        ]

    @covers(CobolFeature.PERFORM, CobolFeature.PERFORM_THRU)
    def test_perform_of_section_reaches_that_sections_paragraph(self):
        work = {"name": "WORK", "statements": [{"type": "CONTINUE"}]}
        instructions = CobolFrontend(make_cobol_parser()).lower_from_ast_dict(
            {
                "program_id": "QUALPFM",
                "data_fields": [],
                "sections": [
                    {
                        "name": "S1",
                        "paragraphs": [
                            {
                                "name": "INIT",
                                "statements": [
                                    {
                                        "type": "PERFORM",
                                        "operands": ["WORK"],
                                        "target_section": "S2",
                                    },
                                    {
                                        "type": "PERFORM",
                                        "operands": ["INIT"],
                                        "thru": "WORK",
                                    },
                                ],
                            },
                            work,
                        ],
                    },
                    {
                        "name": "S2",
                        "paragraphs": [
                            {"name": "INIT", "statements": [{"type": "STOP_RUN"}]},
                            work,
                        ],
                    },
                ],
            }
        )

        assert [
            (str(i.name), str(i.target_label))
            for i in instructions
            if isinstance(i, SetContinuation) and str(i.name).startswith("para_")
        ] == [
            ("para_S2_WORK_end", "perform_return_0"),
            ("para_S1_WORK_end", "perform_return_1"),
        ]
        assert [
            i.label
            for i in instructions
            if isinstance(i, Branch) and i.label.starts_with("para_")
        ] == [
            CodeLabel("para_S2_WORK"),
            CodeLabel("para_S1_INIT"),
        ]
        assert [
            i.label
            for i in instructions
            if isinstance(i, Label_) and i.label.starts_with("para_")
        ] == [
            CodeLabel("para_S1_INIT"),
            CodeLabel("para_S1_WORK"),
            CodeLabel("para_S2_INIT"),
            CodeLabel("para_S2_WORK"),
        ]


class _EntrySpy:
    name = "entry-spy"

    def __init__(self) -> None:
        self.seen: list[CodeLabel] = []

    def handles(self, stmt: object) -> bool:
        return False

    def preprocess_program_dict(self, data: Mapping[str, str]) -> dict[str, str]:
        return dict(data)

    def on_procedure_entry(self, ctx: EmitContext, materialised: object) -> None:
        self.seen = [
            ctx.procedures.procedure("err-para", "", "SEC-B"),
            ctx.procedures.procedure("sec-a", "", ""),
        ]

    def lower(self, ctx: EmitContext, stmt: object, materialised: object) -> None:
        pass


class TestProcedureLabelsAtProcedureEntry:
    @covers(CobolFeature.PERFORM, CobolFeature.GO_TO)
    def test_an_extension_sees_the_programs_labels_on_procedure_entry(self):
        """An extension lowering strategy emits branches to the program's own
        procedures from on_procedure_entry, so the labels exist by then."""
        asg = CobolASG(
            program_id="ENTRY",
            sections=[_section("SEC-A", "ERR-PARA"), _section("SEC-B", "ERR-PARA")],
        )
        spy = _EntrySpy()
        ctx = EmitContext(dispatch_fn=dispatch_statement, extension_strategies=[spy])
        materialised = lower_sectioned_data_division(
            ctx, build_sectioned_layout(asg), "ENTRY"
        )

        lower_procedure_division(ctx, asg, materialised)

        assert spy.seen == [
            CodeLabel("para_SEC-B_ERR-PARA"),
            CodeLabel("section_SEC-A"),
        ]
