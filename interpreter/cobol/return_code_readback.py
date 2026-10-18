"""Read the run unit's RETURN-CODE back from a finished VMState.

Every program exit and every STOP RUN writes the ending program's RETURN-CODE into
the run-unit region, so the value there is the one the last program to end left:
the value the operating system receives (red-dragon-cvwu). Kept out of the lowering
modules so their import chain stays clear of ``interpreter.vm``.
"""

from __future__ import annotations

from interpreter.address import Address
from interpreter.cobol.run_unit import (
    RUN_UNIT_LAYOUT,
    RUN_UNIT_RETURN_CODE,
    RUN_UNIT_VAR,
)
from interpreter.cobol.symbolic_return_code_error import SymbolicReturnCodeError
from interpreter.vm.vm_types import SymbolicValue, VMState


def run_unit_address(vm: VMState) -> Address:
    """The run unit region's handle, from the variable the start-up code declared."""
    return Address(str(vm.call_stack[0].local_vars[RUN_UNIT_VAR].value))


def run_unit_region(vm: VMState) -> bytearray:
    """The run unit's region, found through the variable the start-up code declared."""
    address = run_unit_address(vm)
    match vm.region_get(address):
        case bytearray() as region:
            return region
        case _:
            raise LookupError(f"{RUN_UNIT_VAR} names {address}, which is not a region")


def read_return_code(vm: VMState) -> int:
    """The run unit's RETURN-CODE: what the last program to end wrote into the
    run-unit region. Read through the symbolic overlay, so a symbolic value is
    reported rather than the bytes it masks."""
    fl = RUN_UNIT_LAYOUT.lookup_or_raise(RUN_UNIT_RETURN_CODE)
    base = vm.segment_of(run_unit_address(vm)).base
    match vm.load(base + fl.offset, fl.byte_length):
        case SymbolicValue() as symbolic:
            raise SymbolicReturnCodeError(symbolic)
        case list() as raw:
            return int.from_bytes(bytes(raw), "big", signed=True)
