# pyright: standard
"""BFP conversion programs leave the same declared registers, CC and abend in RedDragon and in z390, bar z390's faults below; those expectations come from the Principles of Operation (figures 19-18 to 19-20). Converting to fixed, z390 rejects a nonzero M4 (S0C6), ignores the FPC rounding mode, wraps or loses bits on out-of-range sources instead of delivering the maximum with CC 3, gives CC 0 for -0.5 rounded to 0 and for -infinity, converts -1 to logical 1, abends S0C5 on a NaN source, and takes no inexact trap."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import bfp_conversion_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

COMPLETED = "U0001"
SPECIFICATION = "S0C6"
ADDRESSING = "S0C5"


def _z390(abend: str, cc: int, registers: Mapping[int, int]) -> HlasmMachine:
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)


def _low(value: int) -> int:
    return HIGH_FILL | value


Z390_PINNED: Mapping[str, HlasmMachine] = {
    "CFEBR CFEBRA": _z390(SPECIFICATION, 1, {2: _low(0xFFFFFFFE), 8: _low(1), 3: FILL}),
    "CFDBR CFDBRA": _z390(
        COMPLETED, 2, {2: _low(0x80000000), 8: _low(1), 3: _low(0x7FFFFFFF)}
    ),
    "CFXBR CFXBRA": _z390(SPECIFICATION, 0, {2: _low(0), 8: _low(0), 3: FILL}),
    "CGEBR CGEBRA": _z390(
        COMPLETED,
        1,
        {2: 0x7FFFFFF7_6B48C000, 8: _low(2), 3: 0x80000008_94B74000},
    ),
    "CGDBR CGDBRA in the current mode": _z390(
        COMPLETED, 1, {2: 4, 8: _low(2), 4: 4, 3: 0xFFFFFFFF_FFFFFFFF}
    ),
    "CGXBR CGXBRA": _z390(COMPLETED, 0, {2: 3, 8: _low(2), 3: 0}),
    "CLFEBR": _z390(COMPLETED, 2, {2: _low(0), 8: _low(0), 3: _low(0x6B48C000)}),
    "CLFDBR": _z390(SPECIFICATION, 2, {2: _low(0xFFFFFFFF), 8: _low(2), 3: FILL}),
    "CLFXBR": _z390(COMPLETED, 2, {2: _low(3), 8: _low(2), 3: _low(1)}),
    "CLGEBR": _z390(
        COMPLETED,
        2,
        {2: 0xFFFFFC4B_83FD4000, 8: _low(2), 3: 0x7FFFFFF7_6B48C000},
    ),
    "CLGDBR": _z390(ADDRESSING, 2, {2: FILL, 8: FILL, 3: FILL}),
    "CLFDBR inexact control under an enabled mask": _z390(SPECIFICATION, 2, {2: FILL}),
    "CFDBR invalid suppresses": _z390(ADDRESSING, 2, {2: FILL}),
    "CGDBR masked invalid takes the inexact trap after the store": _z390(
        ADDRESSING, 2, {2: FILL}
    ),
    "CFDBR inexact traps after the store": _z390(COMPLETED, 2, {2: _low(4)}),
}
AGREED = [case for case in programs.CASES if case not in Z390_PINNED]


def _both(
    z390: Z390Runner, tmp_path: Path, case: str
) -> tuple[HlasmMachine, HlasmMachine]:
    body, registers = programs.CASES[case][:2]
    source = programs.program(body)
    return (
        run_hlasm_machine(source).restricted_to(registers),
        z390.run_machine(source, tmp_path).restricted_to(registers),
    )


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
