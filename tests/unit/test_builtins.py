"""Tests for built-in function implementations."""

import logging

from interpreter.builtins import _builtin_print, _builtin_slice, _builtin_object_rest
from interpreter.vm import Operators
from interpreter.vm_types import HeapObject, VMState


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
        assert heap_obj.fields["0"] == 20
        assert heap_obj.fields["1"] == 30
        assert heap_obj.fields["2"] == 40
        assert heap_obj.fields["length"] == 3

    def test_slice_native_list_from_index_2(self):
        vm = VMState()
        result = _builtin_slice([[1, 2, 3, 4, 5], 2], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["length"] == 3
        assert heap_obj.fields["0"] == 3

    def test_slice_heap_array(self):
        vm = VMState()
        addr = "<arr:0>"
        vm.heap[addr] = HeapObject(
            type_hint="array",
            fields={"0": "a", "1": "b", "2": "c", "length": 3},
        )
        result = _builtin_slice([addr, 1], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"] == "b"
        assert heap_obj.fields["1"] == "c"
        assert heap_obj.fields["length"] == 2

    def test_slice_insufficient_args(self):
        vm = VMState()
        assert _builtin_slice([42], vm) is Operators.UNCOMPUTABLE

    def test_slice_with_stop_native_list(self):
        """slice(collection, start, stop) should return elements [start:stop]."""
        vm = VMState()
        result = _builtin_slice([[10, 20, 30, 40, 50], 1, 3], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"] == 20
        assert heap_obj.fields["1"] == 30
        assert heap_obj.fields["length"] == 2

    def test_slice_with_stop_heap_array(self):
        """slice(heap_arr, 1, 3) should return elements at indices 1 and 2."""
        vm = VMState()
        addr = "<arr:0>"
        vm.heap[addr] = HeapObject(
            type_hint="array",
            fields={"0": "a", "1": "b", "2": "c", "3": "d", "length": 4},
        )
        result = _builtin_slice([addr, 1, 3], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"] == "b"
        assert heap_obj.fields["1"] == "c"
        assert heap_obj.fields["length"] == 2

    def test_slice_with_step(self):
        """slice(collection, start, stop, step) with step=2."""
        vm = VMState()
        result = _builtin_slice([[0, 1, 2, 3, 4, 5], 0, 5, 2], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"] == 0
        assert heap_obj.fields["1"] == 2
        assert heap_obj.fields["2"] == 4
        assert heap_obj.fields["length"] == 3

    def test_slice_with_none_stop(self):
        """slice(collection, 2, 'None') should slice from index 2 to end."""
        vm = VMState()
        result = _builtin_slice([[10, 20, 30, 40], 2, "None"], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"] == 30
        assert heap_obj.fields["1"] == 40
        assert heap_obj.fields["length"] == 2

    def test_slice_with_none_start(self):
        """slice(collection, 'None', 2) should slice from beginning to index 2."""
        vm = VMState()
        result = _builtin_slice([[10, 20, 30, 40], "None", 2], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"] == 10
        assert heap_obj.fields["1"] == 20
        assert heap_obj.fields["length"] == 2

    def test_slice_negative_start(self):
        """slice(collection, -2) should slice last 2 elements."""
        vm = VMState()
        result = _builtin_slice([[10, 20, 30, 40], -2], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields["0"] == 30
        assert heap_obj.fields["1"] == 40
        assert heap_obj.fields["length"] == 2

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
            fields={"a": 1, "b": 2, "c": 3},
        )
        result = _builtin_object_rest([addr, "a"], vm)
        heap_obj = vm.heap[result]
        assert "a" not in heap_obj.fields
        assert heap_obj.fields["b"] == 2
        assert heap_obj.fields["c"] == 3

    def test_object_rest_excludes_multiple_keys(self):
        vm = VMState()
        addr = "<obj:0>"
        vm.heap[addr] = HeapObject(
            type_hint="object",
            fields={"x": 10, "y": 20, "z": 30},
        )
        result = _builtin_object_rest([addr, "x", "y"], vm)
        heap_obj = vm.heap[result]
        assert heap_obj.fields == {"z": 30}

    def test_object_rest_no_args(self):
        vm = VMState()
        assert _builtin_object_rest([], vm) is Operators.UNCOMPUTABLE

    def test_object_rest_non_heap(self):
        vm = VMState()
        assert _builtin_object_rest(["not_a_heap_addr"], vm) is Operators.UNCOMPUTABLE
