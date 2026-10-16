"""ProcedureLabels: the labels that name a program's sections and paragraphs."""

from __future__ import annotations

from cobol_asg.asg_types import CobolParagraph, CobolSection
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.procedure_labels import procedure_labels
from interpreter.continuation_name import ContinuationName
from interpreter.ir import CodeLabel
from tests.covers import covers


class TestProcedureLabels:
    @covers(CobolFeature.PERFORM, CobolFeature.GO_TO)
    def test_procedure_names_fold_case(self):
        labels = procedure_labels(
            [CobolSection(name="Main", paragraphs=[CobolParagraph(name="Pass")])]
        )

        assert [labels.is_section(n) for n in ("main", "MAIN", "pass")] == [
            True,
            True,
            False,
        ]
        assert [labels.procedure(n) for n in ("main", "Pass", "PASS")] == [
            CodeLabel("section_MAIN"),
            CodeLabel("para_PASS"),
            CodeLabel("para_PASS"),
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
            labels.paragraph("pass"),
            labels.paragraph_exit("pAss"),
            labels.paragraph_end("Pass"),
            labels.sentence_exit("pass", 2),
        ) == (
            CodeLabel("para_PASS"),
            CodeLabel("para_PASS_exit"),
            ContinuationName("para_PASS_end"),
            CodeLabel("para_PASS_sentence_2_exit"),
        )
