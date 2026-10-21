# pyright: standard
"""Compile an HLASM source through the unit-file pipeline and run it to its end."""

import io
from contextlib import redirect_stdout
from dataclasses import dataclass

from hlasm_asg.hlasm_bridge_parser import make_hlasm_parser
from interpreter.project.hlasm_compile import compile_hlasm
from interpreter.project.program_entry import ProgramEntry
from interpreter.run import initial_vm_state, run_linked
from interpreter.var_name import VarName
from interpreter.vm.builtins import core_builtins
from interpreter.vm.vm_types import VMState

MAX_STEPS = 20_000
GPR_BYTES = 8
LOW_WORD_OFFSET = 4
WORD_BYTES = 4
RETURN_CODE_REGISTER = 15
NO_RETURN_CODE = 0


@dataclass(frozen=True)
class HlasmRun:
    """What a standalone run left: R15 on return, the abend code, the console."""

    return_code: int
    abend: str
    stdout: str


def _var(vm: VMState, name: str) -> int | str:
    return vm.call_stack[0].local_vars[VarName(name)].value


def _low_word(vm: VMState, register: int) -> int:
    at = int(_var(vm, "__hlasm_gprs")) + GPR_BYTES * register + LOW_WORD_OFFSET
    loaded = vm.load(at, WORD_BYTES)
    assert isinstance(loaded, list)
    return int.from_bytes(bytes(loaded), "big")


def _return_code(vm: VMState, abend: str) -> int:
    match abend:
        case "":
            return _low_word(vm, RETURN_CODE_REGISTER)
        case _:
            return NO_RETURN_CODE


def run_hlasm(source: str) -> HlasmRun:
    linked = compile_hlasm(source.encode("utf-8"), parser=make_hlasm_parser())
    (entry,) = linked.programs
    console = io.StringIO()
    with redirect_stdout(console):
        vm = run_linked(
            linked,
            ProgramEntry(entry),
            max_steps=MAX_STEPS,
            initial_vm=initial_vm_state(),
            builtins=core_builtins(),
        )
    return hlasm_run_of(vm, console.getvalue())


def hlasm_run_of(vm: VMState, stdout: str) -> HlasmRun:
    abend = str(_var(vm, "__hlasm_abend"))
    return HlasmRun(_return_code(vm, abend), abend, stdout)
