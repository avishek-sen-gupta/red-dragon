"""Pattern ADT for structural pattern matching.

Language frontends parse tree-sitter ASTs into these types.
The compile_match function (below) emits IR from them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pattern:
    """Base for all pattern types."""


@dataclass(frozen=True)
class LiteralPattern(Pattern):
    """Match against a literal value (int, str, bool, None)."""

    value: int | float | str | bool | None


@dataclass(frozen=True)
class WildcardPattern(Pattern):
    """Matches anything, binds nothing. Python's ``_``."""


@dataclass(frozen=True)
class CapturePattern(Pattern):
    """Matches anything, binds the subject to a variable name."""

    name: str


@dataclass(frozen=True)
class SequencePattern(Pattern):
    """Matches a tuple or list — checks length, then matches each element by index."""

    elements: tuple[Pattern, ...]


@dataclass(frozen=True)
class MappingPattern(Pattern):
    """Matches a dict — checks each key exists, then matches the value pattern."""

    entries: tuple[tuple[int | float | str | bool | None, Pattern], ...]


@dataclass(frozen=True)
class ClassPattern(Pattern):
    """Matches by type, then matches positional and keyword sub-patterns."""

    class_name: str
    positional: tuple[Pattern, ...]
    keyword: tuple[tuple[str, Pattern], ...]


@dataclass(frozen=True)
class OrPattern(Pattern):
    """Matches if any alternative matches (short-circuit). No bindings."""

    alternatives: tuple[Pattern, ...]


@dataclass(frozen=True)
class AsPattern(Pattern):
    """Matches inner pattern, then binds subject to name."""

    pattern: Pattern
    name: str


@dataclass(frozen=True)
class NoGuard:
    """Sentinel: this case has no guard clause."""


@dataclass(frozen=True)
class NoBody:
    """Sentinel: this case has no body (used in tests)."""


@dataclass(frozen=True)
class MatchCase:
    """A single case in a match statement."""

    pattern: Pattern
    guard_node: object  # tree-sitter node for guard expression, or NoGuard()
    body_node: object  # tree-sitter node for case body, or NoBody()
