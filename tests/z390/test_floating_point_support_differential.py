# pyright: standard
"""Floating-point-support programs leave the same declared registers, CC and abend in RedDragon and in z390, bar z390's initial FPC, its short loads clearing bits 32-63, its sign forms through an HFP value, its unchecked register pairs and FPC values, and its LFAS and SFASR without signaling; those expectations come from the Principles of Operation."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import floating_point_support_programs as programs
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

FILL = storage.FILL
HIGH_FILL = storage.HIGH_FILL
Z390_INITIAL_FPC = 0x70000000
Z390_COMPLETED_PAST_THE_CHECK = {2: HIGH_FILL | 1}


def _z390(abend: str, registers: Mapping[int, int]) -> HlasmMachine:
    return HlasmMachine(
        HlasmRun(return_code=0, abend=abend, stdout=""), programs.PRESET_CC, registers
    )


Z390_PINNED: Mapping[str, HlasmMachine] = {
    "LE LEY LER": _z390(
        programs.COMPLETED,
        {2: 0x80000001_00000000, 3: 0x7FFF7FFE_00000000, 4: 0x80000001_00000000},
    ),
    "LXR invalid pair": _z390(programs.COMPLETED, Z390_COMPLETED_PAST_THE_CHECK),
    "LCDFR LNDFR LPDFR": _z390(programs.DATA_EXCEPTION, {r: FILL for r in range(2, 8)}),
    "CPSDR": _z390(programs.DATA_EXCEPTION, {r: FILL for r in range(2, 5)}),
    "LCDFR unnormalised": _z390(programs.COMPLETED, {2: 0x81234567_89ABCCEF}),
    "EFPC initial": _z390(programs.COMPLETED, {2: HIGH_FILL | Z390_INITIAL_FPC}),
    "SFASR no trap": _z390(programs.COMPLETED, {8: HIGH_FILL | 0x00040003}),
    "LFAS no trap": _z390(programs.COMPLETED, {8: HIGH_FILL | 0x04041201}),
    **{
        case: _z390(programs.COMPLETED, Z390_COMPLETED_PAST_THE_CHECK)
        for case in programs.CHECKED
        if case != "SRNMB mode 5"
    },
}
AGREED = [case for case in programs.CASES if case not in Z390_PINNED]


def _both(
    z390: Z390Runner, tmp_path: Path, case: str
) -> tuple[HlasmMachine, HlasmMachine]:
    body, registers = programs.CASES[case][:2]
    source = storage.based_program(body, storage.ABEND)
    return (
        run_hlasm_machine(source).restricted_to(registers),
        z390.run_machine(source, tmp_path).restricted_to(registers),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", AGREED)
def test_case_matches(z390: Z390Runner, tmp_path: Path, case: str):
    assert _both(z390, tmp_path, case) == (
        programs.expected(case),
        programs.expected(case),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(Z390_PINNED))
def test_case_follows_the_principles_of_operation_where_z390_differs(
    z390: Z390Runner, tmp_path: Path, case: str
):
    assert _both(z390, tmp_path, case) == (
        programs.expected(case),
        Z390_PINNED[case],
    )
