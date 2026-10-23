# pyright: standard
"""Packed-decimal arithmetic programs leave the same declared registers, CC and abend in RedDragon and in z390, bar z390's known decimal errors: SRP rounds a negative toward zero and ignores a bad rounding digit, MP and DP lose a negative zero, and the CC at an S0CA is 0."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import packed_arithmetic_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

Z390_OVERFLOW = HlasmMachine(programs.DECIMAL_OVERFLOW, 0, {})

Z390_MACHINE: Mapping[str, HlasmMachine] = {
    "SRP rounds the magnitude of a negative": HlasmMachine(
        programs.ABENDED, 1, {programs.RESULT: 0x1234D}
    ),
    "SRP invalid rounding digit": HlasmMachine(programs.ABENDED, 2, {}),
    "EX of SRP with an invalid rounding digit": HlasmMachine(programs.ABENDED, 2, {}),
    "MP negative zero": HlasmMachine(programs.ABENDED, 1, {programs.RESULT: 0xC}),
    "DP zero remainder keeps the dividend sign": HlasmMachine(
        programs.ABENDED, 1, {programs.RESULT: 0x2D000C}
    ),
    "DP zero quotient keeps the algebraic sign": HlasmMachine(
        programs.ABENDED, 1, {programs.RESULT: 0xC005D}
    ),
    "AP overflow": Z390_OVERFLOW,
    "SP overflow": Z390_OVERFLOW,
    "ZAP overflow": Z390_OVERFLOW,
    "SRP overflow": Z390_OVERFLOW,
}

MATCHING = [name for name in programs.ALL_CASES if name not in Z390_MACHINE]


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", MATCHING)
def test_packed_arithmetic_matches(z390: Z390Runner, tmp_path: Path, case: str):
    (body, results, cc), run = programs.ALL_CASES[case]
    source = programs.packed_program(body)

    expected = HlasmMachine(run, cc, results)
    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(Z390_MACHINE))
def test_packed_arithmetic_follows_the_principles_of_operation_where_z390_does_not(
    z390: Z390Runner, tmp_path: Path, case: str
):
    (body, results, cc), run = programs.ALL_CASES[case]
    source = programs.packed_program(body)
    z390_machine = Z390_MACHINE[case]

    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(z390_machine.gprs),
    ) == (HlasmMachine(run, cc, results), z390_machine)
