"""Structured function references — replaces stringly-typed FUNC_REF_PATTERN."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FuncRef:
    """Compile-time function reference. Lives in the symbol table."""

    name: str  # "add", "new", "__lambda"
    label: str  # "func_add_0"


@dataclass(frozen=True)
class BoundFuncRef:
    """Runtime function reference with closure binding. Stored in registers."""

    func_ref: FuncRef
    closure_id: str  # "closure_42" or "" for non-closures
