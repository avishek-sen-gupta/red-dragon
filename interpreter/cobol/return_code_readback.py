# pyright: standard
"""Read RETURN-CODE back from a finished VMState (red-dragon-o8uq).

Kept separate from ``special_registers`` (which the lowering pipeline imports) so the
``interpreter.vm`` dependency this needs does not leak into the COBOL/project import
chain. This is the consumer-facing handle for jackal v2: given the VMState a COBOL
program returned, recover its RETURN-CODE.
"""

from __future__ import annotations

from interpreter.address import Address
from interpreter.cobol.binary import decode_binary
from interpreter.cobol.special_registers import (
    RETURN_CODE_HANDLE,
    RETURN_CODE_NAME,
    SPECIAL_REGISTERS_LAYOUT,
)
from interpreter.vm.vm_types import VMState


def read_return_code(vm: VMState) -> int:
    """Return the run unit's RETURN-CODE from a finished VMState.

    The run unit's value is the one left by the LAST program to end, because that
    is the value the operating system receives: a GOBACK chain copies each
    callee's code up until the entry program ends holding it, and a STOP RUN
    inside a subprogram ends the run unit there, with that subprogram's code
    (red-dragon-cvwu). Every program exit and every STOP RUN publishes it, so
    reading it is just reading what was published last.

    Falls back to scanning the heap when nothing was published, which is how a
    VMState assembled by hand — rather than by running COBOL — still answers.
    That scan cannot tell one program's register from another's and returns
    whichever comes first in link order, so it is a last resort, not the rule.
    """
    published = vm.cobol_run_unit_return_code
    if published is not None:
        return published

    field_layout = SPECIAL_REGISTERS_LAYOUT.lookup_or_raise(RETURN_CODE_NAME)
    region = _return_code_region(vm)
    raw = region[field_layout.offset : field_layout.offset + field_layout.byte_length]
    descriptor = field_layout.type_descriptor
    return int(decode_binary(bytes(raw), descriptor.decimal_digits, descriptor.signed))


def _return_code_region(vm: VMState) -> bytearray:
    """Return the SR region bytes via the singleton's ``return_code_handle``."""
    for _addr, obj in vm.heap_items():
        handle = obj.fields.get(RETURN_CODE_HANDLE)
        if handle is not None:
            region = vm.region_get(Address(str(handle.value)))
            if region is not None:
                return region
    raise KeyError("No RETURN-CODE region found in VMState")
