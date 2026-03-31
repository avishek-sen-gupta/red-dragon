"""EntryPoint type -- explicit specification of how to enter a program for execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from interpreter.refs.func_ref import FuncRef


@dataclass(frozen=True)
class EntryPoint:
    """Specifies how to enter a program for execution.

    Two modes:
    - top_level(): execute module code top-to-bottom
    - function(predicate): run preamble, then dispatch into the matched function
    """

    _predicate: Callable[[FuncRef], bool]
    _is_top_level: bool

    @staticmethod
    def function(predicate: Callable[[FuncRef], bool]) -> EntryPoint:
        """Dispatch into the single function matching the predicate."""
        return EntryPoint(_predicate=predicate, _is_top_level=False)

    @staticmethod
    def top_level() -> EntryPoint:
        """Execute module code top-to-bottom (preamble + top-level statements)."""
        return EntryPoint(_predicate=lambda _: False, _is_top_level=True)

    @property
    def is_top_level(self) -> bool:
        return self._is_top_level

    @property
    def is_function(self) -> bool:
        return not self._is_top_level

    def resolve(self, candidates: list[FuncRef]) -> FuncRef:
        """Apply predicate to candidates and return the single match.

        Raises ValueError if zero or multiple matches.
        """
        matches = [f for f in candidates if self._predicate(f)]
        if not matches:
            names = [str(f.name) for f in candidates]
            raise ValueError(
                f"No function matched the entry_point predicate. Available: {names}"
            )
        if len(matches) > 1:
            names = [str(f.name) for f in matches]
            raise ValueError(
                f"Multiple functions matched the entry_point predicate: {names}. "
                f"Narrow the predicate to match exactly one."
            )
        return matches[0]
