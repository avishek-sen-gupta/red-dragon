"""ProcedureLabels — the IR labels that name a program's sections and paragraphs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from cobol_asg.asg_types import CobolSection
from interpreter.continuation_name import ContinuationName
from interpreter.ir import CodeLabel


@dataclass(frozen=True)
class ProcedureLabels:
    """Section and paragraph labels; procedure-names are COBOL words, so case folds."""

    sections: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict[str, tuple[str, ...]]
    )

    def is_section(self, name: str) -> bool:
        return name.upper() in self.sections

    def procedure(self, name: str) -> CodeLabel:
        if self.is_section(name):
            return self.section(name)
        return self.paragraph(name)

    def section(self, name: str) -> CodeLabel:
        return CodeLabel(f"section_{name.upper()}")

    def section_exit(self, name: str) -> CodeLabel:
        return CodeLabel(f"{self.section(name)}_exit")

    def section_end(self, name: str) -> ContinuationName:
        return ContinuationName(f"{self.section(name)}_end")

    def paragraph(self, name: str) -> CodeLabel:
        return CodeLabel(f"para_{name.upper()}")

    def paragraph_exit(self, name: str) -> CodeLabel:
        return CodeLabel(f"{self.paragraph(name)}_exit")

    def paragraph_end(self, name: str) -> ContinuationName:
        return ContinuationName(f"{self.paragraph(name)}_end")

    def sentence_exit(self, name: str, position: int) -> CodeLabel:
        return CodeLabel(f"{self.paragraph(name)}_sentence_{position}_exit")


def procedure_labels(sections: Sequence[CobolSection]) -> ProcedureLabels:
    return ProcedureLabels(
        {
            section.name.upper(): tuple(p.name.upper() for p in section.paragraphs)
            for section in sections
        }
    )
