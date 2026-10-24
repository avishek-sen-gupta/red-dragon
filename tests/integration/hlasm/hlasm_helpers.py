# pyright: standard
"""Compile an HLASM source through the unit-file pipeline and run it to its end."""

import io
from collections.abc import Sequence
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path

from hlasm_asg.assembly_inputs import AssemblyInputs
from interpreter.field_name import FieldName
from interpreter.frontends import get_hlasm_parser
from interpreter.hlasm.bfp_builtins import bfp_builtins
from interpreter.hlasm.clock_builtins import clock_builtins
from interpreter.hlasm.dfp_builtins import dfp_builtins
from interpreter.hlasm.hfp_builtins import hfp_builtins
from interpreter.hlasm.job_parm_builtins import NO_PARM, job_parm_builtins
from interpreter.hlasm.pfpo_builtins import pfpo_builtins
from interpreter.project.hlasm_compile import compile_hlasm
from interpreter.project.hlasm_compile_options import HlasmCompileOptions
from interpreter.project.program_entry import ProgramEntry
from interpreter.run import initial_vm_state, run_linked
from interpreter.var_name import VarName
from interpreter.vm.builtins import compose_builtins, core_builtins
from interpreter.vm.vm_types import Pointer, VMState
from tests.integration.hlasm.fixed_machine_clock import FixedMachineClock
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

MAX_STEPS = 20_000
MAIN_PATH = Path("__main__.asm")
JOB_STEP_ARGUMENTS = 1
GPR_BYTES = 8
LOW_WORD_OFFSET = 4
WORD_BYTES = 4
DOUBLEWORD_BYTES = 8
VECTOR_REGISTER_BYTES = 16
GPR_COUNT = 16
RETURN_CODE_REGISTER = 15
NO_RETURN_CODE = 0
NO_INPUTS = HlasmCompileOptions()
BARE_ASSEMBLY = AssemblyInputs({}, datetime(2026, 1, 1, tzinfo=UTC))


def _var_value(vm: VMState, name: str) -> Pointer | int | str:
    return vm.call_stack[0].local_vars[VarName(name)].value


def _var(vm: VMState, name: str) -> int | str:
    return vm.call_stack[0].local_vars[VarName(name)].value


def _gpr_bytes(vm: VMState, offset: int, width: int) -> int:
    loaded = vm.load(int(_var(vm, "__hlasm_gprs")) + offset, width)
    assert isinstance(loaded, list)
    return int.from_bytes(bytes(loaded), "big")


def gpr(vm: VMState, register: int) -> int:
    return _gpr_bytes(vm, GPR_BYTES * register, GPR_BYTES)


def _low_word(vm: VMState, register: int) -> int:
    return _gpr_bytes(vm, GPR_BYTES * register + LOW_WORD_OFFSET, WORD_BYTES)


def _return_code(vm: VMState, abend: str) -> int:
    match abend:
        case "":
            return _low_word(vm, RETURN_CODE_REGISTER)
        case _:
            return NO_RETURN_CODE


def _run_vm(
    source: str,
    options: HlasmCompileOptions = NO_INPUTS,
    syslib: Sequence[Path] = (),
) -> tuple[VMState, str]:
    linked = compile_hlasm(
        source.encode("utf-8"), parser=get_hlasm_parser(syslib), options=options
    )
    entry = linked.modules[MAIN_PATH].program
    console = io.StringIO()
    with redirect_stdout(console):
        vm = run_linked(
            linked,
            ProgramEntry(entry),
            max_steps=MAX_STEPS,
            initial_vm=initial_vm_state(),
            builtins=compose_builtins(
                core_builtins(),
                clock_builtins(FixedMachineClock()),
                bfp_builtins(),
                hfp_builtins(),
                dfp_builtins(),
                pfpo_builtins(),
                job_parm_builtins(NO_PARM),
            ),
        )
    return vm, console.getvalue()


def run_hlasm(
    source: str,
    options: HlasmCompileOptions = NO_INPUTS,
    syslib: Sequence[Path] = (),
) -> HlasmRun:
    return hlasm_run_of(*_run_vm(source, options, syslib))


def _entry(vm: VMState, entry: Pointer) -> tuple[int, int]:
    fields = vm.heap_get(entry.base).fields
    return (
        int(fields[FieldName("length")].value),
        int(fields[FieldName("subpool")].value),
    )


def run_hlasm_allocations(
    source: str,
) -> tuple[HlasmRun, list[tuple[int, int]], int]:
    vm, stdout = _run_vm(source)
    table = _var_value(vm, "__hlasm_allocations")
    assert isinstance(table, Pointer)
    pointers = [tv.value for tv in vm.heap_get(table.base).fields.values()]
    entries = sorted(_entry(vm, p) for p in pointers if isinstance(p, Pointer))
    others = len(vm.heap_items()) - 1 - len(entries) - JOB_STEP_ARGUMENTS
    return hlasm_run_of(vm, stdout), entries, others


def _machine(vm: VMState, stdout: str) -> HlasmMachine:
    return HlasmMachine(
        hlasm_run_of(vm, stdout),
        int(_var(vm, "__hlasm_cc")),
        {r: _gpr_bytes(vm, GPR_BYTES * r, GPR_BYTES) for r in range(GPR_COUNT)},
    )


def run_hlasm_machine(source: str) -> HlasmMachine:
    return _machine(*_run_vm(source))


def run_hlasm_storage(
    source: str, section: str, span: tuple[int, int]
) -> tuple[HlasmMachine, bytes]:
    vm, stdout = _run_vm(source)
    start, end = span
    loaded = vm.load(
        int(_var(vm, f"__hlasm_sect___main__.{section}")) + start, end - start
    )
    assert isinstance(loaded, list)
    return _machine(vm, stdout), bytes(loaded)


def hlasm_run_of(vm: VMState, stdout: str) -> HlasmRun:
    abend = str(_var(vm, "__hlasm_abend"))
    return HlasmRun(_return_code(vm, abend), abend, stdout)


def run_hlasm_fpc(source: str) -> tuple[HlasmMachine, int]:
    vm, stdout = _run_vm(source)
    return _machine(vm, stdout), int(_var(vm, "__hlasm_fpc"))


def _fpr(vm: VMState, register: int) -> int:
    loaded = vm.load(
        int(_var(vm, "__hlasm_vrs")) + VECTOR_REGISTER_BYTES * register,
        DOUBLEWORD_BYTES,
    )
    assert isinstance(loaded, list)
    return int.from_bytes(bytes(loaded), "big")


def run_hlasm_float(source: str) -> tuple[HlasmMachine, dict[int, int], int]:
    vm, stdout = _run_vm(source)
    fprs = {r: _fpr(vm, r) for r in range(GPR_COUNT)}
    return _machine(vm, stdout), fprs, int(_var(vm, "__hlasm_fpc"))
