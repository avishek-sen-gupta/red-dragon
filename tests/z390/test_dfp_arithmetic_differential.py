# pyright: standard
"""DFP arithmetic programs leave the same declared registers, CC and abend in RedDragon and in z390, bar z390's faults below; those expectations come from the Principles of Operation, chapter 20. z390 encodes a zero result with biased exponent 0 and drops the minus sign of an exact zero difference rounded toward minus infinity; ignores the FPC DFP mode and the M4 method, so MDTRA, DDTRA and the tie round otherwise; keeps the source quantum in FIDTR and FIXTR and rounds QADTR 1.23 to 1.3; abends S0C5 for an M4 of 8-15 and for a zero divisor, S0C6 for a nonzero FIDTR M3 or QADTR M4, and S0CC for the tiny quotient and IEDTR specials; treats infinities and NaNs as numbers in ADTR, CDTR (so minus infinity is above -1), CEDTR, LTDTR, EEDTR, ESDTR, SLDT and SRDT; misclassifies subnormals, NaNs, infinities and extreme exponents in TDCDT and TDGDT; and takes no IEEE or quantum trap. The quantum exception is therefore pinned only to the PoO (20-50, 20-43, 20-53): it compares the result's quantum with the third operand's."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import dfp_arithmetic_programs as programs
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
    "CDTR orders signs, infinities, zeros and distant exponents": _z390(
        1,
        {
            2: 0xA5A5A5A5_00000001,
            3: 0xA5A5A5A5_00000000,
            4: 0xA5A5A5A5_00000002,
            5: 0xA5A5A5A5_00000000,
            6: 0xA5A5A5A5_00000002,
            7: 0xA5A5A5A5_00000001,
        },
    ),
    "CDTR leaves a QNaN unsignaled": _z390(2, {}),
    "AXTR AXTRA": _z390(
        0, {2: 0x22080000_00000000, 3: 3, 9: 0xA5A5A5A5_00000002, 4: 0, 5: 0}
    ),
    "SDTR SDTRA": _z390(0, {2: 0xA2380000_00000001, 8: 0xA5A5A5A5_00000001, 3: 0}),
    "MDTR MDTRA": _z390(2, {2: 0x22300000_00000530, 3: 0x31F88000_00000000}),
    "DDTR DDTRA": _z390(2, {2: 0x2DF9B36C_DB36CDB3, 3: 0x39FB66D9_B66D9B66}),
    "MXTRA DXTRA with modifiers 8 to 15": _z390(
        2,
        {
            2: 0xA5A5A5A5_A5A5A5A5,
            3: 0xA5A5A5A5_A5A5A5A5,
            4: 0xA5A5A5A5_A5A5A5A5,
            5: 0xA5A5A5A5_A5A5A5A5,
        },
        "S0C5",
    ),
    "DDTR rounds a tiny quotient up to Nmin": _z390(
        2, {2: 0xA5A5A5A5_A5A5A5A5}, "S0CC"
    ),
    "ADTR NaNs and infinity set CC 3 and 2": _z390(
        2,
        {
            2: 0x22380000_00000001,
            8: 0xA5A5A5A5_00000002,
            3: 0x22380000_00000001,
            9: 0xA5A5A5A5_00000002,
            4: 0x22380000_00000001,
        },
    ),
    "ADTR rounds a tie by the FPC DFP mode": _z390(2, {2: 0x25FC0000_00000000}),
    "CDTR KDTR": _z390(
        2, {8: 0xA5A5A5A5_00000001, 9: 0xA5A5A5A5_00000000, 10: 0xA5A5A5A5_00000002}
    ),
    "CEDTR CEXTR": _z390(
        1,
        {
            8: 0xA5A5A5A5_00000002,
            9: 0xA5A5A5A5_00000000,
            10: 0xA5A5A5A5_00000000,
            11: 0xA5A5A5A5_00000000,
        },
    ),
    "LTDTR LTXTR": _z390(
        0,
        {
            2: 0,
            8: 0xA5A5A5A5_00000000,
            3: 0x22380000_0000006E,
            9: 0xA5A5A5A5_00000002,
            4: 0xA2080000_00000000,
            5: 1,
            10: 0xA5A5A5A5_00000001,
            6: 0,
        },
    ),
    "EEDTR EEXTR": _z390(2, {2: 398, 3: 398, 4: 398, 5: 6176}),
    "ESDTR ESXTR": _z390(2, {2: 3, 3: 0, 4: 0, 5: 16, 6: 1}),
    "IEDTR makes an infinity, an SNaN and a QNaN": _z390(
        2,
        {5: 0xA5A5A5A5_A5A5A5A5, 6: 0xA5A5A5A5_A5A5A5A5, 7: 0xA5A5A5A5_00000000},
        "S0CC",
    ),
    "FIDTR FIXTR": _z390(
        2,
        {
            2: 0xA5A5A5A5_A5A5A5A5,
            3: 0xA5A5A5A5_A5A5A5A5,
            4: 0xA5A5A5A5_A5A5A5A5,
            5: 0xA5A5A5A5_A5A5A5A5,
        },
        "S0C6",
    ),
    "QADTR QAXTR": _z390(
        2,
        {
            2: 0xA5A5A5A5_A5A5A5A5,
            3: 0xA5A5A5A5_A5A5A5A5,
            4: 0xA5A5A5A5_A5A5A5A5,
            5: 0xA5A5A5A5_A5A5A5A5,
            6: 0xA5A5A5A5_A5A5A5A5,
        },
        "S0C6",
    ),
    "QADTR FIDTR RRDTR keep the source quantum without a quantum trap": _z390(
        2,
        {2: 0xA5A5A5A5_A5A5A5A5, 3: 0xA5A5A5A5_A5A5A5A5, 4: 0xA5A5A5A5_A5A5A5A5},
        "S0C6",
    ),
    "SLDT SLXT": _z390(
        2,
        {
            2: 0x22300000_00004980,
            3: 0x2E300000_00000000,
            4: 0,
            5: 0,
            6: 0x2E080000_00000000,
            7: 0,
        },
    ),
    "SRDT SRXT": _z390(
        2, {2: 0x22300000_00000012, 3: 0x22300000_00000001, 4: 0, 5: 0, 6: 0}
    ),
    "TDCDT TDCET TDCXT": _z390(
        1,
        {
            2: 0xA5A5A5A5_00000001,
            3: 0xA5A5A5A5_00000000,
            4: 0xA5A5A5A5_00000000,
            5: 0xA5A5A5A5_00000000,
            6: 0xA5A5A5A5_00000001,
            7: 0xA5A5A5A5_00000000,
            8: 0xA5A5A5A5_00000001,
            9: 0xA5A5A5A5_00000000,
            10: 0xA5A5A5A5_00000001,
        },
    ),
    "TDGDT TDGET TDGXT": _z390(
        1,
        {
            2: 0xA5A5A5A5_00000001,
            3: 0xA5A5A5A5_00000000,
            4: 0xA5A5A5A5_00000001,
            5: 0xA5A5A5A5_00000001,
            6: 0xA5A5A5A5_00000001,
            7: 0xA5A5A5A5_00000000,
            8: 0xA5A5A5A5_00000000,
            9: 0xA5A5A5A5_00000001,
        },
    ),
}
AGREED = [case for case in programs.CASES if case not in Z390_PINNED]

Z390_TRAPS: Mapping[str, tuple[str, int]] = {
    "compare suppresses on an SNaN and leaves the CC": ("U0001", 2),
    "compare and signal traps on a QNaN": ("U0001", 2),
    "load FP integer traps inexact": ("U0001", 2),
    "load FP integer with XxC traps the quantum": ("S0C6", 2),
    "quantize traps the quantum against the source quantum": ("S0C6", 2),
    "quantize invalid suppresses": ("U0001", 2),
    "load and test suppresses on an SNaN": ("U0001", 0),
    "invalid suppresses": ("U0001", 2),
    "division by zero suppresses": ("S0C5", 2),
    "underflow delivers the scaled result": ("U0001", 2),
    "inexact traps after the store": ("U0001", 2),
    "quantum traps after the store on an A form": ("U0001", 2),
    "an inexact trap takes the place of the quantum trap": ("U0001", 2),
    "quantum traps on an exact product off its quantum": ("U0001", 2),
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
