# pyright: standard
"""Translate programs leave the same declared storage, registers and CC in RedDragon and in z390, bar z390's TRE length 0, its alignment check on the TROO table and its TRTE two-byte argument truncated to its low byte."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import translate_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")

ALL_CASES: Mapping[str, tuple[programs.Case, HlasmRun]] = {
    **{name: (case, ABENDED) for name, case in programs.CASES.items()},
    **{
        name: (case, SPECIFICATION)
        for name, case in programs.SPECIFICATION_EXCEPTIONS.items()
    },
}

Z390_MACHINE: Mapping[str, HlasmMachine] = {
    "TRE length 0": HlasmMachine(
        ABENDED, 0, {3: HIGH_FILL | 0xFFFFFFFF, 6: HIGH_FILL | 0x01010240}
    ),
    "TRTE two-byte arguments and functions over 255": HlasmMachine(
        ABENDED, 1, {3: HIGH_FILL | 2, 4: HIGH_FILL | 0x4321}
    ),
    "TROO table bits 61-63 ignored": HlasmMachine(
        SPECIFICATION, 0, {3: HIGH_FILL | 4, 6: FILL}
    ),
}

MATCHING = [name for name in ALL_CASES if name not in Z390_MACHINE]


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", MATCHING)
def test_translate_matches(z390: Z390Runner, tmp_path: Path, case: str):
    (body, results, cc), run = ALL_CASES[case]
    source = programs.translate_program(body)

    expected = HlasmMachine(run, cc, results)
    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(Z390_MACHINE))
def test_translate_follows_the_principles_of_operation_where_z390_does_not(
    z390: Z390Runner, tmp_path: Path, case: str
):
    (body, results, cc), run = ALL_CASES[case]
    source = programs.translate_program(body)
    z390_machine = Z390_MACHINE[case]

    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(z390_machine.gprs),
    ) == (HlasmMachine(run, cc, results), z390_machine)
