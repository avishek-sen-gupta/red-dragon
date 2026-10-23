# pyright: standard
"""BFP arithmetic programs leave the same declared registers, CC and abend in RedDragon and in z390, bar z390's faults below; those expectations come from the Principles of Operation (figures 19-14 to 19-26). z390 writes X'F4F4F4F4' into bits 32-63 of some short results, rounds the fused product before adding, gives CC 1 for unordered compares and NaN sign forms, ignores the round-toward-minus sign of an exact zero sum, computes extended multiplies inexactly, rejects R1 = 1 for AXBR, any nonzero modifier for FIxBRA and DIxBR, and LTDBR leaves an SNaN unquieted. Its TCEB, TCDB and TCXB match neither subnormals, infinities nor NaNs by Figure 19-26 and match -0 to another bit. It takes no invalid-operation or inexact trap."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import bfp_arithmetic_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

Z390_LOW = 0xF4F4F4F4
SPECIFICATION = "S0C6"


def _z390(abend: str, cc: int, registers: Mapping[int, int]) -> HlasmMachine:
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)


def _cc(cc: int) -> int:
    return HIGH_FILL | cc


Z390_CLASSES: Mapping[str, HlasmMachine] = {
    "selects the class bit, zeros to subnormals": _z390(
        programs.COMPLETED,
        0,
        {2: _cc(1), 3: _cc(1), 4: _cc(1), 5: _cc(1), 6: _cc(0), 7: _cc(0)},
    ),
    "selects the class bit, infinities to SNaNs": _z390(
        programs.COMPLETED, 0, {r: _cc(0) for r in range(2, 8)}
    ),
    "misses every other bit, zeros to subnormals": _z390(
        programs.COMPLETED,
        1,
        {2: _cc(0), 3: _cc(1), 4: _cc(0), 5: _cc(0), 6: _cc(1), 7: _cc(1)},
    ),
    "misses every other bit, infinities to SNaNs": _z390(
        programs.COMPLETED,
        0,
        {2: _cc(1), 3: _cc(1), 4: _cc(0), 5: _cc(0), 6: _cc(0), 7: _cc(0)},
    ),
}

Z390_PINNED: Mapping[str, HlasmMachine] = {
    "FIDBRA inexact control under an enabled mask": _z390(SPECIFICATION, 2, {2: FILL}),
    "AXBR": _z390(SPECIFICATION, 2, {2: FILL, 3: FILL}),
    "SDBR SDB": _z390(programs.COMPLETED, 0, {2: 0xC0000000_00000000, 8: _cc(1), 3: 0}),
    "MXBR": _z390(programs.COMPLETED, 2, {2: 0x40000000_00000000, 3: 0x1001}),
    "MXDBR MXDB": _z390(
        programs.COMPLETED,
        2,
        {
            2: 0x3FFEFFFF_FFFFFFFF,
            3: 0xF196A6B4_13BB21EA,
            4: 0xC0018000_00000000,
            5: 0,
        },
    ),
    "SQEBR SQEB": _z390(
        programs.COMPLETED,
        2,
        {2: 0x40000000_00000000 | Z390_LOW, 3: 0x3FB504F3_00000000 | Z390_LOW},
    ),
    "MADBR MADB": _z390(programs.COMPLETED, 2, {2: 0, 3: 0x401C0000_00000000}),
    "MADBR NaN order": _z390(
        programs.COMPLETED,
        2,
        {2: 0x7FF80000_00000009, 3: 0x7FF80000_00000005, 4: 0x7FF80000_00000009},
    ),
    "CEBR CEB": _z390(programs.COMPLETED, 1, {8: _cc(1)}),
    "CDBR CDB": _z390(programs.COMPLETED, 1, {8: _cc(2)}),
    "KEBR KEB": _z390(programs.COMPLETED, 1, {8: _cc(0)}),
    "FIEBR FIEBRA": _z390(
        SPECIFICATION, 2, {2: 0xC0000000_00000000 | Z390_LOW, 3: FILL}
    ),
    "FIXBR FIXBRA": _z390(
        SPECIFICATION, 2, {2: 0xC0000000_00000000, 3: 0, 4: FILL, 5: FILL}
    ),
    "DIEBR": _z390(SPECIFICATION, 2, {2: FILL, 3: FILL}),
    "DIEBR DIDBR in the current mode": _z390(
        programs.COMPLETED,
        0,
        {
            2: 0x3F800000_00000000,
            3: 0x40400000_00000000 | Z390_LOW,
            4: 0x3FF00000_00000000,
            5: 0x40080000_00000000,
        },
    ),
    "DIEBR quotient overflow": _z390(SPECIFICATION, 2, {2: FILL, 3: FILL}),
    "DIDBR": _z390(SPECIFICATION, 2, {2: FILL, 3: FILL}),
    "LTEBR LTDBR LTXBR": _z390(
        programs.COMPLETED,
        0,
        {8: _cc(1), 2: 0x7FF00000_00000009, 9: _cc(1), 3: 0, 4: 0},
    ),
    "LCEBR LCDBR LCXBR": _z390(
        programs.COMPLETED,
        1,
        {
            2: 0xBF800000_00000000 | Z390_LOW,
            8: _cc(1),
            3: 0xFFF00000_00000009,
            9: _cc(1),
            4: 0xC0000000_00000000,
            5: 0,
        },
    ),
    "LNEBR LNDBR LNXBR": _z390(
        programs.COMPLETED,
        1,
        {
            2: 0xBF800000_00000000 | Z390_LOW,
            8: _cc(1),
            3: 0x80000000_00000000,
            9: _cc(0),
            4: 0xC0000000_00000000,
        },
    ),
    "LPEBR LPDBR LPXBR": _z390(
        programs.COMPLETED,
        0,
        {
            2: 0x3FC00000_00000000 | Z390_LOW,
            8: _cc(2),
            3: 0x7FF00000_00000000,
            9: _cc(2),
            4: 0,
        },
    ),
    **{
        f"{mnemonic} {behaviour}": machine
        for mnemonic in ("TCEB", "TCDB", "TCXB")
        for behaviour, machine in Z390_CLASSES.items()
    },
    "TCXB misses every other bit, infinities to SNaNs": _z390(
        programs.COMPLETED, 1, {r: _cc(1) for r in range(2, 8)}
    ),
}
AGREED = [case for case in programs.CASES if case not in Z390_PINNED]

Z390_TRAPS: Mapping[str, tuple[str, int]] = {
    "invalid suppresses": (programs.COMPLETED, 2),
    "inexact traps after the store": (programs.COMPLETED, 2),
    "inexact traps with the masked overflow flagged": (programs.COMPLETED, 2),
    "compare and signal traps on a QNaN": (programs.COMPLETED, 1),
    "load and test traps on an SNaN": (programs.COMPLETED, 1),
    "load FP integer traps inexact": (programs.COMPLETED, 2),
    "divide to integer suppresses an invalid operand": (SPECIFICATION, 2),
    "divide to integer scales a tiny final remainder": (SPECIFICATION, 2),
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
def test_trap_ends_the_run_as_in_z390_or_as_pinned(
    z390: Z390Runner, tmp_path: Path, case: str
):
    run, cc = programs.expected_trap(case)[:2]
    ours = (run.abend, cc)

    assert _trap_ends(z390, tmp_path, case) == [ours, Z390_TRAPS.get(case, ours)]
