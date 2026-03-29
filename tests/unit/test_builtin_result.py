"""Unit tests for BuiltinResult dataclass."""

from interpreter.field_name import FieldName, FieldKind
from interpreter.types.type_expr import scalar
from interpreter.address import Address
from interpreter.vm.vm_types import BuiltinResult, NewObject, HeapWrite


class TestBuiltinResult:
    def test_pure_result_has_empty_side_effects(self):
        result = BuiltinResult(value=42)
        assert result.value == 42
        assert result.new_objects == []
        assert result.heap_writes == []

    def test_result_with_new_objects(self):
        obj = NewObject(addr=Address("arr_0"), type_hint=scalar("Array"))
        result = BuiltinResult(value="arr_0", new_objects=[obj])
        assert result.new_objects == [obj]
        assert result.heap_writes == []

    def test_result_with_heap_writes(self):
        from interpreter.types.typed_value import typed_from_runtime

        hw = HeapWrite(
            obj_addr=Address("arr_0"),
            field=FieldName("0", FieldKind.INDEX),
            value=typed_from_runtime(10),
        )
        result = BuiltinResult(value="arr_0", heap_writes=[hw])
        assert result.heap_writes[0].field == FieldName("0", FieldKind.INDEX)

    def test_result_with_all_fields(self):
        from interpreter.types.typed_value import typed_from_runtime

        obj = NewObject(addr=Address("arr_0"), type_hint=scalar("Array"))
        hw = HeapWrite(
            obj_addr=Address("arr_0"),
            field=FieldName("length", FieldKind.SPECIAL),
            value=typed_from_runtime(1),
        )
        result = BuiltinResult(value="arr_0", new_objects=[obj], heap_writes=[hw])
        assert result.value == "arr_0"
        assert len(result.new_objects) == 1
        assert len(result.heap_writes) == 1
