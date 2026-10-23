# pyright: standard
"""Every data exception run on the VM places its DXC in FPC byte 2 and keeps the rest of the FPC: 00 for a decimal operand, FF for compare-and-trap and load-and-trap (PoO 6-17 Figure 6-2, 6-18 Figure 6-3, 6-19 programming note)."""

from collections.abc import Mapping

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import run_hlasm_fpc

PRESET = 0x80804000
GENERAL_OPERAND = 0x80800000
COMPARE_AND_TRAP = 0x8080FF00


def _program(body: str) -> str:
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         L     1,PRESET\n"
        "         SFPC  1\n"
        f"{body}"
        "         ABEND 1\n"
        "         DS    0D\n"
        "DBAD     DC    X'0000000000000011'\n"
        f"PRESET   DC    X'{PRESET:08X}'\n"
        "ZERO     DC    F'0'\n"
        "GOOD     DC    P'1'\n"
        "BADDIGIT DC    X'0A1C'\n"
        "BADSIGN  DC    X'0011'\n"
    )


CASES: Mapping[str, tuple[str, int]] = {
    "AP invalid digit": ("         AP    GOOD,BADDIGIT\n", GENERAL_OPERAND),
    "CP invalid sign": ("         CP    GOOD,BADSIGN\n", GENERAL_OPERAND),
    "CVB invalid sign": ("         CVB   3,DBAD\n", GENERAL_OPERAND),
    "CRT equal trap": (
        "         LHI   3,7\n         LHI   4,7\n         CRT   3,4,8\n",
        COMPARE_AND_TRAP,
    ),
    "LAT zero": ("         LAT   3,ZERO\n", COMPARE_AND_TRAP),
    "LFHAT zero": ("         LFHAT 3,ZERO\n", COMPARE_AND_TRAP),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(CASES))
def test_a_data_exception_stores_its_dxc_in_the_fpc(case: str):
    body, fpc = CASES[case]
    machine, left = run_hlasm_fpc(_program(body))

    assert (machine.run.abend, left) == ("S0C7", fpc)
