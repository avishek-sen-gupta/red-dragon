# pyright: standard
"""Structured function references — replaces stringly-typed FUNC_REF_PATTERN."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.closure_id import ClosureId, NO_CLOSURE_ID
from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel


@dataclass(frozen=True)
class FuncRef:
    """Compile-time function reference. Lives in the symbol table."""

    name: FuncName  # FuncName("add"), FuncName("new"), FuncName("__lambda")
    label: CodeLabel  # CodeLabel("func_add_0")


@dataclass(frozen=True)
class BoundFuncRef:
    """Runtime function reference with closure binding. Stored in registers."""

    func_ref: FuncRef
    closure_id: ClosureId = NO_CLOSURE_ID
