"""Unit tests for _builtin_len with heap arrays that have a 'length' field.

Arrays created by arrayOf/intArrayOf store elements as {'0': v0, '1': v1, ..., 'length': N}.
_builtin_len must return the 'length' field value (N), not len(fields) which
includes the 'length' key itself and produces an off-by-one.
"""

from __future__ import annotations

from interpreter.builtins import _builtin_len, _builtin_array_of
from interpreter.constants import TypeName
from interpreter.type_expr import scalar
from interpreter.typed_value import typed
from interpreter.vm import VMState, apply_update
from interpreter.vm_types import BuiltinResult, HeapObject, StackFrame, StateUpdate


def _apply_builtin_result(vm: VMState, result: BuiltinResult) -> None:
    """Apply BuiltinResult side effects to VM for unit testing."""
    apply_update(
        vm,
        StateUpdate(
            new_objects=result.new_objects,
            heap_writes=result.heap_writes,
        ),
    )


class TestBuiltinLenRespectsLengthField:
    def test_len_of_arrayOf_three_elements(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        result = _builtin_array_of([10, 5, 3], vm)
        _apply_builtin_result(vm, result)
        length = _builtin_len([result.value], vm)
        assert length.value == 3

    def test_len_of_arrayOf_empty(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        result = _builtin_array_of([], vm)
        _apply_builtin_result(vm, result)
        length = _builtin_len([result.value], vm)
        assert length.value == 0

    def test_len_of_arrayOf_single_element(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        result = _builtin_array_of([42], vm)
        _apply_builtin_result(vm, result)
        length = _builtin_len([result.value], vm)
        assert length.value == 1

    def test_len_of_heap_object_without_length_field(self):
        """Plain objects (no 'length' field) should use len(fields)."""
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={
                "a": typed(1, scalar(TypeName.INT)),
                "b": typed(2, scalar(TypeName.INT)),
            },
        )
        result = _builtin_len(["obj_0"], vm)
        assert result.value == 2

    def test_len_of_heap_object_with_length_field(self):
        """JS-style arrays with explicit 'length' field should return that value."""
        vm = VMState()
        vm.heap["arr_0"] = HeapObject(
            type_hint="array",
            fields={
                "0": typed(10, scalar(TypeName.INT)),
                "1": typed(20, scalar(TypeName.INT)),
                "2": typed(30, scalar(TypeName.INT)),
                "length": typed(3, scalar(TypeName.INT)),
            },
        )
        result = _builtin_len(["arr_0"], vm)
        assert result.value == 3
