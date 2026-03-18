"""Integration tests for builtins returning Pointer values."""

from interpreter.constants import Language
from interpreter.run import run
from interpreter.vm_types import Pointer
from interpreter.typed_value import unwrap_locals


class TestBuiltinArrayPointer:
    def test_kotlin_array_of_produces_pointer(self):
        vm = run("val arr = arrayOf(1, 2, 3)", language=Language.KOTLIN, max_steps=100)
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_["arr"], Pointer)
        assert locals_["arr"].base.startswith("arr_")

    def test_js_spread_array_produces_pointer(self):
        vm = run(
            "let a = [1, 2, 3]; let b = [...a, 4];",
            language=Language.JAVASCRIPT,
            max_steps=200,
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_["b"], Pointer)
