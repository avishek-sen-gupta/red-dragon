# pyright: standard
"""Macro-language programs assembled by che4z and run on the VM leave the values IBM's HLASM Language Reference gives; where the manual is silent (which statements an expansion numbers for &SYSSTMT) they follow che4z."""

import logging
from pathlib import Path

import pytest

from hlasm_asg.assembly_input import AssemblyInput
from hlasm_asg.hlasm_parse_error import HlasmParseError
from interpreter.hlasm.features import HlasmFeature
from interpreter.project.hlasm_compile import HLASM_FRONTEND_LOGGER
from interpreter.project.hlasm_compile_options import HlasmCompileOptions
from tests.covers import covers
from tests.integration.hlasm import macro_language_programs as programs
from tests.integration.hlasm.fixed_assembly_clock import FixedAssemblyClock
from tests.integration.hlasm.hlasm_helpers import HlasmRun, run_hlasm, run_hlasm_machine


@covers(HlasmFeature.USING)
@pytest.mark.parametrize("case", list(programs.USING_PROGRAMS))
def test_using_resolves_dsect_labeled_dependent_and_literal_addresses(case: str):
    source, registers = programs.USING_PROGRAMS[case]
    machine = run_hlasm_machine(source)

    assert (machine.run.abend, programs.low_words(machine, registers)) == (
        programs.COMPLETED,
        registers,
    )


@covers(
    HlasmFeature.MACRO_DEFINITION,
    HlasmFeature.CONDITIONAL_ASSEMBLY,
    HlasmFeature.SET_SYMBOLS,
    HlasmFeature.MACRO_PARAMETERS,
    HlasmFeature.OPCODE_SUBSTITUTION,
    HlasmFeature.AREAD_AINSERT,
    HlasmFeature.COPY,
    HlasmFeature.DATA_ATTRIBUTES,
    HlasmFeature.SYSTEM_VARIABLES,
)
@pytest.mark.parametrize("case", list(programs.STDOUT_PROGRAMS))
def test_macro_program_prints_the_reference_values(tmp_path: Path, case: str):
    source, stdout = programs.STDOUT_PROGRAMS[case]
    syslib = programs.library_in(tmp_path / "lib", ".mac")

    assert run_hlasm(source, syslib=[syslib]) == HlasmRun(0, "", stdout)


@covers(HlasmFeature.SYSTEM_VARIABLES)
@pytest.mark.parametrize("sysparm", list(programs.SYSPARM_PRINTS))
def test_sysparm_is_what_the_assembly_was_given(sysparm: str):
    options = HlasmCompileOptions({AssemblyInput.SYSPARM: sysparm})

    assert run_hlasm(programs.SYSPARM_PROGRAM, options) == HlasmRun(
        0, "", programs.SYSPARM_PRINTS[sysparm]
    )


@covers(HlasmFeature.SYSTEM_VARIABLES)
def test_date_and_time_come_from_the_injected_assembly_clock():
    options = HlasmCompileOptions(clock=FixedAssemblyClock(programs.CLOCK))

    assert run_hlasm(programs.CLOCK_PROGRAM, options) == HlasmRun(
        0, "", programs.CLOCK_PRINTS
    )


@covers(HlasmFeature.MNOTE)
def test_an_mnote_from_a_macro_reaches_the_log(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger=HLASM_FRONTEND_LOGGER)

    ran = run_hlasm(programs.MNOTE_PROGRAM)

    assert (ran, [(r.levelno, r.getMessage()) for r in caplog.records]) == (
        HlasmRun(0, "", ""),
        list(programs.MNOTE_LOG),
    )


@covers(HlasmFeature.CONDITIONAL_ASSEMBLY)
def test_a_branch_count_past_actr_refuses_the_assembly():
    with pytest.raises(HlasmParseError) as refused:
        run_hlasm(programs.ACTR_PROGRAM)

    assert [
        (d.code, d.line, d.message) for d in refused.value.diagnostics
    ] == programs.ACTR_REFUSAL
