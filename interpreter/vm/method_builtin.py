"""A method builtin: called with the receiver, its resolved arguments and the VM."""

from __future__ import annotations

from typing import Protocol

from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult


class MethodBuiltin(Protocol):
    def __call__(
        self, obj: TypedValue, args: list[TypedValue], vm: VMState, /
    ) -> BuiltinResult: ...
