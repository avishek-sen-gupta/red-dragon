"""Structured class references — replaces stringly-typed CLASS_REF_PATTERN."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassRef:
    """Compile-time class reference. Lives in the symbol table.

    Unlike FuncRef/BoundFuncRef, class references have no runtime binding
    equivalent — they are purely compile-time records.
    """

    name: str  # "Dog", "Counter", "__anon_class_0"
    label: str  # "class_Dog_0"
    parents: tuple[str, ...]  # ("Animal",) or () for no parents


NO_CLASS_REF = ClassRef(name="", label="", parents=())
"""Null object sentinel for failed symbol table lookups.

Consumer sites use ``table.get(label, NO_CLASS_REF)`` and check
``ref.name`` truthiness — no ``None`` checks anywhere.
"""
