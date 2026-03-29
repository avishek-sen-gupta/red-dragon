"""Unit tests for SpreadArguments expansion in _resolve_call_args."""

from __future__ import annotations

from interpreter.vm.executor import _resolve_call_args
from interpreter.ir import SpreadArguments
from interpreter.vm.vm import VMState
from interpreter.field_name import FieldName, FieldKind
from interpreter.address import Address
from interpreter.vm.vm_types import HeapObject, Pointer, StackFrame
from interpreter.types.typed_value import typed, typed_from_runtime
from interpreter.types.type_expr import scalar
from interpreter.constants import TypeName
from interpreter.register import Register


class TestResolveCallArgs:
    def _make_vm_with_array(self, elements: list) -> tuple[VMState, Pointer]:
        """Create a VM with a heap array and a frame holding a register pointing to it."""
        vm = VMState()
        fields = {
            FieldName(str(i), FieldKind.INDEX): typed(e, scalar(TypeName.INT))
            for i, e in enumerate(elements)
        }
        fields[FieldName("length", FieldKind.SPECIAL)] = typed(
            len(elements), scalar(TypeName.INT)
        )
        vm.heap["arr_0"] = HeapObject(type_hint="Array", fields=fields)
        ptr = Pointer(base=Address("arr_0"), offset=0)
        vm.call_stack.append(
            StackFrame(
                function_name="test",
                registers={Register("%arr"): typed_from_runtime(ptr)},
            )
        )
        return vm, ptr

    def test_plain_args_resolve_normally(self):
        """Non-spread operands resolve via _resolve_reg as usual."""
        vm = VMState()
        vm.call_stack.append(
            StackFrame(
                function_name="test",
                registers={
                    Register("%a"): typed_from_runtime(1),
                    Register("%b"): typed_from_runtime(2),
                },
            )
        )
        args = _resolve_call_args(vm, ["%a", "%b"])
        assert [a.value for a in args] == [1, 2]

    def test_spread_expands_heap_array(self):
        """SpreadArguments should expand a heap array into individual args."""
        vm, _ = self._make_vm_with_array([10, 5, 3])
        args = _resolve_call_args(vm, [SpreadArguments(register="%arr")])
        assert [a.value for a in args] == [10, 5, 3]

    def test_spread_empty_array(self):
        """SpreadArguments on an empty array should produce zero args."""
        vm, _ = self._make_vm_with_array([])
        args = _resolve_call_args(vm, [SpreadArguments(register="%arr")])
        assert args == []

    def test_spread_mixed_with_plain_args(self):
        """SpreadArguments can be mixed with plain register args."""
        vm, _ = self._make_vm_with_array([2, 3])
        vm.current_frame.registers[Register("%x")] = typed_from_runtime(1)
        vm.current_frame.registers[Register("%y")] = typed_from_runtime(4)
        args = _resolve_call_args(vm, ["%x", SpreadArguments(register="%arr"), "%y"])
        assert [a.value for a in args] == [1, 2, 3, 4]

    def test_spread_preserves_element_order(self):
        """Elements should come out in index order 0, 1, 2, ..."""
        vm, _ = self._make_vm_with_array([100, 200, 300, 400])
        args = _resolve_call_args(vm, [SpreadArguments(register="%arr")])
        assert [a.value for a in args] == [100, 200, 300, 400]

    def test_spread_str_representation(self):
        """SpreadArguments should have a readable str for IR display."""
        sa = SpreadArguments(register="%arr")
        assert str(sa) == "*%arr"
