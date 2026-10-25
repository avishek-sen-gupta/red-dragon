# pyright: standard
"""The user abend a COBOL program raised through LE's CEE3ABD: the code its stub left in storage."""

from __future__ import annotations

from pathlib import Path

from infrastructure.zos.abend.user_abend import UserAbend
from interpreter.address import Address
from interpreter.cobol.program_object import WORKING_STORAGE_FIELD, program_var
from interpreter.vm.vm_types import Pointer, VMState

LE_STUBS = Path(__file__).parent / "le_stubs"

_SINGLETON = program_var("CEE3ABD")
_WORKING_STORAGE = WORKING_STORAGE_FIELD
_CODE_BYTES = 4
_NOT_CALLED = -1


def user_abend(vm: VMState) -> tuple[UserAbend, ...]:
    linked = vm.call_stack[0].local_vars
    if _SINGLETON not in linked:
        return ()
    match linked[_SINGLETON].value:
        case Pointer() as singleton:
            return _recorded(vm, singleton)
        case other:
            raise TypeError(f"CEE3ABD's program object is {other!r}")


def _recorded(vm: VMState, singleton: Pointer) -> tuple[UserAbend, ...]:
    handle = vm.heap_get(singleton.base).fields[_WORKING_STORAGE].value
    match vm.region_get(Address(str(handle))):
        case bytearray() as storage:
            return _code(
                int.from_bytes(bytes(storage[:_CODE_BYTES]), "big", signed=True)
            )
        case None:
            raise LookupError("CEE3ABD's WORKING-STORAGE is not in the finished VM")


def _code(code: int) -> tuple[UserAbend, ...]:
    return () if code == _NOT_CALLED else (UserAbend(code),)
