# pyright: standard
"""Macro-language programs leave the same results in RedDragon and in z390, bar where they differ: z390 gives S' of a symbol defined later and every I' as 0, T' of every literal as U and D' as 0, leaves &SYSSEQF empty, numbers &SYSSTMT by open-code lines, and cannot parse an attribute of a literal in a macro body. Those are pinned as z390 gives them (red-dragon-6uyp.74). The assembly clock cannot be given to z390, so &SYSDATC and &SYSTIME are VM tests only; z390 writes MNOTEs to its listing, not the run log, so MNOTE is too."""

from pathlib import Path

import pytest

from hlasm_asg.assembly_input import AssemblyInput
from hlasm_asg.hlasm_parse_error import HlasmParseError
from interpreter.hlasm.features import HlasmFeature
from interpreter.project.hlasm_compile_options import HlasmCompileOptions
from tests.covers import covers
from tests.integration.hlasm import macro_language_programs as programs
from tests.integration.hlasm.hlasm_helpers import HlasmRun, run_hlasm, run_hlasm_machine
from tests.z390.z390_assembly_failed import Z390AssemblyFailed
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390


@covers(HlasmFeature.USING)
@pytest.mark.parametrize("case", list(programs.USING_PROGRAMS))
def test_using_programs_match(z390: Z390Runner, tmp_path: Path, case: str):
    source, registers = programs.USING_PROGRAMS[case]
    ours = run_hlasm_machine(source)
    theirs = z390.run_machine(source, tmp_path)

    assert (
        (ours.run.abend, programs.low_words(ours, registers)),
        (theirs.run.abend, programs.low_words(theirs, registers)),
    ) == ((programs.COMPLETED, registers), (programs.COMPLETED, registers))


AGREED = [
    c
    for c in programs.STDOUT_PROGRAMS
    if c not in programs.Z390_STDOUT and c not in programs.Z390_REFUSES
]


def _libraries(tmp_path: Path) -> Path:
    programs.library_in(tmp_path, ".CPY")
    programs.library_in(tmp_path, ".MAC")
    return programs.library_in(tmp_path / "lib", ".mac")


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
@pytest.mark.parametrize("case", AGREED)
def test_macro_programs_match(z390: Z390Runner, tmp_path: Path, case: str):
    source, stdout = programs.STDOUT_PROGRAMS[case]
    syslib = _libraries(tmp_path)
    expected = HlasmRun(0, "", stdout)

    assert (
        run_hlasm(source, syslib=[syslib]),
        z390.run(source, tmp_path),
    ) == (expected, expected)


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
@pytest.mark.parametrize("case", list(programs.Z390_STDOUT))
def test_z390_follows_its_own_values(z390: Z390Runner, tmp_path: Path, case: str):
    source, stdout = programs.STDOUT_PROGRAMS[case]
    syslib = _libraries(tmp_path)

    assert (run_hlasm(source, syslib=[syslib]), z390.run(source, tmp_path)) == (
        HlasmRun(0, "", stdout),
        HlasmRun(0, "", programs.Z390_STDOUT[case]),
    )


@covers(HlasmFeature.SYSTEM_VARIABLES)
@pytest.mark.parametrize("sysparm", list(programs.SYSPARM_PRINTS))
def test_sysparm_matches(z390: Z390Runner, tmp_path: Path, sysparm: str):
    options = HlasmCompileOptions({AssemblyInput.SYSPARM: sysparm})
    expected = HlasmRun(0, "", programs.SYSPARM_PRINTS[sysparm])

    assert (
        run_hlasm(programs.SYSPARM_PROGRAM, options),
        z390.run(programs.SYSPARM_PROGRAM, tmp_path, [f"SYSPARM({sysparm})"]),
    ) == (expected, expected)


@covers(HlasmFeature.CONDITIONAL_ASSEMBLY)
def test_a_branch_count_past_actr_refuses_in_both(z390: Z390Runner, tmp_path: Path):
    with pytest.raises(HlasmParseError) as ours:
        run_hlasm(programs.ACTR_PROGRAM)
    with pytest.raises(Z390AssemblyFailed):
        z390.run(programs.ACTR_PROGRAM, tmp_path)

    assert [
        (d.code, d.line, d.message) for d in ours.value.diagnostics
    ] == programs.ACTR_REFUSAL


@covers(HlasmFeature.DATA_ATTRIBUTES)
@pytest.mark.parametrize("case", sorted(programs.Z390_REFUSES))
def test_z390_refuses_what_it_cannot_parse(z390: Z390Runner, tmp_path: Path, case: str):
    source, stdout = programs.STDOUT_PROGRAMS[case]

    assert run_hlasm(source) == HlasmRun(0, "", stdout)
    with pytest.raises(Z390AssemblyFailed):
        z390.run(source, tmp_path)
