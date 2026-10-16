"""ProcedureLabels — the IR labels that name a program's sections and paragraphs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from cobol_asg.asg_types import CobolParagraph, CobolSection
from interpreter.continuation_name import ContinuationName
from interpreter.ir import CodeLabel


@dataclass(frozen=True)
class ProcedureLabels:
    """Procedure labels: names fold case; a paragraph-name declared twice carries its section."""

    sections: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict[str, tuple[str, ...]]
    )
    duplicated: frozenset[str] = frozenset()

    def is_section(self, name: str) -> bool:
        return name.upper() in self.sections

    def owner(self, paragraph: str, qualifier: str, current: str) -> str:
        name = paragraph.upper()
        if qualifier:
            return qualifier.upper()
        if name in self.sections.get(current.upper(), ()):
            return current.upper()
        return next(
            (section for section, names in self.sections.items() if name in names), ""
        )

    def procedure(self, name: str, qualifier: str, current: str) -> CodeLabel:
        if not qualifier and self.is_section(name):
            return self.section(name)
        return self.paragraph(name, self.owner(name, qualifier, current))

    def section(self, name: str) -> CodeLabel:
        return CodeLabel(f"section_{name.upper()}")

    def section_exit(self, name: str) -> CodeLabel:
        return CodeLabel(f"{self.section(name)}_exit")

    def section_end(self, name: str) -> ContinuationName:
        return ContinuationName(f"{self.section(name)}_end")

    def paragraph(self, name: str, section: str) -> CodeLabel:
        bare = name.upper()
        if bare in self.duplicated:
            return CodeLabel(f"para_{section.upper()}_{bare}")
        return CodeLabel(f"para_{bare}")

    def paragraph_exit(self, name: str, section: str) -> CodeLabel:
        return CodeLabel(f"{self.paragraph(name, section)}_exit")

    def paragraph_end(self, name: str, section: str) -> ContinuationName:
        return ContinuationName(f"{self.paragraph(name, section)}_end")

    def sentence_exit(self, name: str, section: str, position: int) -> CodeLabel:
        return CodeLabel(f"{self.paragraph(name, section)}_sentence_{position}_exit")


def _names(paragraphs: Sequence[CobolParagraph]) -> tuple[str, ...]:
    return tuple(p.name.upper() for p in paragraphs)


def procedure_labels(
    sections: Sequence[CobolSection], paragraphs: Sequence[CobolParagraph]
) -> ProcedureLabels:
    by_section = {s.name.upper(): _names(s.paragraphs) for s in sections}
    declared = Counter(
        [*_names(paragraphs), *(n for names in by_section.values() for n in names)]
    )
    return ProcedureLabels(
        sections=by_section,
        duplicated=frozenset(name for name, count in declared.items() if count > 1),
    )
