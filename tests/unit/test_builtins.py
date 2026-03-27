"""Tests for built-in function implementations."""

import logging

from interpreter.field_name import FieldName
from interpreter.vm.builtins import (
    _builtin_print,
    _builtin_slice,
    _builtin_object_rest,
    Builtins,
)
from interpreter.vm.vm import Operators, apply_update
from interpreter.vm.vm_types import (
    BuiltinResult,
    HeapObject,
    StackFrame,
    StateUpdate,
    VMState,
)
from interpreter.types.typed_value import TypedValue, typed_from_runtime
from interpreter.vm.vm_types import Pointer


def _apply_builtin_result(vm: VMState, result: BuiltinResult) -> None:
    """Apply BuiltinResult side effects to VM for unit testing."""
    apply_update(
        vm,
        StateUpdate(
            new_objects=result.new_objects,
            heap_writes=result.heap_writes,
        ),
    )


def _result_addr(result: BuiltinResult) -> str:
    """Extract the heap address from a BuiltinResult value (TypedValue<Pointer> or bare string)."""
    val = result.value
    if isinstance(val, TypedValue):
        val = val.value
    if isinstance(val, Pointer):
        return val.base
    return val


class TestBuiltinPrint:
    def test_returns_none(self):
        vm = VMState()
        result = _builtin_print(
            [typed_from_runtime("hello"), typed_from_runtime(42)], vm
        )
        assert result.value is None

    def test_logs_arguments(self, caplog):
        vm = VMState()
        with caplog.at_level(logging.INFO, logger="interpreter.vm.builtins"):
            _builtin_print([typed_from_runtime("hello"), typed_from_runtime(42)], vm)
        assert "[VM print] hello 42" in caplog.text

    def test_logs_empty_args(self, caplog):
        vm = VMState()
        with caplog.at_level(logging.INFO, logger="interpreter.vm.builtins"):
            _builtin_print([], vm)
        assert "[VM print] " in caplog.text


