"""Unit tests for BuiltinResult dataclass."""

from interpreter.vm_types import BuiltinResult, NewObject, HeapWrite


class TestBuiltinResult:
    def test_pure_result_has_empty_side_effects(self):
        result = BuiltinResult(value=42)
        assert result.value == 42
        assert result.new_objects == []
        assert result.heap_writes == []

    def test_result_with_new_objects(self):
        obj = NewObject(addr="arr_0", type_hint="array")
        result = BuiltinResult(value="arr_0", new_objects=[obj])
        assert result.new_objects == [obj]
        assert result.heap_writes == []

    def test_result_with_heap_writes(self):
        from interpreter.typed_value import typed_from_runtime

        hw = HeapWrite(obj_addr="arr_0", field="0", value=typed_from_runtime(10))
        result = BuiltinResult(value="arr_0", heap_writes=[hw])
        assert result.heap_writes[0].field == "0"

    def test_result_with_all_fields(self):
        from interpreter.typed_value import typed_from_runtime

        obj = NewObject(addr="arr_0", type_hint="array")
        hw = HeapWrite(obj_addr="arr_0", field="length", value=typed_from_runtime(1))
        result = BuiltinResult(value="arr_0", new_objects=[obj], heap_writes=[hw])
        assert result.value == "arr_0"
        assert len(result.new_objects) == 1
        assert len(result.heap_writes) == 1
