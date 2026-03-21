"""Integration tests: C# pattern matching through VM execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_csharp(source: str, max_steps: int = 1000) -> dict:
    vm = run(source, language=Language.CSHARP, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestIsinstancePrimitive:
    def test_isinstance_int(self):
        from interpreter.builtins import _builtin_isinstance
        from interpreter.typed_value import typed
        from interpreter.type_expr import scalar
        from interpreter.vm import VMState

        vm = VMState()
        args = [typed(42, scalar("Int")), typed("int", scalar("String"))]
        result = _builtin_isinstance(args, vm)
        assert result.value.value is True

    def test_isinstance_string(self):
        from interpreter.builtins import _builtin_isinstance
        from interpreter.typed_value import typed
        from interpreter.type_expr import scalar
        from interpreter.vm import VMState

        vm = VMState()
        args = [typed("hello", scalar("String")), typed("string", scalar("String"))]
        result = _builtin_isinstance(args, vm)
        assert result.value.value is True

    def test_isinstance_mismatch(self):
        from interpreter.builtins import _builtin_isinstance
        from interpreter.typed_value import typed
        from interpreter.type_expr import scalar
        from interpreter.vm import VMState

        vm = VMState()
        args = [typed(42, scalar("Int")), typed("string", scalar("String"))]
        result = _builtin_isinstance(args, vm)
        assert result.value.value is False
