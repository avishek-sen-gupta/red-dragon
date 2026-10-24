# pyright: standard
"""The job-step PARM, a run input: its halfword length and EBCDIC text in a 100-byte area; irreducible, since it reads outside the program."""

from collections.abc import Mapping, Sequence

from interpreter.encoding.ebcdic_table import EbcdicTable
from interpreter.func_name import FuncName
from interpreter.hlasm.hlasm_constants import (
    JOB_PARM_BUILTIN,
    PARM_LENGTH_BYTES,
    PARM_TEXT_BYTES,
)
from interpreter.hlasm.parm_too_long import ParmTooLong
from interpreter.types.typed_value import TypedValue
from interpreter.vm.builtin import Builtin
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult

NO_PARM = ""


def job_parm_builtins(parm: str) -> Mapping[FuncName, Builtin]:
    if len(parm) > PARM_TEXT_BYTES:
        raise ParmTooLong(parm)
    text = EbcdicTable.ascii_to_ebcdic(parm.encode("ascii"))
    image = [
        *len(text).to_bytes(PARM_LENGTH_BYTES, "big"),
        *text.ljust(PARM_TEXT_BYTES, b"\0"),
    ]

    def job_parm(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        return BuiltinResult(value=list(image))

    return {JOB_PARM_BUILTIN: job_parm}
