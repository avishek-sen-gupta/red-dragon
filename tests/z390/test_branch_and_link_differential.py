# pyright: standard
"""Branch and link programs save the same link relative to the next instruction, take the same path and leave the same CC in RedDragon and in z390; z390 also leaves AMODE 31, which RedDragon abends on."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import branch_and_link_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import FILL
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
OPERATION = HlasmRun(return_code=0, abend="S0C1", stdout="")


def _mode(run: HlasmRun, cc: int, taken: bool, mode_register: int) -> HlasmMachine:
    return HlasmMachine(
        run,
        cc,
        {
            programs.PATH_REGISTER: programs.path(taken),
            programs.MODE_REGISTER: mode_register,
        },
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.LINK_CASES))
def test_link_case_matches(z390: Z390Runner, tmp_path: Path, case: str):
    code, taken = programs.LINK_CASES[case]
    source = programs.program(code)
    expected = HlasmMachine(
        ABENDED,
        programs.PRESET_CC,
        {
            programs.PATH_REGISTER: programs.path(taken),
            programs.LINK_REGISTER: programs.AMODE_31_LINK,
        },
    )

    assert (
        programs.link_view(run_hlasm_machine(source)),
        programs.link_view(z390.run_machine(source, tmp_path)),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.MODE_CASES))
def test_mode_case_matches(z390: Z390Runner, tmp_path: Path, case: str):
    code, taken, cc, mode_register = programs.MODE_CASES[case]
    source = programs.program(code)
    expected = _mode(ABENDED, cc, taken, mode_register)

    assert (
        run_hlasm_machine(source).restricted_to(programs.MODE_VIEW),
        z390.run_machine(source, tmp_path).restricted_to(programs.MODE_VIEW),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.MODE_SWITCH_CASES))
def test_z390_leaves_amode_31_where_reddragon_abends(
    z390: Z390Runner, tmp_path: Path, case: str
):
    code, taken, cc, mode_register = programs.MODE_SWITCH_CASES[case]
    source = programs.program(code)

    assert (
        run_hlasm_machine(source).restricted_to(programs.MODE_VIEW),
        z390.run_machine(source, tmp_path).restricted_to(programs.MODE_VIEW),
    ) == (
        HlasmMachine(
            OPERATION,
            programs.PRESET_CC,
            {programs.PATH_REGISTER: FILL, programs.MODE_REGISTER: FILL},
        ),
        _mode(ABENDED, cc, taken, mode_register),
    )
