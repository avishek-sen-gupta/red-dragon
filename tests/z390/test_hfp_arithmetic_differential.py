# pyright: standard
"""HFP arithmetic programs leave the same declared registers, CC and abend in RedDragon and in z390, bar z390's faults below; those expectations come from the Principles of Operation (chapter 18 and the HFP exceptions on page 6-29). z390 writes X'F4F4F4F4' into bits 32-63 of some short results; rounds or computes in host floating point where HFP truncates with one guard digit (SDR, SWR, SW, MD, MXDR, MSE, SQD); ignores the guard digit in unnormalized subtraction and in COMPARE; drops the sign of MY, MYH and MYL; makes a zero MY product a true zero; rejects MAY with R1 = 6 and garbles MAYH and MAYL; makes LTDR and LCDR of a zero fraction a true zero and LTXR, LNXR of a signed zero positive; stores a nonzero value where a masked underflow gives a true zero; and abends S0C7 for the square root of a negative."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import hfp_arithmetic_programs as programs
from tests.integration.hlasm.bfp_arithmetic_programs import high_word
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

Z390_LOW = 0xF4F4F4F4
COMPLETED = "U0001"


def _z390(
    cc: int, registers: Mapping[int, int], abend: str = COMPLETED
) -> HlasmMachine:
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)


def _cc(cc: int) -> int:
    return HIGH_FILL | cc


def _short(image: int) -> int:
    return image << 32 | Z390_LOW


Z390_PINNED: Mapping[str, HlasmMachine] = {
    "SDR SD": _z390(1, {2: 0x32F907F2_9096918D, 8: _cc(2), 3: 0xC0FFFFFF_FFFFFFFF}),
    "SUR SU": _z390(2, {2: high_word(0x41200000), 8: _cc(2), 3: high_word(0x41100001)}),
    "SU zero without the guard digit is a true zero": _z390(
        2, {2: high_word(0x41000001)}
    ),
    "SWR SW": _z390(1, {2: 0x410AAAAA_AAAAAAAB, 8: _cc(2), 3: 0xC1055555_55555555}),
    "CDR CD": _z390(1, {8: _cc(2)}),
    "MDR MD": _z390(2, {2: 0x40FFFFFF_FFFFFFFF, 3: 0xC1200000_00000000}),
    "MXDR MXD": _z390(
        2,
        {
            2: 0x41100000_00000001,
            3: 0x33CD2B29_7D889BD0,
            4: 0xC1200000_00000000,
            5: 0xB3000000_00000000,
        },
    ),
    "HER HDR": _z390(2, {2: _short(0x40800008), 3: 0x40800000_00000008, 4: 0}),
    "SQER SQE": _z390(2, {2: _short(0x41500000), 3: _short(0x412D413D)}),
    "SQDR SQD": _z390(2, {2: 0x41200000_00000000, 3: 0x4116A09E_667F3BCC, 4: 0}),
    "FIER FIDR FIXR": _z390(
        2,
        {
            2: _short(0xC1200000),
            3: 0,
            4: 0x41200000_00000000,
            5: 0x33000000_00000000,
        },
    ),
    "MSER MSE": _z390(2, {2: high_word(0x35100000), 3: high_word(0x40FFFFFF)}),
    "MYR MY": _z390(
        2,
        {
            4: 0x42020000_00000000,
            5: 0x34000000_00000000,
            6: 0x42020000_00000000,
            7: 0x34000000_00000000,
            8: 0,
            9: 0,
        },
    ),
    "MYHR MYH": _z390(2, {4: 0x42010000_00000000, 5: 0x42020000_00000000}),
    "MYLR MYL": _z390(2, {4: 0x34200000_00000001, 5: 0x34100000_00000000}),
    "MAYR MAY": _z390(2, {r: FILL for r in range(4, 8)}, "S0C6"),
    "MAYHR MAYH": _z390(2, {4: 0x4F000000_00000000, 5: 0}),
    "MAYLR MAYL": _z390(2, {4: 0x34100000_00000000, 5: 0x34000000_00000000}),
    "LTER LTDR LTXR": _z390(
        2,
        {
            2: _short(0xC1100000),
            8: _cc(1),
            3: 0,
            9: _cc(0),
            4: 0,
            5: 0,
            10: _cc(0),
            6: 0x41100000_00000000,
            7: 0x33000000_00000001,
        },
    ),
    "LCER LCDR LCXR": _z390(
        1,
        {
            2: _short(0xC1100000),
            8: _cc(1),
            3: 0,
            9: _cc(0),
            4: 0xC1100000_00000000,
            5: 0xB3100000_00000000,
        },
    ),
    "LNER LNDR LNXR": _z390(
        0,
        {
            2: _short(0xC1100000),
            8: _cc(1),
            3: 0xC1200000_00000000,
            9: _cc(1),
            4: 0,
            5: 0,
        },
    ),
    "LPER LPDR LPXR": _z390(
        0, {2: _short(0x41100000), 8: _cc(2), 3: 0, 9: _cc(0), 4: 0, 5: 0}
    ),
    "underflow with the mask off gives a true zero": _z390(
        0, {2: 0xC1100000_00000000, 3: 0, 4: 0}
    ),
}
AGREED = [case for case in programs.CASES if case not in Z390_PINNED]

Z390_TRAPS: Mapping[str, tuple[str, int]] = {
    "unnormalized significance with the mask on keeps the characteristic": (
        COMPLETED,
        2,
    ),
    "square root of a negative suppresses": ("S0C7", 2),
}


def _both(
    z390: Z390Runner, tmp_path: Path, case: str
) -> tuple[HlasmMachine, HlasmMachine]:
    body, registers = programs.CASES[case][:2]
    source = programs.program(body)
    return (
        run_hlasm_machine(source).restricted_to(registers),
        z390.run_machine(source, tmp_path).restricted_to(registers),
    )


def _trap_ends(z390: Z390Runner, tmp_path: Path, case: str) -> list[tuple[str, int]]:
    source = programs.program(programs.TRAPS[case][0])
    machines = (run_hlasm_machine(source), z390.run_machine(source, tmp_path))
    return [(machine.run.abend, machine.cc) for machine in machines]


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


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.TRAPS))
def test_exception_ends_the_run_as_in_z390_or_as_pinned(
    z390: Z390Runner, tmp_path: Path, case: str
):
    run, cc = programs.expected_trap(case)[:2]
    ours = (run.abend, cc)

    assert _trap_ends(z390, tmp_path, case) == [ours, Z390_TRAPS.get(case, ours)]
