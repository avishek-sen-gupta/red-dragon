"""Unit tests for _builtin_object_rest returning BuiltinResult."""

from interpreter.field_name import FieldName
from interpreter.vm.builtins import _builtin_object_rest
from interpreter.vm.vm import VMState, Operators
from interpreter.vm.vm_types import BuiltinResult, HeapObject, Pointer
from interpreter.types.type_expr import scalar
from interpreter.types.typed_value import TypedValue, typed_from_runtime


class TestObjectRestBuiltinResult:
    def test_returns_builtin_result(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={
                FieldName("a"): typed_from_runtime(1),
                FieldName("b"): typed_from_runtime(2),
                FieldName("c"): typed_from_runtime(3),
            },
        )
        result = _builtin_object_rest(
            [typed_from_runtime("obj_0"), typed_from_runtime("a")], vm
        )
        assert isinstance(result, BuiltinResult)

    def test_new_objects_contains_rest_object(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={
                FieldName("a"): typed_from_runtime(1),
                FieldName("b"): typed_from_runtime(2),
            },
        )
        result = _builtin_object_rest(
            [typed_from_runtime("obj_0"), typed_from_runtime("a")], vm
        )
        assert len(result.new_objects) == 1
        assert isinstance(result.value, TypedValue)
        assert isinstance(result.value.value, Pointer)
        assert result.new_objects[0].addr == result.value.value.base
        assert result.new_objects[0].type_hint == scalar("Object")

    def test_heap_writes_contain_rest_fields(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={
                FieldName("a"): typed_from_runtime(1),
                FieldName("b"): typed_from_runtime(2),
                FieldName("c"): typed_from_runtime(3),
            },
        )
        result = _builtin_object_rest(
            [typed_from_runtime("obj_0"), typed_from_runtime("a")], vm
        )
        fields = {hw.field: hw.value for hw in result.heap_writes}
        assert FieldName("a") not in fields
        assert FieldName("b") in fields
        assert FieldName("c") in fields

    def test_does_not_mutate_heap(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={
                FieldName("a"): typed_from_runtime(1),
                FieldName("b"): typed_from_runtime(2),
            },
        )
        result = _builtin_object_rest(
            [typed_from_runtime("obj_0"), typed_from_runtime("a")], vm
        )
        assert str(result.value.value.base) not in vm.heap

    def test_uncomputable_no_args_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_object_rest([], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE

    def test_uncomputable_source_not_on_heap(self):
        vm = VMState()
        result = _builtin_object_rest(
            [typed_from_runtime("nonexistent_addr"), typed_from_runtime("a")], vm
        )
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE
        assert result.new_objects == []
