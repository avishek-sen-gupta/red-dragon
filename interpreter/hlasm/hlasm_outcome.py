# pyright: standard
"""An HLASM run's outcome, read off the finished VM: R15's low word and the abend the run ended in."""

from collections.abc import Callable, Mapping

from infrastructure.zos.abend.system_abend import SystemAbend
from infrastructure.zos.abend.user_abend import UserAbend
from interpreter.hlasm.hlasm_constants import (
    ABEND_VAR,
    GPR_BYTES,
    GPRS_VAR,
    LOW_WORD_OFFSET,
    RETURN_CODE_REGISTER,
    SYSTEM_ABEND_PREFIX,
    USER_ABEND_PREFIX,
    WORD_BYTES,
)
from interpreter.vm.vm_types import VMState

_HEX = 16
_DECIMAL = 10
_BY_PREFIX: Mapping[str, Callable[[str], SystemAbend | UserAbend]] = {
    SYSTEM_ABEND_PREFIX: lambda digits: SystemAbend(int(digits, _HEX)),
    USER_ABEND_PREFIX: lambda digits: UserAbend(int(digits, _DECIMAL)),
}
_RETURN_CODE_OFFSET = GPR_BYTES * RETURN_CODE_REGISTER + LOW_WORD_OFFSET


def hlasm_return_code(vm: VMState) -> int:
    base = vm.call_stack[0].local_vars[GPRS_VAR].value
    loaded = vm.load(int(base) + _RETURN_CODE_OFFSET, WORD_BYTES)
    if not isinstance(loaded, list):
        raise TypeError(f"R15 loaded as {loaded!r}")
    return int.from_bytes(bytes(loaded), "big")


def hlasm_abend(vm: VMState) -> tuple[SystemAbend | UserAbend, ...]:
    linked = vm.call_stack[0].local_vars
    return _parsed(str(linked[ABEND_VAR].value)) if ABEND_VAR in linked else ()


def _parsed(text: str) -> tuple[SystemAbend | UserAbend, ...]:
    return (_BY_PREFIX[text[0]](text[1:]),) if text else ()
