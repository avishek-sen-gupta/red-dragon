"""Unit tests for _builtin_keys — extracting object keys as a heap array.

The JS for-in lowerer emits CALL_FUNCTION("keys", obj_reg). This builtin
must return a concrete heap array of the object's field names so that
len() and index-based iteration work correctly.
"""

from __future__ import annotations

from interpreter.builtins import Builtins, _builtin_len
from interpreter.type_expr import scalar
from interpreter.vm import VMState, apply_update
from interpreter.vm_types import BuiltinResult, HeapObject, StackFrame, StateUpdate
from interpreter.typed_value import TypedValue, typed_from_runtime
from interpreter.vm_types import Pointer


def _result_addr(result: BuiltinResult) -> str:
    """Extract the heap address from a BuiltinResult value."""
    val = result.value
    if isinstance(val, TypedValue):
        val = val.value
    if isinstance(val, Pointer):
        return val.base
    return val


def _apply_builtin_result(vm: VMState, result: BuiltinResult) -> None:
    """Apply BuiltinResult side effects to VM for unit testing."""
    apply_update(
        vm,
        StateUpdate(
            new_objects=result.new_objects,
            heap_writes=result.heap_writes,
        ),
    )


class TestBuiltinKeysRegistered:
    def test_keys_in_builtins_table(self):
        assert "keys" in Builtins.TABLE, "keys not registered in Builtins.TABLE"


class TestBuiltinKeysProducesConcreteArray:
    def test_keys_of_two_field_object(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={k: typed_from_runtime(v) for k, v in {"a": 10, "b": 5}.items()},
        )
        result = Builtins.TABLE["keys"]([typed_from_runtime("obj_0")], vm)
        _apply_builtin_result(vm, result)
        assert isinstance(result.value, TypedValue)
        assert isinstance(result.value.value, Pointer)
        assert _result_addr(result) in vm.heap
        keys_obj = vm.heap[_result_addr(result)]
        assert keys_obj.fields["length"].value == 2
        key_values = {keys_obj.fields["0"].value, keys_obj.fields["1"].value}
        assert key_values == {"a", "b"}

    def test_keys_of_empty_object(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        vm.heap["obj_0"] = HeapObject(type_hint=scalar("object"), fields={})
        result = Builtins.TABLE["keys"]([typed_from_runtime("obj_0")], vm)
        _apply_builtin_result(vm, result)
        assert _result_addr(result) in vm.heap
        assert vm.heap[_result_addr(result)].fields["length"].value == 0

    def test_keys_excludes_length_field(self):
        """Arrays have a 'length' field — keys() should exclude it."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        vm.heap["arr_0"] = HeapObject(
            type_hint="array",
            fields={
                k: typed_from_runtime(v)
                for k, v in {"0": 10, "1": 20, "length": 2}.items()
            },
        )
        result = Builtins.TABLE["keys"]([typed_from_runtime("arr_0")], vm)
        _apply_builtin_result(vm, result)
        keys_obj = vm.heap[_result_addr(result)]
        assert keys_obj.fields["length"].value == 2
        key_values = {keys_obj.fields["0"].value, keys_obj.fields["1"].value}
        assert key_values == {"0", "1"}

    def test_len_of_keys_result(self):
        """len() on the keys array should return correct count."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={
                k: typed_from_runtime(v) for k, v in {"x": 1, "y": 2, "z": 3}.items()
            },
        )
        keys_result = Builtins.TABLE["keys"]([typed_from_runtime("obj_0")], vm)
        _apply_builtin_result(vm, keys_result)
        length = _builtin_len([keys_result.value], vm)
        assert length.value == 3
