"""Tests for built-in function implementations."""

import logging

from interpreter.builtins import (
    _builtin_print,
    _builtin_slice,
    _builtin_object_rest,
    Builtins,
)
from interpreter.vm import Operators
from interpreter.vm_types import HeapObject, VMState
from interpreter.typed_value import typed_from_runtime


class TestBuiltinPrint:
    def test_returns_none(self):
        vm = VMState()
        result = _builtin_print(["hello", 42], vm)
        assert result is None

    def test_logs_arguments(self, caplog):
        vm = VMState()
        with caplog.at_level(logging.INFO, logger="interpreter.builtins"):
            _builtin_print(["hello", 42], vm)
        assert "[VM print] hello 42" in caplog.text

    def test_logs_empty_args(self, caplog):
        vm = VMState()
        with caplog.at_level(logging.INFO, logger="interpreter.builtins"):
            _builtin_print([], vm)
        assert "[VM print] " in caplog.text


class TestBuiltinSlice:
    def test_slice_native_list(self):
        vm = VMState()
        result = _builtin_slice([[10, 20, 30, 40], 1], vm)
        # Returns heap address; verify heap array contents
        assert result in vm.heap
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"].value == 20
        assert heap_obj.fields["1"].value == 30
        assert heap_obj.fields["2"].value == 40
        assert heap_obj.fields["length"].value == 3

    def test_slice_native_list_from_index_2(self):
        vm = VMState()
        result = _builtin_slice([[1, 2, 3, 4, 5], 2], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["length"].value == 3
        assert heap_obj.fields["0"].value == 3

    def test_slice_heap_array(self):
        vm = VMState()
        addr = "<arr:0>"
        vm.heap[addr] = HeapObject(
            type_hint="array",
            fields={
                k: typed_from_runtime(v)
                for k, v in {"0": "a", "1": "b", "2": "c", "length": 3}.items()
            },
        )
        result = _builtin_slice([addr, 1], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"].value == "b"
        assert heap_obj.fields["1"].value == "c"
        assert heap_obj.fields["length"].value == 2

    def test_slice_insufficient_args(self):
        vm = VMState()
        assert _builtin_slice([42], vm) is Operators.UNCOMPUTABLE

    def test_slice_with_stop_native_list(self):
        """slice(collection, start, stop) should return elements [start:stop]."""
        vm = VMState()
        result = _builtin_slice([[10, 20, 30, 40, 50], 1, 3], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"].value == 20
        assert heap_obj.fields["1"].value == 30
        assert heap_obj.fields["length"].value == 2

    def test_slice_with_stop_heap_array(self):
        """slice(heap_arr, 1, 3) should return elements at indices 1 and 2."""
        vm = VMState()
        addr = "<arr:0>"
        vm.heap[addr] = HeapObject(
            type_hint="array",
            fields={
                k: typed_from_runtime(v)
                for k, v in {
                    "0": "a",
                    "1": "b",
                    "2": "c",
                    "3": "d",
                    "length": 4,
                }.items()
            },
        )
        result = _builtin_slice([addr, 1, 3], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"].value == "b"
        assert heap_obj.fields["1"].value == "c"
        assert heap_obj.fields["length"].value == 2

    def test_slice_with_step(self):
        """slice(collection, start, stop, step) with step=2."""
        vm = VMState()
        result = _builtin_slice([[0, 1, 2, 3, 4, 5], 0, 5, 2], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"].value == 0
        assert heap_obj.fields["1"].value == 2
        assert heap_obj.fields["2"].value == 4
        assert heap_obj.fields["length"].value == 3

    def test_slice_with_none_stop(self):
        """slice(collection, 2, 'None') should slice from index 2 to end."""
        vm = VMState()
        result = _builtin_slice([[10, 20, 30, 40], 2, "None"], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"].value == 30
        assert heap_obj.fields["1"].value == 40
        assert heap_obj.fields["length"].value == 2

    def test_slice_with_none_start(self):
        """slice(collection, 'None', 2) should slice from beginning to index 2."""
        vm = VMState()
        result = _builtin_slice([[10, 20, 30, 40], "None", 2], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"].value == 10
        assert heap_obj.fields["1"].value == 20
        assert heap_obj.fields["length"].value == 2

    def test_slice_negative_start(self):
        """slice(collection, -2) should slice last 2 elements."""
        vm = VMState()
        result = _builtin_slice([[10, 20, 30, 40], -2], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"].value == 30
        assert heap_obj.fields["1"].value == 40
        assert heap_obj.fields["length"].value == 2

    def test_slice_string(self):
        """slice(string, start, stop) should return substring."""
        vm = VMState()
        result = _builtin_slice(["hello", 1, 3], vm)
        assert result == "el"

    def test_slice_string_no_stop(self):
        """slice(string, 2) should return from index 2 onward."""
        vm = VMState()
        result = _builtin_slice(["hello", 2], vm)
        assert result == "llo"


class TestBuiltinObjectRest:
    def test_object_rest_excludes_keys(self):
        vm = VMState()
        addr = "<obj:0>"
        vm.heap[addr] = HeapObject(
            type_hint="object",
            fields={
                k: typed_from_runtime(v) for k, v in {"a": 1, "b": 2, "c": 3}.items()
            },
        )
        result = _builtin_object_rest([addr, "a"], vm)
        heap_obj = vm.heap[result]
        assert "a" not in heap_obj.fields
        assert heap_obj.fields["b"].value == 2
        assert heap_obj.fields["c"].value == 3

    def test_object_rest_excludes_multiple_keys(self):
        vm = VMState()
        addr = "<obj:0>"
        vm.heap[addr] = HeapObject(
            type_hint="object",
            fields={
                k: typed_from_runtime(v) for k, v in {"x": 10, "y": 20, "z": 30}.items()
            },
        )
        result = _builtin_object_rest([addr, "x", "y"], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["z"].value == 30
        assert set(heap_obj.fields.keys()) == {"z"}

    def test_object_rest_no_args(self):
        vm = VMState()
        assert _builtin_object_rest([], vm) is Operators.UNCOMPUTABLE

    def test_object_rest_non_heap(self):
        vm = VMState()
        assert _builtin_object_rest(["not_a_heap_addr"], vm) is Operators.UNCOMPUTABLE


class TestMethodBuiltins:
    """Method builtins: obj.method(args) dispatched via METHOD_TABLE."""

    def test_sublist_delegates_to_slice(self):
        """subList should call slice(obj, start, stop)."""
        vm = VMState()
        addr = "<arr:0>"
        vm.heap[addr] = HeapObject(
            type_hint="array",
            fields={
                k: typed_from_runtime(v)
                for k, v in {"0": 10, "1": 20, "2": 30, "3": 40, "length": 4}.items()
            },
        )
        fn = Builtins.METHOD_TABLE["subList"]
        result = fn(addr, [1, 3], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"].value == 20
        assert heap_obj.fields["1"].value == 30
        assert heap_obj.fields["length"].value == 2

    def test_substring_delegates_to_slice(self):
        """substring should call slice(obj, start, stop) on strings."""
        vm = VMState()
        fn = Builtins.METHOD_TABLE["substring"]
        result = fn("hello", [1, 3], vm)
        assert result == "el"

    def test_method_table_has_expected_entries(self):
        assert "subList" in Builtins.METHOD_TABLE
        assert "substring" in Builtins.METHOD_TABLE
        assert "slice" in Builtins.METHOD_TABLE
