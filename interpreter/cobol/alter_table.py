"""The program's alterable GO TOs and the targets its ALTER statements name for each."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from interpreter.cobol.alterable_goto import AlterableGoto
from interpreter.ir import CodeLabel


@dataclass(frozen=True)
class AlterTable:
    """Each ALTER target of a paragraph has an ordinal, 1 upwards in the order the
    ALTER statements are lowered; 0 is the GO TO as written."""

    gotos: tuple[AlterableGoto, ...] = ()
    targets: Mapping[CodeLabel, tuple[CodeLabel, ...]] = field(
        default_factory=dict[CodeLabel, tuple[CodeLabel, ...]]
    )

    def with_goto(self, goto: AlterableGoto) -> AlterTable:
        return AlterTable(gotos=(*self.gotos, goto), targets=self.targets)

    def with_target(self, paragraph: CodeLabel, target: CodeLabel) -> AlterTable:
        known = self.targets_of(paragraph)
        if target in known:
            return self
        return AlterTable(
            gotos=self.gotos,
            targets={**self.targets, paragraph: (*known, target)},
        )

    def targets_of(self, paragraph: CodeLabel) -> tuple[CodeLabel, ...]:
        return self.targets.get(paragraph, ())

    def ordinal(self, paragraph: CodeLabel, target: CodeLabel) -> int:
        return self.targets_of(paragraph).index(target) + 1
