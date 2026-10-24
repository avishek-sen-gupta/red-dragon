# pyright: standard
"""The job-step PARM, a run input: its halfword length and EBCDIC text in a 100-byte area; irreducible, since it reads outside the program."""

from collections.abc import Mapping, Sequence

from interpreter.encoding.ebcdic_table import EbcdicTable
from interpreter.func_name import FuncName
from interpreter.hlasm_run_inputs.parm_not_encodable import ParmNotEncodable
from interpreter.hlasm_run_inputs.parm_too_long import ParmTooLong
from interpreter.hlasm_run_inputs.run_input_names import (
    JOB_PARM_BUILTIN,
    PARM_LENGTH_BYTES,
    PARM_TEXT_BYTES,
)
from interpreter.types.typed_value import TypedValue
from interpreter.vm.builtin import Builtin
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult

NO_PARM = ""


def _ebcdic(character: str) -> int:
    code = ord(character)
    if code >= len(EbcdicTable.ASCII_TO_EBCDIC):
        raise ParmNotEncodable(character)
    return EbcdicTable.ASCII_TO_EBCDIC[code]


def job_parm_builtins(parm: str) -> Mapping[FuncName, Builtin]:
    if len(parm) > PARM_TEXT_BYTES:
        raise ParmTooLong(parm)
    text = bytes(map(_ebcdic, parm))
    image = [
        *len(text).to_bytes(PARM_LENGTH_BYTES, "big"),
        *text.ljust(PARM_TEXT_BYTES, b"\0"),
    ]

    def job_parm(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        return BuiltinResult(value=list(image))

    return {JOB_PARM_BUILTIN: job_parm}
