"""Unit tests for _builtin_len with heap arrays that have a 'length' field.

Arrays created by arrayOf/intArrayOf store elements as {'0': v0, '1': v1, ..., 'length': N}.
_builtin_len must return the 'length' field value (N), not len(fields) which
includes the 'length' key itself and produces an off-by-one.
"""

from __future__ import annotations

from interpreter.builtins import _builtin_len, _builtin_array_of
from interpreter.vm import VMState
from interpreter.vm_types import HeapObject


class TestBuiltinLenRespectsLengthField:
    def test_len_of_arrayOf_three_elements(self):
        vm = VMState()
        addr = _builtin_array_of([10, 5, 3], vm)
        result = _builtin_len([addr], vm)
        assert result == 3

    def test_len_of_arrayOf_empty(self):
        vm = VMState()
        addr = _builtin_array_of([], vm)
        result = _builtin_len([addr], vm)
        assert result == 0

    def test_len_of_arrayOf_single_element(self):
        vm = VMState()
        addr = _builtin_array_of([42], vm)
        result = _builtin_len([addr], vm)
        assert result == 1

    def test_len_of_heap_object_without_length_field(self):
        """Plain objects (no 'length' field) should use len(fields)."""
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(type_hint="object", fields={"a": 1, "b": 2})
        result = _builtin_len(["obj_0"], vm)
        assert result == 2

    def test_len_of_heap_object_with_length_field(self):
        """JS-style arrays with explicit 'length' field should return that value."""
        vm = VMState()
        vm.heap["arr_0"] = HeapObject(
            type_hint="array",
            fields={"0": 10, "1": 20, "2": 30, "length": 3},
        )
        result = _builtin_len(["arr_0"], vm)
        assert result == 3
