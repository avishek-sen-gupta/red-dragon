"""Structured class references — replaces stringly-typed CLASS_REF_PATTERN."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.ir import CodeLabel, NO_LABEL


@dataclass(frozen=True)
class ClassRef:
    """Compile-time class reference. Lives in the symbol table.

    Unlike FuncRef/BoundFuncRef, class references have no runtime binding
    equivalent — they are purely compile-time records.
    """

    name: str  # "Dog", "Counter", "__anon_class_0"
    label: CodeLabel  # CodeLabel("class_Dog_0")
    parents: tuple[str, ...]  # ("Animal",) or () for no parents


NO_CLASS_REF = ClassRef(name="", label=NO_LABEL, parents=())
"""Null object sentinel for failed symbol table lookups.

Consumer sites use ``table.get(label, NO_CLASS_REF)`` and check
``ref.name`` truthiness — no ``None`` checks anywhere.
"""
