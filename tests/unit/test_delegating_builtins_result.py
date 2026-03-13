"""Unit tests for partially-delegating builtins returning BuiltinResult."""

from interpreter.builtins import (
    _builtin_keys,
    _builtin_slice,
    _slice_heap_array,
    _method_slice,
)
from interpreter.vm import Operators
from interpreter.vm_types import BuiltinResult, HeapObject, VMState
from interpreter.typed_value import typed, typed_from_runtime
from interpreter.type_expr import scalar
from interpreter.constants import TypeName


class TestBuiltinKeysResult:
    def test_uncomputable_no_args_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_keys([], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE

    def test_uncomputable_not_on_heap_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_keys(["nonexistent"], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE

    def test_happy_path_returns_builtin_result(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={"a": typed_from_runtime(1)},
        )
        result = _builtin_keys(["obj_0"], vm)
        assert isinstance(result, BuiltinResult)
        assert isinstance(result.value, str)
        assert len(result.new_objects) == 1


class TestBuiltinSliceResult:
    def test_uncomputable_bad_args_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_slice([1], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE

    def test_native_list_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_slice([[10, 20, 30], 0, 2], vm)
        assert isinstance(result, BuiltinResult)
        assert isinstance(result.value, str)

    def test_native_string_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_slice(["hello", 1, 3], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == "el"
        assert result.new_objects == []

    def test_heap_array_returns_builtin_result(self):
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
        result = _builtin_slice(["arr_0", 0, 2], vm)
        assert isinstance(result, BuiltinResult)
        assert isinstance(result.value, str)
        assert len(result.new_objects) == 1


class TestSliceHeapArrayResult:
    def test_returns_builtin_result(self):
        heap_obj = HeapObject(
            type_hint="array",
            fields={
                "0": typed(10, scalar(TypeName.INT)),
                "1": typed(20, scalar(TypeName.INT)),
                "length": typed(2, scalar(TypeName.INT)),
            },
        )
        vm = VMState()
        result = _slice_heap_array(heap_obj, slice(0, 1), vm)
        assert isinstance(result, BuiltinResult)
        assert isinstance(result.value, str)
        assert len(result.new_objects) == 1

    def test_uncomputable_non_int_length(self):
        heap_obj = HeapObject(
            type_hint="array",
            fields={"length": typed("unknown", scalar(TypeName.STRING))},
        )
        vm = VMState()
        result = _slice_heap_array(heap_obj, slice(0, 1), vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE


class TestMethodSliceResult:
    def test_returns_builtin_result(self):
        vm = VMState()
        result = _method_slice([10, 20, 30], [0, 2], vm)
        assert isinstance(result, BuiltinResult)
