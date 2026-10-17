"""One INSPECT TALLYING or REPLACING phrase, with its operands' values."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.inspect_mode import InspectMode


@dataclass(frozen=True)
class InspectPhrase:
    """A phrase's mode, pattern, BY value, AFTER / BEFORE operands and counter.

    An empty ``after`` or ``before`` means that phrase was not written: an
    operand's value is never empty. ``counter`` numbers the TALLYING identifier
    the phrase counts into.
    """

    mode: InspectMode
    pattern: str = ""
    replacement: str = ""
    after: str = ""
    before: str = ""
    counter: int = 0

    def length(self) -> int:
        return 1 if self.mode == InspectMode.CHARACTERS else len(self.pattern)

    def region(self, source: str) -> tuple[int, int]:
        """The part of ``source`` this phrase inspects, as (start, end)."""
        start = self._region_start(source)
        found = source.find(self.before, start) if self.before else -1
        return start, found if found >= 0 else len(source)

    def _region_start(self, source: str) -> int:
        if not self.after:
            return 0
        found = source.find(self.after)
        return found + len(self.after) if found >= 0 else len(source)

    def fitted_replacement(self) -> str:
        """The BY value sized to the matched characters: a one-character BY
        (a figurative constant) fills them all."""
        size = self.length()
        return (
            (self.replacement * size)[:size]
            if len(self.replacement) == 1
            else self.replacement[:size]
        )
