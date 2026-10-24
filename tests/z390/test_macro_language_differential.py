# pyright: standard
"""Macro-language programs leave the same results in RedDragon and in z390, bar the attributes z390 gets wrong: S' and I' of symbols defined later, I' always, and T' of a literal already used in an instruction (red-dragon-6uyp.74); those are pinned as z390 prints them."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import macro_language_programs as programs
from tests.integration.hlasm.hlasm_helpers import HlasmRun, run_hlasm, run_hlasm_machine
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.USING_PROGRAMS))
def test_using_programs_match(z390: Z390Runner, tmp_path: Path, case: str):
    source, registers = programs.USING_PROGRAMS[case]
    ours = run_hlasm_machine(source)
    theirs = z390.run_machine(source, tmp_path)

    assert (
        (ours.run.abend, programs.low_words(ours, registers)),
        (theirs.run.abend, programs.low_words(theirs, registers)),
    ) == ((programs.COMPLETED, registers), (programs.COMPLETED, registers))


AGREED = [c for c in programs.STDOUT_PROGRAMS if c not in programs.Z390_STDOUT]


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", AGREED)
def test_macro_programs_match(z390: Z390Runner, tmp_path: Path, case: str):
    source, stdout = programs.STDOUT_PROGRAMS[case]
    expected = HlasmRun(0, "", stdout)

    assert (run_hlasm(source), z390.run(source, tmp_path)) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.Z390_STDOUT))
def test_z390_follows_its_own_attribute_values(
    z390: Z390Runner, tmp_path: Path, case: str
):
    source, stdout = programs.STDOUT_PROGRAMS[case]

    assert (run_hlasm(source), z390.run(source, tmp_path)) == (
        HlasmRun(0, "", stdout),
        HlasmRun(0, "", programs.Z390_STDOUT[case]),
    )
