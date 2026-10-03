"""The argument array a CALL hands its callee: one region and offset per argument."""

from __future__ import annotations

from collections.abc import Sequence

from interpreter import constants
from interpreter.address import Address
from interpreter.field_name import FieldKind, FieldName
from interpreter.types.type_expr import UNKNOWN
from interpreter.types.typed_value import TypedValue, typed
from interpreter.vm.vm_types import HeapObject, Pointer, VMState


def call_arguments(vm: VMState, regions: Sequence[Address]) -> TypedValue:
    """For a harness frame: each region passed BY REFERENCE at offset 0."""
    elements = tuple(_element(vm, region) for region in regions)
    array = _fresh(vm, constants.ARR_ADDR_PREFIX)
    vm.heap_set(
        array,
        HeapObject(
            fields={
                FieldName("count"): typed(len(elements), UNKNOWN),
                **{
                    FieldName(str(position), FieldKind.INDEX): element
                    for position, element in enumerate(elements)
                },
            }
        ),
    )
    return typed(Pointer(base=array, offset=0), UNKNOWN)


def _element(vm: VMState, region: Address) -> TypedValue:
    element = _fresh(vm, constants.OBJ_ADDR_PREFIX)
    vm.heap_set(
        element,
        HeapObject(
            fields={
                FieldName("region"): typed(region.value, UNKNOWN),
                FieldName("offset"): typed(0, UNKNOWN),
                FieldName("omitted"): typed(False, UNKNOWN),
            }
        ),
    )
    return typed(Pointer(base=element, offset=0), UNKNOWN)


def _fresh(vm: VMState, prefix: str) -> Address:
    counter = vm.symbolic_counter
    vm.symbolic_counter = counter + 1
    return Address(f"{prefix}{counter}")
