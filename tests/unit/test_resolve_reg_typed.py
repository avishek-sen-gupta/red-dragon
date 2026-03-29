"""Tests for _resolve_reg returning TypedValue."""

from interpreter.register import Register
from interpreter.vm.vm import _resolve_reg
from interpreter.address import Address
from interpreter.vm.vm_types import Pointer, StackFrame, VMState
from interpreter.func_name import FuncName
from interpreter.types.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.types.type_expr import pointer, scalar, UNKNOWN


def _make_vm(**registers: object) -> VMState:
    """Create a minimal VMState with the given registers."""
    frame = StackFrame(function_name=FuncName("test"))
    frame.registers.update({Register(k): v for k, v in registers.items()})
    return VMState(call_stack=[frame])


class TestResolveRegReturnsTypedValue:
    def test_returns_typed_value_for_typed_register(self):
        """A register holding a TypedValue should be returned as-is."""
        tv = typed(Pointer(base=Address("obj_0"), offset=0), pointer(scalar("Dog")))
        vm = _make_vm(**{"%0": tv})
        result = _resolve_reg(vm, "%0")
        assert isinstance(result, TypedValue)
        assert result is tv

    def test_preserves_parameterized_type(self):
        """pointer(scalar('Dog')) must survive the resolve."""
        expected_type = pointer(scalar("Dog"))
        tv = typed(Pointer(base=Address("obj_0"), offset=0), expected_type)
        vm = _make_vm(**{"%0": tv})
        result = _resolve_reg(vm, "%0")
        assert result.type == expected_type

    def test_wraps_bare_register_value_via_typed_from_runtime(self):
        """A register holding a bare int should be wrapped as TypedValue."""
        vm = _make_vm(**{"%0": 42})
        result = _resolve_reg(vm, "%0")
        assert isinstance(result, TypedValue)
        assert result.value == 42

    def test_wraps_non_register_operand(self):
        """A non-register operand (e.g., literal string) is wrapped."""
        vm = _make_vm()
        result = _resolve_reg(vm, "hello")
        assert isinstance(result, TypedValue)
        assert result.value == "hello"

    def test_wraps_missing_register(self):
        """An unset register returns the register name wrapped."""
        vm = _make_vm()
        result = _resolve_reg(vm, "%99")
        assert isinstance(result, TypedValue)
        assert result.value == "%99"

    def test_bare_pointer_in_register_gets_unknown_type(self):
        """A bare Pointer (not wrapped in TypedValue) gets UNKNOWN type."""
        vm = _make_vm(**{"%0": Pointer(base=Address("obj_0"), offset=0)})
        result = _resolve_reg(vm, "%0")
        assert isinstance(result, TypedValue)
        assert isinstance(result.value, Pointer)
        assert result.type == UNKNOWN
