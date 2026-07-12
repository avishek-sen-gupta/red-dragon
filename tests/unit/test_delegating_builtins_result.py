"""Unit tests for partially-delegating builtins returning BuiltinResult."""

from interpreter.address import Address
from interpreter.constants import FoundationTypeName
from interpreter.field_name import FieldKind, FieldName
from interpreter.types.type_expr import scalar
from interpreter.types.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.vm.builtins import (
    _builtin_keys,
    _builtin_slice,
    _method_slice,
    _slice_heap_array,
)
from interpreter.vm.vm import Operators
from interpreter.vm.vm_types import BuiltinResult, HeapObject, Pointer, VMState


class TestBuiltinKeysResult:
    def test_uncomputable_no_args_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_keys([], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE

    def test_uncomputable_not_on_heap_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_keys([typed_from_runtime("nonexistent")], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE

    def test_happy_path_returns_builtin_result(self):
        vm = VMState()
        vm.heap_set(
            Address("obj_0"),
            HeapObject(
                type_hint="object",
                fields={FieldName("a"): typed_from_runtime(1)},
            ),
        )
        result = _builtin_keys([typed_from_runtime("obj_0")], vm)
        assert isinstance(result, BuiltinResult)
        assert isinstance(result.value, TypedValue)
        assert isinstance(result.value.value, Pointer)
        assert len(result.new_objects) == 1


class TestBuiltinSliceResult:
    def test_uncomputable_bad_args_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_slice([typed_from_runtime(1)], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE

    def test_native_list_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_slice(
            [
                typed_from_runtime([10, 20, 30]),
                typed_from_runtime(0),
                typed_from_runtime(2),
            ],
            vm,
        )
        assert isinstance(result, BuiltinResult)
        assert isinstance(result.value, TypedValue)
        assert isinstance(result.value.value, Pointer)

    def test_native_string_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_slice(
            [typed_from_runtime("hello"), typed_from_runtime(1), typed_from_runtime(3)],
            vm,
        )
        assert isinstance(result, BuiltinResult)
        assert result.value == "el"
        assert result.new_objects == []

    def test_heap_array_returns_builtin_result(self):
        vm = VMState()
        vm.heap_set(
            Address("arr_0"),
            HeapObject(
                type_hint="array",
                fields={
                    FieldName("0", FieldKind.INDEX): typed(
                        10, scalar(FoundationTypeName.INT)
                    ),
                    FieldName("1", FieldKind.INDEX): typed(
                        20, scalar(FoundationTypeName.INT)
                    ),
                    FieldName("2", FieldKind.INDEX): typed(
                        30, scalar(FoundationTypeName.INT)
                    ),
                    FieldName("length", FieldKind.SPECIAL): typed(
                        3, scalar(FoundationTypeName.INT)
                    ),
                },
            ),
        )
        result = _builtin_slice(
            [typed_from_runtime("arr_0"), typed_from_runtime(0), typed_from_runtime(2)],
            vm,
        )
        assert isinstance(result, BuiltinResult)
        assert isinstance(result.value, TypedValue)
        assert isinstance(result.value.value, Pointer)
        assert len(result.new_objects) == 1


class TestSliceHeapArrayResult:
    def test_returns_builtin_result(self):
        heap_obj = HeapObject(
            type_hint="array",
            fields={
                FieldName("0", FieldKind.INDEX): typed(
                    10, scalar(FoundationTypeName.INT)
                ),
                FieldName("1", FieldKind.INDEX): typed(
                    20, scalar(FoundationTypeName.INT)
                ),
                FieldName("length", FieldKind.SPECIAL): typed(
                    2, scalar(FoundationTypeName.INT)
                ),
            },
        )
        vm = VMState()
        result = _slice_heap_array(heap_obj, slice(0, 1), vm)
        assert isinstance(result, BuiltinResult)
        assert isinstance(result.value, TypedValue)
        assert isinstance(result.value.value, Pointer)
        assert len(result.new_objects) == 1

    def test_uncomputable_non_int_length(self):
        heap_obj = HeapObject(
            type_hint="array",
            fields={
                FieldName("length", FieldKind.SPECIAL): typed(
                    "unknown", scalar(FoundationTypeName.STRING)
                )
            },
        )
        vm = VMState()
        result = _slice_heap_array(heap_obj, slice(0, 1), vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE


class TestMethodSliceResult:
    def test_returns_builtin_result(self):
        vm = VMState()
        result = _method_slice(
            typed_from_runtime([10, 20, 30]),
            [typed_from_runtime(0), typed_from_runtime(2)],
            vm,
        )
        assert isinstance(result, BuiltinResult)