class TestBuiltinSlice:
    def test_slice_native_list(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        result = _builtin_slice(
            [typed_from_runtime([10, 20, 30, 40]), typed_from_runtime(1)], vm
        )
        _apply_builtin_result(vm, result)
        heap_obj = vm.heap[_result_addr(result)]
        assert heap_obj.fields[FieldName("0", FieldKind.INDEX)].value == 20
        assert heap_obj.fields[FieldName("1", FieldKind.INDEX)].value == 30
        assert heap_obj.fields[FieldName("2", FieldKind.INDEX)].value == 40
        assert heap_obj.fields[FieldName("length", FieldKind.SPECIAL)].value == 3

    def test_slice_native_list_from_index_2(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        result = _builtin_slice(
            [typed_from_runtime([1, 2, 3, 4, 5]), typed_from_runtime(2)], vm
        )
        _apply_builtin_result(vm, result)
        heap_obj = vm.heap[_result_addr(result)]
        assert heap_obj.fields[FieldName("length", FieldKind.SPECIAL)].value == 3
        assert heap_obj.fields[FieldName("0", FieldKind.INDEX)].value == 3

    def test_slice_heap_array(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        addr = "<arr:0>"
        vm.heap[addr] = HeapObject(
            type_hint="array",
            fields={
                k: typed_from_runtime(v)
                for k, v in {
                    FieldName("0", FieldKind.INDEX): "a",
                    FieldName("1", FieldKind.INDEX): "b",
                    FieldName("2", FieldKind.INDEX): "c",
                    FieldName("length", FieldKind.SPECIAL): 3,
                }.items()
            },
        )
        result = _builtin_slice([typed_from_runtime(addr), typed_from_runtime(1)], vm)
        _apply_builtin_result(vm, result)
        heap_obj = vm.heap[_result_addr(result)]
        assert heap_obj.fields[FieldName("0", FieldKind.INDEX)].value == "b"
        assert heap_obj.fields[FieldName("1", FieldKind.INDEX)].value == "c"
        assert heap_obj.fields[FieldName("length", FieldKind.SPECIAL)].value == 2

    def test_slice_insufficient_args(self):
        vm = VMState()
        assert (
            _builtin_slice([typed_from_runtime(42)], vm).value is Operators.UNCOMPUTABLE
        )

    def test_slice_with_stop_native_list(self):
        """slice(collection, start, stop) should return elements [start:stop]."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        result = _builtin_slice(
            [
                typed_from_runtime([10, 20, 30, 40, 50]),
                typed_from_runtime(1),
                typed_from_runtime(3),
            ],
            vm,
        )
        _apply_builtin_result(vm, result)
        heap_obj = vm.heap[_result_addr(result)]
        assert heap_obj.fields[FieldName("0", FieldKind.INDEX)].value == 20
        assert heap_obj.fields[FieldName("1", FieldKind.INDEX)].value == 30
        assert heap_obj.fields[FieldName("length", FieldKind.SPECIAL)].value == 2

    def test_slice_with_stop_heap_array(self):
        """slice(heap_arr, 1, 3) should return elements at indices 1 and 2."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        addr = "<arr:0>"
        vm.heap[addr] = HeapObject(
            type_hint="array",
            fields={
                k: typed_from_runtime(v)
                for k, v in {
                    FieldName("0", FieldKind.INDEX): "a",
                    FieldName("1", FieldKind.INDEX): "b",
                    FieldName("2", FieldKind.INDEX): "c",
                    FieldName("3", FieldKind.INDEX): "d",
                    FieldName("length", FieldKind.SPECIAL): 4,
                }.items()
            },
        )
        result = _builtin_slice(
            [typed_from_runtime(addr), typed_from_runtime(1), typed_from_runtime(3)], vm
        )
        _apply_builtin_result(vm, result)
        heap_obj = vm.heap[_result_addr(result)]
        assert heap_obj.fields[FieldName("0", FieldKind.INDEX)].value == "b"
        assert heap_obj.fields[FieldName("1", FieldKind.INDEX)].value == "c"
        assert heap_obj.fields[FieldName("length", FieldKind.SPECIAL)].value == 2

    def test_slice_with_step(self):
        """slice(collection, start, stop, step) with step=2."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        result = _builtin_slice(
            [
                typed_from_runtime([0, 1, 2, 3, 4, 5]),
                typed_from_runtime(0),
                typed_from_runtime(5),
                typed_from_runtime(2),
            ],
            vm,
        )
        _apply_builtin_result(vm, result)
        heap_obj = vm.heap[_result_addr(result)]
        assert heap_obj.fields[FieldName("0", FieldKind.INDEX)].value == 0
        assert heap_obj.fields[FieldName("1", FieldKind.INDEX)].value == 2
        assert heap_obj.fields[FieldName("2", FieldKind.INDEX)].value == 4
        assert heap_obj.fields[FieldName("length", FieldKind.SPECIAL)].value == 3

    def test_slice_with_none_stop(self):
        """slice(collection, 2, 'None') should slice from index 2 to end."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        result = _builtin_slice(
            [
                typed_from_runtime([10, 20, 30, 40]),
                typed_from_runtime(2),
                typed_from_runtime("None"),
            ],
            vm,
        )
        _apply_builtin_result(vm, result)
        heap_obj = vm.heap[_result_addr(result)]
        assert heap_obj.fields[FieldName("0", FieldKind.INDEX)].value == 30
        assert heap_obj.fields[FieldName("1", FieldKind.INDEX)].value == 40
        assert heap_obj.fields[FieldName("length", FieldKind.SPECIAL)].value == 2

    def test_slice_with_none_start(self):
        """slice(collection, 'None', 2) should slice from beginning to index 2."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        result = _builtin_slice(
            [
                typed_from_runtime([10, 20, 30, 40]),
                typed_from_runtime("None"),
                typed_from_runtime(2),
            ],
            vm,
        )
        _apply_builtin_result(vm, result)
        heap_obj = vm.heap[_result_addr(result)]
        assert heap_obj.fields[FieldName("0", FieldKind.INDEX)].value == 10
        assert heap_obj.fields[FieldName("1", FieldKind.INDEX)].value == 20
        assert heap_obj.fields[FieldName("length", FieldKind.SPECIAL)].value == 2

    def test_slice_negative_start(self):
        """slice(collection, -2) should slice last 2 elements."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        result = _builtin_slice(
            [typed_from_runtime([10, 20, 30, 40]), typed_from_runtime(-2)], vm
        )
        _apply_builtin_result(vm, result)
        heap_obj = vm.heap[_result_addr(result)]
        assert heap_obj.fields[FieldName("0", FieldKind.INDEX)].value == 30
        assert heap_obj.fields[FieldName("1", FieldKind.INDEX)].value == 40
        assert heap_obj.fields[FieldName("length", FieldKind.SPECIAL)].value == 2

    def test_slice_string(self):
        """slice(string, start, stop) should return substring."""
        vm = VMState()
        result = _builtin_slice(
            [typed_from_runtime("hello"), typed_from_runtime(1), typed_from_runtime(3)],
            vm,
        )
        assert result.value == "el"

    def test_slice_string_no_stop(self):
        """slice(string, 2) should return from index 2 onward."""
        vm = VMState()
        result = _builtin_slice(
            [typed_from_runtime("hello"), typed_from_runtime(2)], vm
        )
        assert result.value == "llo"


class TestBuiltinObjectRest:
    def test_object_rest_excludes_keys(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        addr = "<obj:0>"
        vm.heap[addr] = HeapObject(
            type_hint="object",
            fields={
                k: typed_from_runtime(v)
                for k, v in {
                    FieldName("a"): 1,
                    FieldName("b"): 2,
                    FieldName("c"): 3,
                }.items()
            },
        )
        result = _builtin_object_rest(
            [typed_from_runtime(addr), typed_from_runtime("a")], vm
        )
        _apply_builtin_result(vm, result)
        heap_obj = vm.heap[_result_addr(result)]
        assert FieldName("a") not in heap_obj.fields
        assert heap_obj.fields[FieldName("b")].value == 2
        assert heap_obj.fields[FieldName("c")].value == 3

    def test_object_rest_excludes_multiple_keys(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        addr = "<obj:0>"
        vm.heap[addr] = HeapObject(
            type_hint="object",
            fields={
                k: typed_from_runtime(v)
                for k, v in {
                    FieldName("x"): 10,
                    FieldName("y"): 20,
                    FieldName("z"): 30,
                }.items()
            },
        )
        result = _builtin_object_rest(
            [
                typed_from_runtime(addr),
                typed_from_runtime("x"),
                typed_from_runtime("y"),
            ],
            vm,
        )
        _apply_builtin_result(vm, result)
        heap_obj = vm.heap[_result_addr(result)]
        assert heap_obj.fields[FieldName("z")].value == 30
        assert set(heap_obj.fields.keys()) == {"z"}

    def test_object_rest_no_args(self):
        vm = VMState()
        result = _builtin_object_rest([], vm)
        assert result.value is Operators.UNCOMPUTABLE

    def test_object_rest_non_heap(self):
        vm = VMState()
        result = _builtin_object_rest([typed_from_runtime("not_a_heap_addr")], vm)
        assert result.value is Operators.UNCOMPUTABLE


class TestMethodBuiltins:
    """Method builtins: obj.method(args) dispatched via METHOD_TABLE."""

    def test_sublist_delegates_to_slice(self):
        """subList should call slice(obj, start, stop)."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="test"))
        addr = "<arr:0>"
        vm.heap[addr] = HeapObject(
            type_hint="array",
            fields={
                k: typed_from_runtime(v)
                for k, v in {
                    FieldName("0", FieldKind.INDEX): 10,
                    FieldName("1", FieldKind.INDEX): 20,
                    FieldName("2", FieldKind.INDEX): 30,
                    FieldName("3", FieldKind.INDEX): 40,
                    FieldName("length", FieldKind.SPECIAL): 4,
                }.items()
            },
        )
        fn = Builtins.METHOD_TABLE["subList"]
        result = fn(
            typed_from_runtime(addr), [typed_from_runtime(1), typed_from_runtime(3)], vm
        )
        _apply_builtin_result(vm, result)
        heap_obj = vm.heap[_result_addr(result)]
        assert heap_obj.fields[FieldName("0", FieldKind.INDEX)].value == 20
        assert heap_obj.fields[FieldName("1", FieldKind.INDEX)].value == 30
        assert heap_obj.fields[FieldName("length", FieldKind.SPECIAL)].value == 2

    def test_substring_delegates_to_slice(self):
        """substring should call slice(obj, start, stop) on strings."""
        vm = VMState()
        fn = Builtins.METHOD_TABLE["substring"]
        result = fn(
            typed_from_runtime("hello"),
            [typed_from_runtime(1), typed_from_runtime(3)],
            vm,
        )
        assert result.value == "el"

    def test_method_table_has_expected_entries(self):
        assert "subList" in Builtins.METHOD_TABLE
        assert "substring" in Builtins.METHOD_TABLE
        assert "slice" in Builtins.METHOD_TABLE
