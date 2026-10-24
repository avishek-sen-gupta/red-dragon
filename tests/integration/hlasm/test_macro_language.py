# pyright: standard
"""Macro-language programs assembled by che4z and run on the VM leave the values IBM's HLASM Language Reference gives."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import macro_language_programs as programs
from tests.integration.hlasm.hlasm_helpers import HlasmRun, run_hlasm, run_hlasm_machine


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.USING_PROGRAMS))
def test_using_resolves_dsect_labeled_dependent_and_literal_addresses(case: str):
    source, registers = programs.USING_PROGRAMS[case]
    machine = run_hlasm_machine(source)

    assert (machine.run.abend, programs.low_words(machine, registers)) == (
        programs.COMPLETED,
        registers,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.STDOUT_PROGRAMS))
def test_macro_program_prints_the_reference_values(case: str):
    source, stdout = programs.STDOUT_PROGRAMS[case]

    assert run_hlasm(source) == HlasmRun(0, "", stdout)
