# pyright: standard
"""Miscellaneous programs leave the same declared registers, CC and abend in RedDragon and in z390, bar the instructions z390 does not execute, its unchecked boundaries, its STFLE and clock CCs, its initial access registers and its LAE, which leaves the access register; those expectations come from the Principles of Operation."""

from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import miscellaneous_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

FILL = programs.FILL
HIGH_FILL = programs.HIGH_FILL
ONES = programs.ONES
Z390_INITIAL_ACCESS_REGISTER = 0xF4F4F4F4
Z390_FACILITY_WORD = 0xE1000DC0_00000000


def _z390(abend: str, cc: int, registers: Mapping[int, int]) -> HlasmMachine:
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)


def _filled(*registers: int) -> Mapping[int, int]:
    return {r: FILL for r in registers}


Z390_PINNED: Mapping[str, HlasmMachine] = {
    "EPSW": _z390("S0C1", 2, _filled(2, 3)),
    "EPSW after SPM": _z390("S0C1", 1, {0: 5, 4: FILL, 5: FILL}),
    "SAR CPYA EAR": _z390(
        "U0001",
        2,
        {4: HIGH_FILL | 0x12345678, 5: HIGH_FILL | Z390_INITIAL_ACCESS_REGISTER},
    ),
    "LAE LAEY clear the access register": _z390(
        "U0001",
        0,
        {
            2: HIGH_FILL,
            3: HIGH_FILL,
            6: HIGH_FILL | 0x12345678,
            7: HIGH_FILL | 0x12345678,
        },
    ),
    "LAM off a word": _z390("U0001", 2, {2: HIGH_FILL}),
    "STAM off a word": _z390("U0001", 2, {2: HIGH_FILL}),
    "CKSM tail and carry": _z390("S0C1", 0, {2: FILL, 5: HIGH_FILL | 7, 7: FILL}),
    "CKSM whole words": _z390("S0C1", 0, {2: HIGH_FILL, 5: HIGH_FILL | 8}),
    "CKSM zero length": _z390("S0C1", 2, {2: FILL, 5: HIGH_FILL}),
    "ECAG": _z390("S0C1", 2, _filled(*range(2, 12))),
    "ECAG sizes and ways": _z390("S0C1", 2, _filled(*range(2, 11))),
    "LCBB short": _z390("S0C1", 0, _filled(2, 3, 4)),
    "LCBB sixteen": _z390("S0C1", 0, _filled(3, 4)),
    "ECTG": _z390("S0C5", 2, {0: 7, 1: 9}),
    "STFLE short": _z390("U0001", 0, {2: 0, 3: Z390_FACILITY_WORD, 4: ONES}),
    "STFLE complete": _z390(
        "U0001", 0, {2: 0x1FF, 3: Z390_FACILITY_WORD, 4: ONES, 5: ONES}
    ),
    "STFLE exact": _z390("U0001", 0, {2: 1, 3: Z390_FACILITY_WORD, 4: ONES, 5: ONES}),
    "STFLE off a doubleword": _z390(
        "U0001", 0, {0: 1, 2: 0xFFFFFFFF_00000000 | (Z390_FACILITY_WORD >> 32)}
    ),
    "MC": _z390("S0C1", 2, {2: FILL}),
    "EX MC class 15": _z390("S0C1", 2, {}),
    "EX MC class over 15": _z390("S0C1", 2, {}),
    "MC class over 15": _z390("S0C1", 2, {}),
}
STCKE_PROGRAMMABLE_BITS = 16
CLOCK_RELATIONS: Mapping[str, tuple[int, int]] = {
    "STCK unique": (1, 1),
    "STCKF": (0, 0),
    "STCKE": ((programs.EXTENDED_CLOCK & ONES) >> STCKE_PROGRAMMABLE_BITS, 0),
    "STCKE twice": (2 << STCKE_PROGRAMMABLE_BITS, 0),
    "STCK after STCKE": (1, 0),
}
Z390_CLOCK_CC = {
    "STCK unique": 2,
    "STCKF": 0,
    "STCKE": 2,
    "STCKE twice": 2,
    "STCK after STCKE": 2,
}
CLOCK_REGISTERS = {2: 0, 3: 0, 4: 0, 5: 0}
STCKE_CLOCK_SHIFT = 8
STCKE_LOW_CLOCK_SHIFT = 56
AGREED = [
    case
    for case in programs.CASES
    if case not in Z390_PINNED and case not in CLOCK_RELATIONS
]


def _both(
    z390: Z390Runner, tmp_path: Path, case: str, registers: Mapping[int, int]
) -> tuple[HlasmMachine, HlasmMachine]:
    source = programs.program(programs.CASES[case][0])
    return (
        run_hlasm_machine(source).restricted_to(registers),
        z390.run_machine(source, tmp_path).restricted_to(registers),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", AGREED)
def test_case_matches(z390: Z390Runner, tmp_path: Path, case: str):
    registers = programs.CASES[case][1]

    assert _both(z390, tmp_path, case, registers) == (
        programs.expected(case),
        programs.expected(case),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(Z390_PINNED))
def test_principles_of_operation_result_where_z390_differs(
    z390: Z390Runner, tmp_path: Path, case: str
):
    ours, theirs = programs.expected(case), Z390_PINNED[case]
    source = programs.program(programs.CASES[case][0])

    assert (
        run_hlasm_machine(source).restricted_to(ours.gprs),
        z390.run_machine(source, tmp_path).restricted_to(theirs.gprs),
    ) == (ours, theirs)


def _quadword(machine: HlasmMachine, r: int) -> int:
    return (machine.gprs[r] << 64) | machine.gprs[r + 1]


def _stcke_clock(machine: HlasmMachine) -> int:
    return (machine.gprs[2] << STCKE_CLOCK_SHIFT) | (
        machine.gprs[3] >> STCKE_LOW_CLOCK_SHIFT
    )


CLOCK_RELATION_OF: Mapping[str, Callable[[HlasmMachine], int]] = {
    "STCK unique": lambda m: m.gprs[3] - m.gprs[2],
    "STCKF": lambda m: m.gprs[3] - m.gprs[2],
    "STCKE": lambda m: m.gprs[3] >> STCKE_PROGRAMMABLE_BITS,
    "STCKE twice": lambda m: _quadword(m, 4) - _quadword(m, 2),
    "STCK after STCKE": lambda m: m.gprs[4] - _stcke_clock(m),
}


def _clock_relation(case: str, machine: HlasmMachine) -> int:
    return CLOCK_RELATION_OF[case](machine)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(CLOCK_RELATIONS))
def test_clocks_set_cc_zero_and_keep_order_where_z390_does_neither_for_stcke(
    z390: Z390Runner, tmp_path: Path, case: str
):
    ours, theirs = _both(z390, tmp_path, case, CLOCK_REGISTERS)

    assert (
        (ours.run, ours.cc, _clock_relation(case, ours)),
        (theirs.run, theirs.cc, _clock_relation(case, theirs)),
    ) == (
        (programs.expected(case).run, 0, CLOCK_RELATIONS[case][0]),
        (programs.expected(case).run, Z390_CLOCK_CC[case], CLOCK_RELATIONS[case][1]),
    )
