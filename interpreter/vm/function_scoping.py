"""Function scoping strategies — controls where FuncRef/BoundFuncRef values are registered.

LocalFunctionScopingStrategy (default):
    Writes only to the current frame. Correct for all lexically-scoped languages.

GlobalLeakFunctionScopingStrategy:
    Writes to the current frame AND the global frame (call_stack[0]) when nested.
    Used for Ruby, PHP, and Lua where inner function definitions leak to global scope.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from interpreter.types.typed_value import TypedValue
from interpreter.var_name import VarName
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import StackFrame

_GLOBAL_FRAME_DEPTH = 1


class FunctionScopingStrategy(ABC):
    """Strategy for registering function-ref values when executing STORE_VAR/DECL_VAR."""

    @abstractmethod
    def register_func(
        self,
        name: VarName,
        value: TypedValue,
        vm: VMState,
        current_frame: StackFrame,
    ) -> None:
        """Write *value* to the appropriate frame(s) in *vm*."""


class LocalFunctionScopingStrategy(FunctionScopingStrategy):
    """Default: write to the current frame only."""

    def register_func(
        self,
        name: VarName,
        value: TypedValue,
        vm: VMState,
        current_frame: StackFrame,
    ) -> None:
        current_frame.local_vars[name] = value


class GlobalLeakFunctionScopingStrategy(FunctionScopingStrategy):
    """Ruby/PHP/Lua: write to current frame and global frame when nested."""

    def register_func(
        self,
        name: VarName,
        value: TypedValue,
        vm: VMState,
        current_frame: StackFrame,
    ) -> None:
        current_frame.local_vars[name] = value
        if len(vm.call_stack) > _GLOBAL_FRAME_DEPTH:
            vm.call_stack[0].local_vars[name] = value
