"""Field fallback strategies for implicit this.field resolution.

When LOAD_VAR or STORE_VAR cannot find a variable in the scope chain,
a FieldFallbackStrategy decides whether to fall back to ``this.field``
access on the current object.

Languages with implicit this (Java, C#, Kotlin, Scala, C++) should use
ImplicitThisFieldFallback.  Languages requiring explicit self/this
(Python, Ruby, PHP) or non-OOP languages (C, Rust, Go) should use
NoFieldFallback (the default).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from interpreter import constants
from interpreter.field_name import FieldName
from interpreter.types.typed_value import TypedValue
from interpreter.var_name import VarName
from interpreter.vm.vm import VMState, _heap_addr as shared_heap_addr


class FieldFallbackStrategy(ABC):
    """Strategy for resolving bare names as this.field when not in scope."""

    @abstractmethod
    def resolve_load(self, vm: VMState, name: str) -> TypedValue | None:
        """Return the field value if resolvable, else None."""

    @abstractmethod
    def resolve_store(self, vm: VMState, name: str) -> str | None:
        """Return the heap address to write to if resolvable, else None."""


class NoFieldFallback(FieldFallbackStrategy):
    """Default: no implicit this resolution."""

    def resolve_load(self, vm: VMState, name: str) -> TypedValue | None:
        return None

    def resolve_store(self, vm: VMState, name: str) -> str | None:
        return None


class ImplicitThisFieldFallback(FieldFallbackStrategy):
    """Resolve bare names as this.field when this is in scope."""

    def _find_this_addr(self, vm: VMState) -> str | None:
        """Walk call stack looking for this pointing to a heap object."""
        for f in reversed(vm.call_stack):
            this_tv = f.local_vars.get(VarName(constants.PARAM_THIS))
            if this_tv is None:
                continue
            addr = self._heap_addr(this_tv.value)
            if addr and addr in vm.heap:
                return addr
        return None

    def _heap_addr(self, value: object) -> str | None:
        addr = shared_heap_addr(value)
        if addr and addr.startswith(constants.OBJ_ADDR_PREFIX):
            return addr
        return None

    def resolve_load(self, vm: VMState, name: str) -> TypedValue | None:
        addr = self._find_this_addr(vm)
        if addr is None:
            return None
        return vm.heap[addr].fields.get(FieldName(str(name)))

    def resolve_store(self, vm: VMState, name: str) -> str | None:
        addr = self._find_this_addr(vm)
        if addr is None:
            return None
        if FieldName(str(name)) in vm.heap[addr].fields:
            return addr
        return None
