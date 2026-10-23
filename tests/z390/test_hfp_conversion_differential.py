# pyright: standard
"""HFP conversion programs leave the same declared registers, CC and abend in RedDragon and in z390, bar z390's faults below; those expectations come from the Principles of Operation (18-11, 18-15, 18-17 and figures 9-18 and 9-20). Converting to fixed, z390 sets the CC from the result rather than the source (0.33 rounded to 0 gives CC 0) and wraps an out-of-range source instead of delivering the maximum with CC 3. Converting HFP to BFP, it writes X'F4F4F4F4' into bits 32-63 of short results, flushes a tiny value to +0 with CC 0 instead of denormalizing it with CC 1, gives CC 2 instead of 3 on overflow, and garbles TBDR (1/3 becomes 1.0, -0 becomes +0). Converting from fixed, it rounds where HFP truncates (CEFR, CDGR) and writes X'F4F4F4F4' into bits 32-63 of short results. Converting BFP to HFP, it goes through host floating point, so THDER of a subnormal and THDR of 2^251 lose low bits, THDR overflow gives X'7FFFFFFFFFFFFFFE' with CC 2 instead of all ones with CC 3, an underflow or -0 becomes +0, and THDER of an infinity abends S0C5."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import hfp_conversion_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

COMPLETED = "U0001"
Z390_LOW = 0xF4F4F4F4


def _z390(
    cc: int, registers: Mapping[int, int], abend: str = COMPLETED
) -> HlasmMachine:
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)


def _cc(cc: int) -> int:
    return HIGH_FILL | cc


def _low(value: int) -> int:
    return HIGH_FILL | value


def _short(image: int) -> int:
    return image << 32 | Z390_LOW


Z390_PINNED: Mapping[str, HlasmMachine] = {
    "CFDR CGDR": _z390(
        1, {2: _low(1), 8: _cc(2), 4: _low(0), 9: _cc(0), 3: 0xAB000000_00000000}
    ),
    "TBEDR": _z390(
        2,
        {
            3: _short(0x3F800000),
            8: _cc(2),
            7: Z390_LOW,
            9: _cc(0),
            5: _short(0x7F800000),
        },
    ),
    "TBDR": _z390(0, {3: 0x3FF00000_00000000, 4: 0, 8: _cc(0), 5: 0}),
    "CEFR CEGR": _z390(2, {3: _short(0x48800000), 4: _short(0xD0800000)}),
    "CDFR CDGR": _z390(2, {3: 0xC1100000_00000000, 4: 0x50800000_00000000, 5: 0}),
    "THDER": _z390(
        1,
        {
            3: 0x41100000_00000000,
            8: _cc(2),
            4: 0x9B7FFFFF_FFFFFFFE,
            9: _cc(1),
            5: FILL,
            10: FILL,
            6: FILL,
        },
        "S0C5",
    ),
    "THDR": _z390(
        0,
        {
            3: 0x40199999_9999999A,
            8: _cc(2),
            4: 0x7F7FFFFF_FFFFFFFF,
            5: 0x7FFFFFFF_FFFFFFFE,
            9: _cc(2),
            6: 0x00100000_00000000,
            7: 0,
            10: _cc(1),
            11: 0,
        },
    ),
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
