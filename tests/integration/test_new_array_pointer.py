"""Integration tests for NEW_ARRAY producing Pointer with correct type."""

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.vm.vm_types import Pointer
from interpreter.types.typed_value import unwrap_locals


class TestNewArrayProducesPointer:
    def test_python_list_is_pointer(self):
        vm = run("x = [1, 2, 3]\n", language=Language.PYTHON, max_steps=100)
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_[VarName("x")], Pointer)
        assert locals_[VarName("x")].base.startswith("arr_")

    def test_javascript_array_is_pointer(self):
        vm = run("let x = [1, 2, 3];", language=Language.JAVASCRIPT, max_steps=100)
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert isinstance(locals_[VarName("x")], Pointer)
        assert locals_[VarName("x")].base.startswith("arr_")

    def test_array_elements_accessible_via_pointer(self):
        vm = run(
            "x = [10, 20, 30]\ny = x[1]\n", language=Language.PYTHON, max_steps=100
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_[VarName("y")] == 20
