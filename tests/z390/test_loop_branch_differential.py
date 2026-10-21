# pyright: standard
"""Branch on count and branch on index programs leave the same path, registers and CC in RedDragon and in z390, except where z390 reads R2 or the compare value after writing R1."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import loop_branch_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
ADDRESSING = HlasmRun(return_code=0, abend="S0C5", stdout="")

Z390_AFTER_WRITE: Mapping[str, HlasmMachine] = {
    "BCTR 5,5": HlasmMachine(
        ADDRESSING, programs.PRESET_CC, {programs.PATH_REGISTER: FILL}
    ),
    "BXH 7,6 compares the original R7": HlasmMachine(
        ABENDED,
        programs.PRESET_CC,
        {programs.PATH_REGISTER: programs.FELL_THROUGH, 7: HIGH_FILL | 6},
    ),
    "BXHG 7,6 compares the original R7": HlasmMachine(
        ABENDED,
        programs.PRESET_CC,
        {programs.PATH_REGISTER: programs.FELL_THROUGH, 7: 6},
    ),
}

MATCHING = [case for case in programs.CASES if case not in Z390_AFTER_WRITE]


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", MATCHING)
def test_loop_branch_case_matches(z390: Z390Runner, tmp_path: Path, case: str):
    code, registers = programs.CASES[case]
    source = programs.program(code)
    expected = HlasmMachine(ABENDED, programs.PRESET_CC, registers)

    assert (
        run_hlasm_machine(source).restricted_to(registers),
        z390.run_machine(source, tmp_path).restricted_to(registers),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(Z390_AFTER_WRITE))
def test_z390_reads_operands_after_writing_r1(
    z390: Z390Runner, tmp_path: Path, case: str
):
    code, registers = programs.CASES[case]
    source = programs.program(code)

    assert (
        run_hlasm_machine(source).restricted_to(registers),
        z390.run_machine(source, tmp_path).restricted_to(registers),
    ) == (
        HlasmMachine(ABENDED, programs.PRESET_CC, registers),
        Z390_AFTER_WRITE[case],
    )
