# pyright: standard
"""Images of several HLASM modules: a V-constant reaches a later module's ENTRY and its data, the first unit is entered at its own END though another module ends at the same label and two are private code alone, the job step hands the program its PARM, a linking branch to an unresolved EXTRN calls it by name, a CSECT named in two units is refused, and run() hands the job step an empty PARM."""

import logging
from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.frontends import get_hlasm_parser
from interpreter.handlers.calls import UnresolvedProgramError
from interpreter.hlasm_run_inputs.job_parm_builtins import NO_PARM, job_parm_builtins
from interpreter.project.duplicate_program_in_image import DuplicateProgramInImage
from interpreter.project.entry_point import EntryPoint
from interpreter.project.hlasm_compile import (
    HLASM_FRONTEND_LOGGER,
    compile_hlasm,
    link_hlasm_units,
    lower_hlasm_program,
)
from interpreter.project.source_file import SourceFile
from interpreter.project.types import LinkedProgram
from interpreter.run import initial_vm_state, run, run_linked
from interpreter.var_name import VarName
from interpreter.vm.builtins import compose_builtins, core_builtins
from interpreter.vm.vm_types import SymbolicValue, VMState
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import MAX_STEPS, gpr, hlasm_run_of
from tests.integration.hlasm.hlasm_run import HlasmRun

CALLER = b"""\
MAIN     CSECT
         USING MAIN,15
LAB      L     2,=V(BDATA)
         L     15,0(,2)
         BR    14
         END   LAB
"""
CALLEE = b"""\
BMOD     CSECT
         ENTRY BDATA
LAB      DC    F'1'
BDATA    DC    F'42'
         END   LAB
"""
PRIVATE = b"""\
         LA    15,3
         BR    14
         END
"""
PARM_READER = b"""\
MAIN     CSECT
         LR    12,15
         USING MAIN,12
         L     3,0(,1)
         LH    15,0(,3)
         MVC   TEXT,2(3)
         BR    14
TEXT     DS    CL5
         END   MAIN
"""
CALLS_MISSING = b"""\
MAIN     CSECT
         LR    12,15
         USING MAIN,12
         LR    11,14
         L     15,=V(MISSING)
         BALR  14,15
         LR    2,15
         LR    14,11
         LA    15,7
         BR    14
         END   MAIN
"""
LOW_WORD = 0xFFFFFFFF


def _run(linked: LinkedProgram, parm: str = NO_PARM, permit: bool = True) -> VMState:
    return run_linked(
        linked,
        EntryPoint.function(lambda ref: ref.label == linked.entry_func_label),
        max_steps=MAX_STEPS,
        initial_vm=initial_vm_state(),
        builtins=compose_builtins(core_builtins(), job_parm_builtins(parm)),
        permit_unresolved_call_targets=permit,
    )


def _var(vm: VMState, name: str) -> int:
    return int(vm.call_stack[0].local_vars[VarName(name)].value)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_v_constant_reaches_a_later_module_and_the_first_unit_is_entered_at_its_end(
    tmp_path: Path,
):
    parser = get_hlasm_parser()
    units = (
        *lower_hlasm_program(
            SourceFile(Path("A.asm"), CALLER), parser=parser, work_dir=tmp_path
        ),
        *lower_hlasm_program(
            SourceFile(Path("B.asm"), CALLEE), parser=parser, work_dir=tmp_path
        ),
        *lower_hlasm_program(
            SourceFile(Path("C.asm"), PRIVATE), parser=parser, work_dir=tmp_path
        ),
        *lower_hlasm_program(
            SourceFile(Path("D.asm"), PRIVATE), parser=parser, work_dir=tmp_path
        ),
    )
    linked = link_hlasm_units(units, tmp_path)
    vm = _run(linked)
    main, callee = _var(vm, "__hlasm_sect_A.MAIN"), _var(vm, "__hlasm_sect_B.BMOD")

    assert sorted(linked.programs) == ["BDATA", "BMOD", "MAIN"]
    assert hlasm_run_of(vm, "") == HlasmRun(return_code=42, abend="", stdout="")
    assert (gpr(vm, 2) & LOW_WORD, main % 8, callee % 8) == (callee + 4, 0, 0)


def _parm_seen(parm: str) -> tuple[HlasmRun, int, int, bytes]:
    vm = _run(compile_hlasm(PARM_READER, parser=get_hlasm_parser()), parm)
    text = vm.load(_var(vm, "__hlasm_sect___main__.MAIN") + 18, 5)
    assert isinstance(text, list)
    list_word = vm.load(gpr(vm, 1) & LOW_WORD, 4)
    assert isinstance(list_word, list)
    area = int.from_bytes(bytes(list_word), "big")
    return hlasm_run_of(vm, ""), area >> 31, area & 0x7FFFFFFF, bytes(text)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_job_step_hands_the_program_its_parm_or_an_empty_one():
    supplied = _parm_seen("HELLO")
    empty = _parm_seen(NO_PARM)

    assert supplied[:2] + supplied[3:] == (
        HlasmRun(return_code=5, abend="", stdout=""),
        1,
        bytes([0xC8, 0xC5, 0xD3, 0xD3, 0xD6]),
    )
    assert empty[:2] + empty[3:] == (
        HlasmRun(return_code=0, abend="", stdout=""),
        1,
        bytes(5),
    )
    assert supplied[2] % 4 == 0


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_linking_branch_to_an_unresolved_extrn_calls_it_by_name(
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.WARNING, logger=HLASM_FRONTEND_LOGGER)
    linked = compile_hlasm(CALLS_MISSING, parser=get_hlasm_parser())
    permitted = _run(linked)
    gprs = _var(permitted, "__hlasm_gprs")

    with pytest.raises(UnresolvedProgramError) as refused:
        _run(linked, permit=False)

    assert [r.getMessage() for r in caplog.records] == [
        "__main__.asm:5: EXTRN MISSING is not in the image; calls reach it by name"
    ]
    assert hlasm_run_of(permitted, "") == HlasmRun(return_code=7, abend="", stdout="")
    assert type(permitted.load(gprs + 2 * 8, 8)) is SymbolicValue
    assert str(refused.value) == (
        "CALL to __entry_MISSING, but nothing in this run unit is registered under it"
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_csect_in_two_units_is_refused_naming_both():
    twice = b"BMOD     CSECT\n         BR    14\n         END\n"

    with pytest.raises(DuplicateProgramInImage) as refused:
        compile_hlasm(
            CALLEE,
            parser=get_hlasm_parser(),
            programs=(SourceFile(Path("TWICE.asm"), twice),),
        )

    assert str(refused.value) == (
        "program BMOD is in the image twice: __main__.asm and TWICE.asm"
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_run_hands_the_job_step_an_empty_parm():
    vm = run(PARM_READER.decode("ascii"), language=Language.HLASM, max_steps=MAX_STEPS)
    text = vm.load(_var(vm, "__hlasm_sect___main__.MAIN") + 18, 5)

    assert (hlasm_run_of(vm, ""), text) == (
        HlasmRun(return_code=0, abend="", stdout=""),
        [0] * 5,
    )
