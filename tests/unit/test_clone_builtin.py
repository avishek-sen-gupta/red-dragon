"""Unit tests for the clone builtin (PHP object cloning)."""

from __future__ import annotations

from interpreter.builtins import Builtins
from interpreter.vm import VMState
from interpreter.vm_types import BuiltinResult, HeapObject, Pointer
from interpreter.typed_value import typed, typed_from_runtime
from interpreter.type_expr import scalar
from interpreter.constants import TypeName


class TestCloneBuiltin:
    def _make_vm_with_object(
        self, type_hint: str, fields: dict
    ) -> tuple[VMState, Pointer]:
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(type_hint=type_hint, fields=fields)
        return vm, Pointer(base="obj_0", offset=0)

    def test_clone_is_registered(self):
        assert "clone" in Builtins.TABLE

    def test_clone_creates_new_object(self):
        """clone should return a new Pointer, not the original."""
        vm, ptr = self._make_vm_with_object(
            "MyClass",
            {"x": typed(42, scalar(TypeName.INT))},
        )
        result = Builtins.TABLE["clone"]([typed_from_runtime(ptr)], vm)
        assert isinstance(result, BuiltinResult)
        assert isinstance(result.value.value, Pointer)
        assert result.value.value.base != "obj_0"  # different heap address

    def test_clone_copies_all_fields(self):
        """clone should copy all fields from the original object."""
        vm, ptr = self._make_vm_with_object(
            "MyClass",
            {
                "x": typed(42, scalar(TypeName.INT)),
                "name": typed("hello", scalar(TypeName.STRING)),
            },
        )
        result = Builtins.TABLE["clone"]([typed_from_runtime(ptr)], vm)
        field_writes = {w.field: w.value for w in result.heap_writes}
        assert field_writes["x"].value == 42
        assert field_writes["name"].value == "hello"

    def test_clone_preserves_type_hint(self):
        """clone should create a new object with the same type_hint."""
        vm, ptr = self._make_vm_with_object(
            "Dog",
            {"breed": typed("labrador", scalar(TypeName.STRING))},
        )
        result = Builtins.TABLE["clone"]([typed_from_runtime(ptr)], vm)
        assert len(result.new_objects) == 1
        assert result.new_objects[0].type_hint == "Dog"
