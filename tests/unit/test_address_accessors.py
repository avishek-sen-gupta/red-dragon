"""Tests for VMState heap/region accessors and NullHeapObject."""

from interpreter.address import Address
from interpreter.field_name import FieldName
from interpreter.vm.vm_types import VMState, HeapObject, NO_HEAP_OBJECT


class TestVMStateHeapAccessors:
    def test_heap_get_found(self):
        vm = VMState()
        vm.heap_set(Address("obj_0"), HeapObject())
        assert vm.heap_get(Address("obj_0")) is not None

    def test_heap_get_not_found_returns_null(self):
        vm = VMState()
        result = vm.heap_get(Address("missing"))
        assert not result.is_present()
        assert result is NO_HEAP_OBJECT

    def test_heap_get_found_is_present(self):
        vm = VMState()
        vm.heap_set(Address("obj_0"), HeapObject())
        assert vm.heap_get(Address("obj_0")).is_present()

    def test_heap_set_and_get(self):
        vm = VMState()
        obj = HeapObject()
        vm.heap_set(Address("obj_0"), obj)
        assert vm.heap_get(Address("obj_0")) is obj

    def test_heap_contains(self):
        vm = VMState()
        vm.heap_set(Address("obj_0"), HeapObject())
        assert vm.heap_contains(Address("obj_0"))
        assert not vm.heap_contains(Address("missing"))

    def test_heap_ensure_creates(self):
        vm = VMState()
        obj = vm.heap_ensure(Address("obj_0"))
        assert isinstance(obj, HeapObject)
        assert vm.heap_contains(Address("obj_0"))

    def test_heap_ensure_returns_existing(self):
        vm = VMState()
        vm.heap_set(Address("obj_0"), HeapObject())
        obj = vm.heap_ensure(Address("obj_0"))
        assert obj is vm.heap_get(Address("obj_0"))

    def test_null_heap_object_fields_empty(self):
        assert len(NO_HEAP_OBJECT.fields) == 0

    def test_null_heap_object_fields_get_returns_none(self):
        assert NO_HEAP_OBJECT.fields.get(FieldName("x")) is None

    def test_heap_items(self):
        vm = VMState()
        obj = HeapObject()
        vm.heap_set(Address("obj_0"), obj)
        items = list(vm.heap_items())
        assert len(items) == 1
        assert items[0] == (Address("obj_0"), obj)

    def test_heap_keys(self):
        vm = VMState()
        vm.heap_set(Address("obj_0"), HeapObject())
        vm.heap_set(Address("arr_1"), HeapObject())
        keys = list(vm.heap_keys())
        assert Address("obj_0") in keys
        assert Address("arr_1") in keys

    def test_region_set_and_get(self):
        vm = VMState()
        data = bytearray(b"\x01\x02\x03")
        vm.region_set(Address("mem_0"), data)
        assert vm.region_get(Address("mem_0")) is data

    def test_region_get_missing_returns_none(self):
        vm = VMState()
        assert vm.region_get(Address("missing")) is None
