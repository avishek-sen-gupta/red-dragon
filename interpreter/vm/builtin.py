"""A builtin function: called with its resolved arguments and the VM, returns a BuiltinResult."""

from __future__ import annotations

from typing import Protocol

from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult


class Builtin(Protocol):
    def __call__(self, args: list[TypedValue], vm: VMState, /) -> BuiltinResult: ...
