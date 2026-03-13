"""Unit tests for _builtin_keys — extracting object keys as a heap array.

The JS for-in lowerer emits CALL_FUNCTION("keys", obj_reg). This builtin
must return a concrete heap array of the object's field names so that
len() and index-based iteration work correctly.
"""

from __future__ import annotations

from interpreter.builtins import Builtins, _builtin_len
from interpreter.vm import VMState
from interpreter.vm_types import HeapObject
from interpreter.typed_value import typed_from_runtime


class TestBuiltinKeysRegistered:
    def test_keys_in_builtins_table(self):
        assert "keys" in Builtins.TABLE, "keys not registered in Builtins.TABLE"


class TestBuiltinKeysProducesConcreteArray:
    def test_keys_of_two_field_object(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={k: typed_from_runtime(v) for k, v in {"a": 10, "b": 5}.items()},
        )
        result = Builtins.TABLE["keys"](["obj_0"], vm)
        # Should return a heap address
        assert isinstance(result, str)
        assert result in vm.heap
        keys_obj = vm.heap[result]
        # Should be an array with 2 elements
        assert keys_obj.fields["length"].value == 2
        key_values = {keys_obj.fields["0"].value, keys_obj.fields["1"].value}
        assert key_values == {"a", "b"}

    def test_keys_of_empty_object(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(type_hint="object", fields={})
        result = Builtins.TABLE["keys"](["obj_0"], vm)
        assert result in vm.heap
        assert vm.heap[result].fields["length"].value == 0

    def test_keys_excludes_length_field(self):
        """Arrays have a 'length' field — keys() should exclude it."""
        vm = VMState()
        vm.heap["arr_0"] = HeapObject(
            type_hint="array",
            fields={
                k: typed_from_runtime(v)
                for k, v in {"0": 10, "1": 20, "length": 2}.items()
            },
        )
        result = Builtins.TABLE["keys"](["arr_0"], vm)
        keys_obj = vm.heap[result]
        assert keys_obj.fields["length"].value == 2
        key_values = {keys_obj.fields["0"].value, keys_obj.fields["1"].value}
        assert key_values == {"0", "1"}

    def test_len_of_keys_result(self):
        """len() on the keys array should return correct count."""
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={
                k: typed_from_runtime(v) for k, v in {"x": 1, "y": 2, "z": 3}.items()
            },
        )
        keys_addr = Builtins.TABLE["keys"](["obj_0"], vm)
        length = _builtin_len([keys_addr], vm)
        assert length == 3
