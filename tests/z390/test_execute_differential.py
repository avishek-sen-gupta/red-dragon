# pyright: standard
"""EX and EXRL programs run the same modified target, link after the execute instruction and leave the same CC in RedDragon and in z390; z390 misses the odd-target check, links an executed BRAS after the BRAS, sets CC 1 for ALSI with a carry (as without EX), and runs the targets RedDragon cannot resolve."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import execute_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

BRAS_PAST_NEXT = 40
Z390_DIFFERENCES = {
    "EX odd target": HlasmMachine(programs.OPERATION, programs.PRESET_CC, {}),
    "ALSI negative immediate from a register": HlasmMachine(
        programs.ABENDED,
        1,
        {
            programs.MOVED_REGISTER: 0xFFFFFF7FFFFFFFFF,
            programs.PATH_REGISTER: programs.FELL_THROUGH,
        },
    ),
    "EXRL BRAS links after the EXRL": HlasmMachine(
        programs.ABENDED,
        programs.PRESET_CC,
        {
            programs.LINK_REGISTER: programs.AMODE_31_LINK + BRAS_PAST_NEXT,
            programs.PATH_REGISTER: programs.BRANCHED,
        },
    ),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize(
    "case", [c for c in programs.CASES if c not in Z390_DIFFERENCES]
)
def test_execute_case_matches(z390: Z390Runner, tmp_path: Path, case: str):
    code, run, cc, registers = programs.CASES[case]
    source = programs.program(code)
    expected = HlasmMachine(run, cc, registers)

    assert (
        programs.view(run_hlasm_machine(source), registers),
        programs.view(z390.run_machine(source, tmp_path), registers),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(Z390_DIFFERENCES))
def test_z390_differs_on_the_odd_target_bras_link_and_alsi_cc(
    z390: Z390Runner, tmp_path: Path, case: str
):
    code, run, cc, registers = programs.CASES[case]
    source = programs.program(code)

    assert (
        programs.view(run_hlasm_machine(source), registers),
        programs.view(z390.run_machine(source, tmp_path), registers),
    ) == (HlasmMachine(run, cc, registers), Z390_DIFFERENCES[case])


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize(
    "case",
    [programs.INDEXED_TARGET, programs.MODIFIED_OPCODE],
    ids=["indexed", "opcode"],
)
def test_z390_runs_the_targets_reddragon_abends_on(
    z390: Z390Runner, tmp_path: Path, case: programs.ExecuteCase
):
    code, run, cc, registers = case
    source = programs.program(code)

    assert (
        programs.view(run_hlasm_machine(source), {}),
        programs.view(z390.run_machine(source, tmp_path), registers),
    ) == (HlasmMachine(programs.OPERATION, cc, {}), HlasmMachine(run, cc, registers))
