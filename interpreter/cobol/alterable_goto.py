"""A paragraph whose only statement is a GO TO, which an ALTER may redirect."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.ir import CodeLabel


@dataclass(frozen=True)
class AlterableGoto:
    """The paragraph's label, and the point at the GO TO its dispatch returns to
    while the GO TO is unaltered."""

    paragraph: CodeLabel
    unaltered: CodeLabel

    @property
    def dispatch(self) -> CodeLabel:
        return CodeLabel(f"{self.paragraph}_altered_goto")
