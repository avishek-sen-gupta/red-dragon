# pyright: standard
"""Shared utilities for language-specific pattern parsers.

Extracted from duplicated logic across Rust, Scala, Kotlin, and Ruby
pattern parsers. Each language re-implemented these; now they import
from here.
"""

from __future__ import annotations

from interpreter.frontends.common.patterns import ClassPattern, Pattern
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.class_name import ClassName


def parse_number(text: str, strip_suffixes: str = "") -> int | float:
    """Parse numeric literal text to int or float.

    Strips ``_`` separators (Rust/Scala/Kotlin convention) and optional
    trailing suffix characters (e.g. ``lLuU`` for Kotlin, ``fFdD`` for
    Scala/Kotlin floats).
    """
    cleaned = text.replace("_", "")
    if strip_suffixes:
        cleaned = cleaned.rstrip(strip_suffixes)
    if "." in cleaned:
        return float(cleaned)
    if cleaned.startswith(("0x", "0X")):
        return int(cleaned, 16)
    return int(cleaned, 0)


def resolve_positional_via_match_args(
    ctx: TreeSitterEmitContext, class_name: str, positional: tuple[Pattern, ...]
) -> ClassPattern:
    """Convert positional args to keyword args via match_args if available.

    If the class has match_args in the symbol table, positional patterns
    are converted to keyword patterns using LOAD_FIELD instead of LOAD_INDEX.
    """
    class_info = ctx.symbol_table.classes.get(ClassName(class_name))
    match_args = list(class_info.match_args) if class_info else []
    if positional and match_args:
        keyword = tuple(
            (match_args[i], pat)
            for i, pat in enumerate(positional)
            if i < len(match_args)
        )
        return ClassPattern(class_name, positional=(), keyword=keyword)
    return ClassPattern(class_name, positional=positional, keyword=())
