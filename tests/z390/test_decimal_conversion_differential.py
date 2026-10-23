# pyright: standard
"""Decimal conversion programs leave the same declared registers, CC and abend in RedDragon and in z390, bar z390's known errors: CVB suppresses an out-of-range result the Principles of Operation complete into the low word, CVDY stores a stale value, and PKU and UNPKU abend S0C1, so their expected values come from the Principles of Operation alone."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import decimal_conversion_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

OPERATION = HlasmRun(return_code=0, abend="S0C1", stdout="")


def _z390_operation_exception(cc: int, results: int) -> HlasmMachine:
    return HlasmMachine(
        OPERATION,
        cc,
        {programs.FIRST + k: programs.FILLED for k in range(results)},
    )


def _z390_suppressed_cvb() -> HlasmMachine:
    return HlasmMachine(
        programs.FIXED_POINT_DIVIDE,
        programs.CC_SET_BY_LTR,
        {programs.RESULT: programs.FILLED},
    )


Z390_MACHINE: Mapping[str, HlasmMachine] = {
    "CVB too large stores the low word": _z390_suppressed_cvb(),
    "CVB too negative stores the low word": _z390_suppressed_cvb(),
    "CVBY 15 digits stores the low word": _z390_suppressed_cvb(),
    "CVDY most negative": HlasmMachine(
        programs.ABENDED, programs.CC_SET_BY_LTR, {programs.FIRST: 0xC}
    ),
    "PKU": _z390_operation_exception(programs.CC_SET_BY_LTR, 2),
    "PKU ignores the leftmost 12 bits": _z390_operation_exception(
        programs.CC_SET_BY_LTR, 2
    ),
    "PKU 32 characters ignores the leftmost": _z390_operation_exception(
        programs.CC_SET_BY_LTR, 2
    ),
    "EX of PKU sets the second length": _z390_operation_exception(
        programs.CC_SET_BY_LTR, 2
    ),
    "PKU second operand over 64 bytes": _z390_operation_exception(
        programs.CC_SET_BY_LTR, 0
    ),
    "PKU odd second-operand length": _z390_operation_exception(
        programs.CC_SET_BY_LTR, 0
    ),
    "UNPKU": _z390_operation_exception(programs.CC_SET_BY_LTR, 1),
    "UNPKU negative": _z390_operation_exception(0, 1),
    "UNPKU invalid sign sets CC 3": _z390_operation_exception(
        programs.CC_SET_BY_LTR, 1
    ),
    "UNPKU 64 bytes puts a zero leftmost": _z390_operation_exception(
        programs.CC_SET_BY_LTR, 8
    ),
    "EX of UNPKU sets the first length": _z390_operation_exception(
        programs.CC_SET_BY_LTR, 1
    ),
    "UNPKU first operand over 64 bytes": _z390_operation_exception(
        programs.CC_SET_BY_LTR, 0
    ),
    "UNPKU odd first-operand length": _z390_operation_exception(
        programs.CC_SET_BY_LTR, 0
    ),
}

MATCHING = [name for name in programs.ALL_CASES if name not in Z390_MACHINE]


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", MATCHING)
def test_decimal_conversion_matches(z390: Z390Runner, tmp_path: Path, case: str):
    (body, results, cc), run = programs.ALL_CASES[case]
    source = programs.conversion_program(body)

    expected = HlasmMachine(run, cc, results)
    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(Z390_MACHINE))
def test_decimal_conversion_follows_the_principles_of_operation_where_z390_does_not(
    z390: Z390Runner, tmp_path: Path, case: str
):
    (body, results, cc), run = programs.ALL_CASES[case]
    source = programs.conversion_program(body)
    z390_machine = Z390_MACHINE[case]

    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(z390_machine.gprs),
    ) == (HlasmMachine(run, cc, results), z390_machine)
