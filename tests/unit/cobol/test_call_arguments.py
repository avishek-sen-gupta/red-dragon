"""call_arguments builds the argument array a callee's LINKAGE binds to."""

from interpreter.address import Address
from interpreter.cobol.call_arguments import call_arguments
from interpreter.field_name import FieldKind, FieldName
from interpreter.vm.vm_types import Pointer, VMState


def test_each_region_is_handed_over_by_base_address_with_the_count() -> None:
    vm = VMState()
    vm.region_set(Address("rgn_first"), bytearray(3))
    vm.region_set(Address("rgn_commarea"), bytearray(b"\x00" * 4))

    args = call_arguments(vm, [Address("rgn_commarea")])

    assert isinstance(args.value, Pointer)
    array = vm.heap_get(args.value.base)
    element = array.fields[FieldName("0", FieldKind.INDEX)].value
    assert isinstance(element, Pointer)
    fields = vm.heap_get(element.base).fields
    assert (
        array.fields[FieldName("count")].value,
        fields[FieldName("region")].value,
        fields[FieldName("offset")].value,
        fields[FieldName("omitted")].value,
    ) == (1, 4099, 0, False)
