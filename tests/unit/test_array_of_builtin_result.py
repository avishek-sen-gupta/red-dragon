"""Unit tests for _builtin_array_of returning BuiltinResult with heap side effects."""

from interpreter.builtins import _builtin_array_of
from interpreter.vm import VMState
from interpreter.vm_types import BuiltinResult, Pointer
from interpreter.typed_value import TypedValue, typed_from_runtime


class TestArrayOfBuiltinResult:
    def test_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_array_of(
            [typed_from_runtime(10), typed_from_runtime(20), typed_from_runtime(30)], vm
        )
        assert isinstance(result, BuiltinResult)

    def test_value_is_heap_address(self):
        vm = VMState()
        result = _builtin_array_of([typed_from_runtime(10)], vm)
        assert isinstance(result.value, TypedValue)
        assert isinstance(result.value.value, Pointer)
        assert result.value.value.base.startswith("arr_")

    def test_new_objects_contains_array(self):
        vm = VMState()
        result = _builtin_array_of([typed_from_runtime(10)], vm)
        assert len(result.new_objects) == 1
        assert result.new_objects[0].addr == result.value.value.base
        assert result.new_objects[0].type_hint == "array"

    def test_heap_writes_contain_elements_and_length(self):
        vm = VMState()
        result = _builtin_array_of([typed_from_runtime(10), typed_from_runtime(20)], vm)
        fields = {hw.field: hw.value for hw in result.heap_writes}
        assert "0" in fields
        assert "1" in fields
        assert "length" in fields
        assert isinstance(fields["0"], TypedValue)
        assert fields["0"].value == 10
        assert fields["length"].value == 2

    def test_does_not_mutate_heap(self):
        vm = VMState()
        result = _builtin_array_of([typed_from_runtime(10)], vm)
        assert result.value.value.base not in vm.heap

    def test_empty_array(self):
        vm = VMState()
        result = _builtin_array_of([], vm)
        assert len(result.new_objects) == 1
        length_writes = [hw for hw in result.heap_writes if hw.field == "length"]
        assert len(length_writes) == 1
        assert length_writes[0].value.value == 0

    def test_increments_symbolic_counter(self):
        vm = VMState()
        _builtin_array_of([typed_from_runtime(1)], vm)
        assert vm.symbolic_counter == 1
        _builtin_array_of([typed_from_runtime(2)], vm)
        assert vm.symbolic_counter == 2
