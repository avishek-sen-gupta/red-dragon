# pyright: standard
"""CALL, LINK, LOAD and DELETE: CALL builds the parameter list (inline, MF=L and MF=E, VL marking the last word) and calls through a V-constant or a register; LOAD answers the entry with the AMODE 31 bit and the length in doublewords; LINK calls by name (through R15's list) and leaves the registers as the program left them, and a branch to the system's return address inside it ends the LINK; DELETE succeeds only for a loaded name; a missing name is a dynamic call for LINK, an 806 abend for LOAD, or LOAD's ERRET when R1's high bit asks; bad operands refuse the assembly."""

import pytest

from hlasm_asg.hlasm_parse_error import HlasmParseError
from hlasm_asg.program.mnote_level import MnoteLevel
from interpreter.frontends import get_hlasm_parser
from interpreter.handlers.calls import UnresolvedProgramError
from interpreter.hlasm_run_inputs.job_parm_builtins import NO_PARM, job_parm_builtins
from interpreter.project.entry_point import EntryPoint
from interpreter.project.hlasm_compile import compile_hlasm
from interpreter.run import initial_vm_state, run_linked
from interpreter.vm.builtins import compose_builtins, core_builtins
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import program_service_programs as programs
from tests.integration.hlasm.far_branch_programs import module
from tests.integration.hlasm.hlasm_helpers import (
    MAX_STEPS,
    run_hlasm,
    run_hlasm_machine,
)
from tests.integration.hlasm.hlasm_run import HlasmRun

LOW_WORD = 0xFFFFFFFF
VL_SHIFT = 31


def _words(main: str, name: str, callee: str) -> tuple[HlasmRun, dict[int, int]]:
    machine = run_hlasm_machine(main, (module(name, callee),))
    return machine.run, {r: v & LOW_WORD for r, v in machine.gprs.items()}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_call_passes_inline_and_execute_form_lists_marking_the_last_word():
    run, words = _words(programs.CALLER, "SUB", programs.ADDER)

    assert (
        run,
        words[2],
        words[5] >> VL_SHIFT,
        words[6] >> VL_SHIFT,
        words[7] >> VL_SHIFT,
    ) == (
        HlasmRun(return_code=180, abend="", stdout=""),
        100,
        0,
        1,
        1,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_load_answers_entry_and_length_then_call_15_reaches_it_and_delete_releases_only_what_was_loaded():
    run, words = _words(programs.LOADER, "SUB", programs.RETURNS_23)

    assert (run, words[7], words[8], words[9], words[4], words[5]) == (
        HlasmRun(return_code=4, abend="", stdout=""),
        0x80000000,
        1,
        23,
        0,
        4,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_link_calls_by_name_with_a_vl_list_and_leaves_the_registers_the_program_left():
    run, words = _words(programs.LINKER, "SUB", programs.CLOBBERS)
    forms, _ = _words(programs.LINK_FORMS, "SUB", programs.RETURNS_23)
    lowercase = _words(programs.LINKS_IN_LOWERCASE, "SUB", programs.RETURNS_23)[0]
    exited = _words(programs.LINKS_THEN_EXITS, "B", programs.CALLS_BACK_AND_EXITS)[0]

    assert (run, words[7], words[9] >> VL_SHIFT, forms, lowercase, exited) == (
        HlasmRun(return_code=142, abend="", stdout=""),
        99,
        1,
        HlasmRun(return_code=69, abend="", stdout=""),
        HlasmRun(return_code=23, abend="", stdout=""),
        HlasmRun(return_code=7, abend="", stdout=""),
    )


def _refused_link(permit: bool) -> str:
    linked = compile_hlasm(
        programs.LINKS_MISSING.encode("ascii"), parser=get_hlasm_parser()
    )
    with pytest.raises(UnresolvedProgramError) as refused:
        run_linked(
            linked,
            EntryPoint.function(lambda ref: ref.label == linked.entry_func_label),
            max_steps=MAX_STEPS,
            initial_vm=initial_vm_state(),
            builtins=compose_builtins(core_builtins(), job_parm_builtins(NO_PARM)),
            permit_unresolved_call_targets=permit,
        )
    return str(refused.value)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_missing_name_is_called_as_a_dynamic_call_or_abends_806_or_takes_erret():
    exited = run_hlasm_machine(programs.LOADS_MISSING_WITH_EXIT)
    refused = (
        "CALL resolved at run time to __entry_NOPE, but nothing in this run unit"
        " is registered under it"
    )

    assert (
        _refused_link(permit=True),
        _refused_link(permit=False),
        run_hlasm(programs.LOADS_MISSING),
        run_hlasm(programs.LOADS_MISSING_BY_HAND),
        exited.run,
        exited.gprs[2] & LOW_WORD,
        exited.gprs[3] & LOW_WORD,
    ) == (
        refused,
        refused,
        HlasmRun(return_code=0, abend="S806", stdout=""),
        HlasmRun(return_code=0, abend="S806", stdout=""),
        HlasmRun(return_code=9, abend="", stdout=""),
        0x00806000,
        4,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bad_service_operands_refuse_the_assembly_with_severity_8():
    with pytest.raises(HlasmParseError) as refused:
        run_hlasm(programs.BAD_OPERANDS)

    assert [
        (d.message, d.related[-1].line, d.mnote) for d in refused.value.diagnostics
    ] == [
        (m, line, MnoteLevel(kind="LEVEL", level=8))
        for m, line in programs.BAD_OPERAND_REFUSALS
    ]
