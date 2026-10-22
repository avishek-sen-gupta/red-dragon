# pyright: standard
"""A run of emitted instructions, by index, that one statement's source location covers."""

from dataclasses import dataclass

from interpreter.ir import SourceLocation


@dataclass(frozen=True)
class LocatedSpan:
    """Instructions start up to end, exclusive, take location."""

    start: int
    end: int
    location: SourceLocation

    def indices(self) -> range:
        return range(self.start, self.end)
