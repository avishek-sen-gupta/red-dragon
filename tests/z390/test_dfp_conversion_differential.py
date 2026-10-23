# pyright: standard
"""DFP conversion and PFPO programs leave the same declared registers, CC and abend in RedDragon and in z390, bar z390's faults pinned below; those expectations come from the Principles of Operation (chapter 20; PFPO 9-35 to 9-46), not from z390. z390 abends S0C1 for CDZT, CXZT, CPDT and CPXT (not emulated) and S0C5 for CZDT; abends S0C5 or S0C6 for CDGTR(A), CXGTR(A), CDLGTR, CGDTR(A), CGXTR(A), LDETR of an SNaN or infinity and the PFPO test bit; treats CDLFTR's source as signed; ignores M3 methods (CFXTR) and FPC modes (PFPO method 1); sets CC 0 for a negative fraction to logical (figure 20-19: CC 1) and gives 1 with CC 1 for -1 to logical (figure 20-19: 0 with CC 3); drops a NaN's digits in CUDTR and garbles LEDTR's XiC results; does not check CDPT's length or unused digits; gives PFPO no CC 1, return code, DPQC, alternate action, overflow handling or Hmax and wraps an out-of-range HFP characteristic; and takes no DFP IEEE or quantum trap."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import dfp_conversion_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

COMPLETED = "U0001"


def _z390(
    cc: int, registers: Mapping[int, int], abend: str = COMPLETED
) -> HlasmMachine:
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)


Z390_PINNED: Mapping[str, HlasmMachine] = {
    "CDGTR CDGTRA": _z390(2, {4: 0xA5A5A5A5_A5A5A5A5, 5: 0xA5A5A5A5_A5A5A5A5}, "S0C5"),
    "CXGTR CXGTRA": _z390(
        2,
        {
            4: 0xA5A5A5A5_A5A5A5A5,
            5: 0xA5A5A5A5_A5A5A5A5,
            6: 0xA5A5A5A5_A5A5A5A5,
            7: 0xA5A5A5A5_00000000,
        },
        "S0C6",
    ),
    "CDLFTR CXLFTR": _z390(2, {3: 0xA2380000_00000001, 4: 0xA2080000_00000000, 5: 0x1}),
    "CDLGTR CXLGTR": _z390(
        2,
        {3: 0xA5A5A5A5_A5A5A5A5, 4: 0xA5A5A5A5_A5A5A5A5, 5: 0xA5A5A5A5_A5A5A5A5},
        "S0C6",
    ),
    "CFDTR CFXTR": _z390(
        1, {2: 0xA5A5A5A5_FFFFFFFE, 8: 0xA5A5A5A5_00000001, 3: 0xA5A5A5A5_FFFFFFFE}
    ),
    "CGDTR CGDTRA": _z390(
        3,
        {2: 0xA5A5A5A5_A5A5A5A5, 8: 0xA5A5A5A5_00000003, 3: 0xA5A5A5A5_A5A5A5A5},
        "S0C6",
    ),
    "CGXTR CGXTRA": _z390(
        2,
        {2: 0xA5A5A5A5_A5A5A5A5, 8: 0xA5A5A5A5_A5A5A5A5, 3: 0xA5A5A5A5_A5A5A5A5},
        "S0C5",
    ),
    "CLFDTR CLFXTR": _z390(
        2, {2: 0xA5A5A5A5_00000000, 8: 0xA5A5A5A5_00000000, 3: 0xA5A5A5A5_FFFFFFFF}
    ),
    "CLGDTR CLGXTR": _z390(0, {2: 0x1, 8: 0xA5A5A5A5_00000001, 3: 0x0}),
    "LDETR keeps an infinity's digits and an SNaN only under XiC": _z390(
        2,
        {
            2: 0xA5A5A5A5_A5A5A5A5,
            3: 0xA5A5A5A5_A5A5A5A5,
            4: 0xA5A5A5A5_A5A5A5A5,
            5: 0xA5A5A5A5_A5A5A5A5,
        },
        "S0C5",
    ),
    "LDETR quiets an SNaN": _z390(2, {2: 0xA5A5A5A5_A5A5A5A5}, "S0C5"),
    "LEDTR keeps an infinity's and an SNaN's last digits only under XiC": _z390(
        2, {2: 0xF4F4F4F4, 3: 0xF4F4F4F4, 4: 0xF4F4F4F4}
    ),
    "CSDTR CUDTR": _z390(
        2, {2: 0x12345D, 3: 0x23456789_0123456F, 4: 0x12345678_90123456, 5: 0x0}
    ),
    "CDZT CXZT": _z390(
        2,
        {
            2: 0xA5A5A5A5_A5A5A5A5,
            3: 0xA5A5A5A5_A5A5A5A5,
            5: 0xA5A5A5A5_A5A5A5A5,
            6: 0xA5A5A5A5_A5A5A5A5,
        },
        "S0C1",
    ),
    "CPDT CPXT": _z390(
        0,
        {
            8: 0xA5A5A5A5_A5A5A5A5,
            9: 0xA5A5A5A5_A5A5A5A5,
            2: 0xA5A5A5A5_A5A5A5A5,
            3: 0xA5A5A5A5_A5A5A5A5,
            4: 0xA5A5A5A5_A5A5A5A5,
            5: 0xA5A5A5A5_A5A5A5A5,
            6: 0xA5A5A5A5_A5A5A5A5,
        },
        "S0C1",
    ),
    "CPDT converts specials with CC 3 and forces a plus zero": _z390(
        2, {8: 0xA5A5A5A5_A5A5A5A5, 2: 0xA5A5A5A5_A5A5A5A5}, "S0C1"
    ),
    "CZDT CZXT": _z390(
        1,
        {
            2: 0xA5A5A5A5_A5A5A5A5,
            3: 0xA5A5A5A5_A5A5A5A5,
            4: 0xA5A5A5A5_A5A5A5A5,
            5: 0xA5A5A5A5_A5A5A5A5,
            6: 0xA5A5A5A5_A5A5A5A5,
        },
        "S0C5",
    ),
    "CPDT lost digits complete then abend S0CA": _z390(2, {}, "S0C1"),
    "CDPT longer than 9 bytes abends S0C6": _z390(2, {}),
    "PFPO test bit sets CC 0 or 3 and a zero return code": _z390(
        2,
        {8: 0xA5A5A5A5_A5A5A5A5, 2: 0xA5A5A5A5_A5A5A5A5, 9: 0xA5A5A5A5_A5A5A5A5},
        "S0C5",
    ),
    "PFPO BFP long to DFP long rounds by the DFP mode": _z390(
        0, {2: 0x25F80000_00000000, 3: 0xA5A5A5A5_A5A5A5A5}
    ),
    "PFPO DFP long to BFP long": _z390(0, {2: 0x3FB99999_9999999A}),
    "PFPO HFP short to BFP short and BFP long to HFP long are exact": _z390(
        0, {2: 0x3F800000_F4F4F4F4, 3: 0xC1180000_00000000}
    ),
    "PFPO turns a DFP NaN into plus Hmax": _z390(0, {2: 0xF4F4F4F4}),
    "PFPO picks the exact DFP quantum by DPQC": _z390(
        0, {2: 0x22380000_00000010, 3: 0x22380000_00000010}
    ),
    "PFPO rounds by the BFP mode for method 1": _z390(0, {2: 0x39FB66D9_B66D9B66}),
    "PFPO alternate action delivers the scaled overflow with CC 2": _z390(
        0, {2: 0xA5A5A5A5_A5A5A5A5, 3: 0xA5A5A5A5_A5A5A5A5}, "S0CC"
    ),
    "PFPO masked overflow gives infinity and a zero return code": _z390(
        0, {2: 0xA5A5A5A5_A5A5A5A5, 3: 0xA5A5A5A5_A5A5A5A5}, "S0CC"
    ),
    "PFPO with an invalid function abends S0C6": _z390(0, {}),
    "PFPO reports HFP overflow as invalid or as overflow by bit 58": _z390(
        0, {2: 0x8335F9DF_F4F4F4F4, 3: 0x8335F9DF_F4F4F4F4}
    ),
    "PFPO gives HFP underflow a signed true zero, unreported without bit 59": _z390(
        0, {2: 0xFE4BE2B0_F4F4F4F4}
    ),
    "PFPO reports HFP underflow under bit 59": _z390(0, {2: 0xFE4BE2B0_F4F4F4F4}),
    "EX of CDZT takes the length from R1": _z390(2, {2: 0xA5A5A5A5_A5A5A5A5}, "S0C1"),
}
AGREED = [case for case in programs.CASES if case not in Z390_PINNED]

Z390_TRAPS: Mapping[str, tuple[str, int]] = {
    "CGDTR invalid suppresses and leaves the CC": ("U0001", 0),
    "CFDTR inexact traps after the store": ("U0001", 1),
    "LDETR invalid suppresses": ("S0C5", 2),
    "LEDTR overflow delivers the scaled long result": ("S0CC", 2),
    "CDPT suppresses on a nonzero unused digit with DXC 0": ("U0001", 2),
    "CDZT suppresses on a bad digit with DXC 0": ("S0C1", 2),
    "PFPO overflow traps after the scaled store": ("U0001", 0),
    "PFPO invalid suppresses": ("U0001", 0),
    "CDLGTR quantum traps after the store": ("S0C6", 2),
    "PFPO inexact traps with a zero return code": ("U0001", 0),
    "PFPO quantum traps with a zero return code": ("U0001", 0),
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
