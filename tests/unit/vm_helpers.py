"""Shared helpers for VM-level unit tests.

Centralizes the boilerplate VMState construction used across many unit test
modules so it is defined exactly once.
"""

from __future__ import annotations

from interpreter.func_name import FuncName
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import StackFrame


def make_vm(func_name: str = "<main>") -> VMState:
    """Create a minimal VMState with a single stack frame."""
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name=FuncName(func_name)))
    return vm
