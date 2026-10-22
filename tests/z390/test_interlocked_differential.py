# pyright: standard
"""Interlocked-update programs leave the same declared registers and CC in RedDragon and in z390, bar what z390 does not do: it does not execute CAL, CALGF, CALG or CSST, checks no boundary for CS, CSG, CDSG, LPD, LPDG, LPQ and STPQ, and sets LAAL's CC from a stale operand; those expectations come from the Principles of Operation."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import interlocked_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.test_interlocked import expected_run
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390


def _z390(abend: str, cc: int, gprs: Mapping[int, int]) -> HlasmMachine:
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, gprs)


Z390_DIFFERS: Mapping[str, HlasmMachine] = {
    "CAL equal": _z390("S0C1", 0, {4: 0xA5A5A5A500000005}),
    "CAL unequal": _z390("S0C1", 0, {4: 0xA5A5A5A500000007}),
    "CAL unequal leaves a misaligned second operand unread": _z390(
        "S0C1", 0, {4: 0xA5A5A5A500000007}
    ),
    "CAL equal off a word": _z390("S0C1", 0, {4: 0xA5A5A5A500000005}),
    "CAL first operand off a word": _z390("S0C1", 0, {4: 0xA5A5A5A500000007}),
    "CALGF equal": _z390("S0C1", 0, {4: 0xA5A5A5A500000005}),
    "CALGF unequal": _z390("S0C1", 0, {4: 0xA5A5A5A500000007}),
    "CALGF equal off a doubleword": _z390("S0C1", 0, {4: 0xA5A5A5A500000005}),
    "CALG equal": _z390("S0C1", 0, {4: 0x0123456789ABCDEF}),
    "CALG unequal": _z390("S0C1", 0, {4: 0xFEDCBA9876543210}),
    "CSST word, store characteristic 0": _z390(
        "S0C1",
        0,
        {
            4: 0xA5A5A5A500000005,
            6: 0xA5A5A5A5A5A5A5A5,
            8: 0xA5A5A5A5A5A5A5A5,
            9: 0xA5A5A5A5A5A5A5A5,
        },
    ),
    "CSST word, store characteristic 1": _z390(
        "S0C1",
        0,
        {
            4: 0xA5A5A5A500000005,
            6: 0xA5A5A5A5A5A5A5A5,
            8: 0xA5A5A5A5A5A5A5A5,
            9: 0xA5A5A5A5A5A5A5A5,
        },
    ),
    "CSST word, store characteristic 2": _z390(
        "S0C1",
        0,
        {
            4: 0xA5A5A5A500000005,
            6: 0xA5A5A5A5A5A5A5A5,
            8: 0xA5A5A5A5A5A5A5A5,
            9: 0xA5A5A5A5A5A5A5A5,
        },
    ),
    "CSST word, store characteristic 3": _z390(
        "S0C1",
        0,
        {
            4: 0xA5A5A5A500000005,
            6: 0xA5A5A5A5A5A5A5A5,
            8: 0xA5A5A5A5A5A5A5A5,
            9: 0xA5A5A5A5A5A5A5A5,
        },
    ),
    "CSST word, store characteristic 4": _z390(
        "S0C1",
        0,
        {
            4: 0xA5A5A5A500000005,
            6: 0xA5A5A5A5A5A5A5A5,
            8: 0xA5A5A5A5A5A5A5A5,
            9: 0xA5A5A5A5A5A5A5A5,
        },
    ),
    "CSST doubleword": _z390(
        "S0C1",
        0,
        {
            4: 0x0123456789ABCDEF,
            6: 0xA5A5A5A5A5A5A5A5,
            8: 0xA5A5A5A5A5A5A5A5,
            9: 0xA5A5A5A5A5A5A5A5,
        },
    ),
    "CSST quadword": _z390(
        "S0C1",
        0,
        {
            6: 0xA5A5A5A5A5A5A5A5,
            7: 0xA5A5A5A5A5A5A5A5,
            8: 0xA5A5A5A5A5A5A5A5,
            9: 0xA5A5A5A5A5A5A5A5,
        },
    ),
    "CSST word unequal": _z390(
        "S0C1",
        0,
        {
            4: 0xA5A5A5A500000007,
            6: 0xA5A5A5A5A5A5A5A5,
            8: 0xA5A5A5A5A5A5A5A5,
            9: 0xA5A5A5A5A5A5A5A5,
        },
    ),
    "CSST doubleword unequal": _z390(
        "S0C5", 0, {4: 0xFEDCBA9876543210, 6: 0xA5A5A5A5A5A5A5A5, 8: 0xA5A5A5A5A5A5A5A5}
    ),
    "CSST quadword unequal": _z390(
        "S0C1",
        0,
        {
            4: 0x0123456789ABCDEF,
            5: 0x0000000000000000,
            6: 0xA5A5A5A5A5A5A5A5,
            7: 0xA5A5A5A5A5A5A5A5,
            8: 0xA5A5A5A5A5A5A5A5,
        },
    ),
    "CSST function code 3": _z390("S0C1", 0, {4: 0xA5A5A5A500000005}),
    "CSST store characteristic 5": _z390("S0C1", 0, {4: 0xA5A5A5A500000005}),
    "CSST doubleword off its boundary": _z390("S0C1", 0, {4: 0x0123456789ABCDEF}),
    "CSST store off its boundary": _z390("S0C1", 0, {4: 0xA5A5A5A500000007}),
    "CSST quadword with an odd register": _z390("S0C1", 0, {5: 0xA5A5A5A5A5A5A5A5}),
    "CS off a word": _z390("U0001", 1, {4: 0xA5A5A5A500050000}),
    "CSG off a doubleword": _z390("U0001", 1, {4: 0x0000000A7FFFFFFF}),
    "CDSG off a quadword": _z390("U0001", 1, {4: 0xFEDCBA9876543210}),
    "LPD off a word": _z390("U0001", 0, {4: 0xA5A5A5A500000005, 5: 0xA5A5A5A5000A7FFF}),
    "LPDG off a doubleword": _z390(
        "U0001", 0, {4: 0x0000000A7FFFFFFF, 5: 0x0123456789ABCDEF}
    ),
    "LPQ off a quadword": _z390(
        "U0001", 0, {4: 0xFEDCBA9876543210, 5: 0x7FFFFFFFFFFFFFFF}
    ),
    "STPQ off a quadword": _z390(
        "U0001", 0, {4: 0xA5A5A5A5A5A5A5A5, 5: 0xA5A5A5A5A5A5A5A5}
    ),
    "LAAL carry": _z390("U0001", 3, {4: 0xA5A5A5A5FFFFFFFF, 6: 0xA5A5A5A500000000}),
}
AGREED = [case for case in programs.CASES if case not in Z390_DIFFERS]


def _both(
    z390: Z390Runner, tmp_path: Path, case: str
) -> tuple[HlasmMachine, HlasmMachine]:
    body, results, _ = programs.CASES[case]
    source = programs.interlocked_program(body)
    return (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    )


def _expected(case: str) -> HlasmMachine:
    _, results, cc = programs.CASES[case]
    return HlasmMachine(expected_run(case), cc, results)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", AGREED)
def test_case_matches(z390: Z390Runner, tmp_path: Path, case: str):
    assert _both(z390, tmp_path, case) == (_expected(case), _expected(case))


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(Z390_DIFFERS))
def test_follows_the_principles_of_operation_where_z390_differs(
    z390: Z390Runner, tmp_path: Path, case: str
):
    assert _both(z390, tmp_path, case) == (_expected(case), Z390_DIFFERS[case])
