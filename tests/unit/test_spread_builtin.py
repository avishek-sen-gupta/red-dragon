"""Unit tests for the spread builtin and argument flattening."""

from __future__ import annotations

import pytest

from interpreter.builtins import Builtins
from interpreter.vm import VMState
from interpreter.vm_types import BuiltinResult, HeapObject, Pointer
from interpreter.typed_value import typed, typed_from_runtime
from interpreter.type_expr import scalar
from interpreter.constants import TypeName


class TestSpreadBuiltin:
    def _make_vm_with_array(self, elements: list) -> tuple[VMState, Pointer]:
        """Create a VM with a heap array containing the given elements."""
        vm = VMState()
        fields = {
            str(i): typed(e, scalar(TypeName.INT)) for i, e in enumerate(elements)
        }
        fields["length"] = typed(len(elements), scalar(TypeName.INT))
        vm.heap["arr_0"] = HeapObject(type_hint="Array", fields=fields)
        return vm, Pointer(base="arr_0", offset=0)

    def test_spread_is_registered(self):
        """spread should be in the builtins TABLE."""
        assert "spread" in Builtins.TABLE

    def test_spread_returns_list_of_elements(self):
        """spread(array_ptr) should return a list of the array's elements."""
        vm, ptr = self._make_vm_with_array([10, 5, 3])
        result = Builtins.TABLE["spread"]([typed_from_runtime(ptr)], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == [10, 5, 3]

    def test_spread_empty_array(self):
        """spread on an empty array should return an empty list."""
        vm, ptr = self._make_vm_with_array([])
        result = Builtins.TABLE["spread"]([typed_from_runtime(ptr)], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == []

    def test_spread_single_element(self):
        """spread on a single-element array should return a one-element list."""
        vm, ptr = self._make_vm_with_array([42])
        result = Builtins.TABLE["spread"]([typed_from_runtime(ptr)], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == [42]

    def test_spread_preserves_order(self):
        """Elements should come out in index order 0, 1, 2, ..."""
        vm, ptr = self._make_vm_with_array([100, 200, 300, 400])
        result = Builtins.TABLE["spread"]([typed_from_runtime(ptr)], vm)
        assert result.value == [100, 200, 300, 400]
