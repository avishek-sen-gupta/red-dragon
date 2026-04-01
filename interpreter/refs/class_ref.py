# pyright: standard
"""Structured class references — replaces stringly-typed CLASS_REF_PATTERN."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.class_name import ClassName, NO_CLASS_NAME
from interpreter.ir import CodeLabel, NO_LABEL


@dataclass(frozen=True)
class ClassRef:
    """Compile-time class reference. Lives in the symbol table.

    Unlike FuncRef/BoundFuncRef, class references have no runtime binding
    equivalent — they are purely compile-time records.
    """

    name: ClassName  # ClassName("Dog"), ClassName("Counter")
    label: CodeLabel  # CodeLabel("class_Dog_0")
    parents: tuple[ClassName, ...]  # (ClassName("Animal"),) or () for no parents


NO_CLASS_REF = ClassRef(name=NO_CLASS_NAME, label=NO_LABEL, parents=())
"""Null object sentinel for failed symbol table lookups.

Consumer sites use ``table.get(label, NO_CLASS_REF)`` and check
``ref.name`` truthiness — no ``None`` checks anywhere.
"""
