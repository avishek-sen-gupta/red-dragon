# pyright: standard
"""Storage move programs leave the same declared registers, storage and CC in RedDragon and in z390, bar z390's known MVN, MVZ, MVCLU and MVST errors; z390 lacks MVCRL, whose values come from the Principles of Operation in the VM test."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import ss_move_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")
OPERATION = HlasmRun(return_code=0, abend="S0C1", stdout="")

ALL_CASES: Mapping[str, tuple[programs.Case, HlasmRun]] = {
    **{name: (case, ABENDED) for name, case in programs.CASES.items()},
    **{
        name: (case, SPECIFICATION)
        for name, case in programs.SPECIFICATION_EXCEPTIONS.items()
    },
}

Z390_MACHINE: Mapping[str, HlasmMachine] = {
    "MVN propagates": HlasmMachine(ABENDED, 0, {7: 0x35F5FFFF_FFFFFFFF}),
    "MVZ propagates": HlasmMachine(ABENDED, 0, {7: 0x3C3FFFFF_FFFFFFFF}),
    "MVCLU": HlasmMachine(OPERATION, 0, {3: HIGH_FILL | 8, 5: HIGH_FILL | 2, 7: FILL}),
    "MVCLU registers": HlasmMachine(OPERATION, 0, {}),
    "MVCLU lengths equal": HlasmMachine(
        OPERATION, 0, {3: HIGH_FILL | 4, 5: HIGH_FILL | 4, 7: FILL}
    ),
    "MVCLU odd length": HlasmMachine(
        OPERATION, 0, {3: HIGH_FILL | 7, 5: HIGH_FILL | 2}
    ),
    "MVST reserved GR0 bits": HlasmMachine(ABENDED, 1, {}),
}

MATCHING = [
    name
    for name in ALL_CASES
    if name not in Z390_MACHINE and name not in programs.RIGHT_TO_LEFT
]


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", MATCHING)
def test_move_matches(z390: Z390Runner, tmp_path: Path, case: str):
    (body, results, cc), run = ALL_CASES[case]
    source = programs.move_program(body)

    expected = HlasmMachine(run, cc, results)
    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(Z390_MACHINE))
def test_move_follows_the_principles_of_operation_where_z390_does_not(
    z390: Z390Runner, tmp_path: Path, case: str
):
    (body, results, cc), run = ALL_CASES[case]
    source = programs.move_program(body)
    z390_machine = Z390_MACHINE[case]

    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(z390_machine.gprs),
    ) == (HlasmMachine(run, cc, results), z390_machine)
