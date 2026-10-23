# pyright: standard
"""HFP conversion programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; results come back in GRs (FPRs through LGDR), intermediate CCs through IPM. Expected values are worked from the Principles of Operation, 18-11, 18-15, 18-17 and figures 9-18 and 9-20."""

from collections.abc import Mapping

from tests.integration.hlasm.bfp_arithmetic_programs import (
    COMPLETED,
    PRESET,
    cc_into,
    cc_word,
    extended_from,
    high_word,
    lines,
    zeroed_short,
)
from tests.integration.hlasm.hfp_arithmetic_programs import DATA, Case
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import ABEND, HIGH_FILL, based_program


def program(body: str) -> str:
    return based_program(body, ABEND + DATA)


def case_of(body: str, registers: Mapping[int, int], cc: int) -> Case:
    return (PRESET + body, registers, cc)


def _low(value: int) -> int:
    return HIGH_FILL | value


TO_FIXED: Mapping[str, Case] = {
    "CFER CGER": case_of(
        lines("LE 1,EM2P5", "CFER 2,0,1") + cc_into(8) + lines("CGER 3,1,1"),
        {2: _low(0xFFFFFFFE), 8: cc_word(1), 3: 0xFFFFFFFF_FFFFFFFD},
        1,
    ),
    "CFDR CGDR": case_of(
        lines("LD 1,DTHIRD", "CFDR 2,6,1")
        + cc_into(8)
        + lines("CFDR 4,4,1")
        + cc_into(9)
        + lines("LD 1,DBIG", "CGDR 3,4,1"),
        {2: _low(1), 8: cc_word(2), 4: _low(0), 9: cc_word(2), 3: 0x7FFFFFFF_FFFFFFFF},
        3,
    ),
    "CFXR CGXR": case_of(
        extended_from(4, "XM1")
        + lines("CFXR 2,5,4")
        + cc_into(8)
        + extended_from(4, "X2P5")
        + lines("CGXR 3,4,4"),
        {2: _low(0xFFFFFFFF), 8: cc_word(1), 3: 3},
        2,
    ),
}

TO_BFP: Mapping[str, Case] = {
    "TBEDR": case_of(
        zeroed_short(2, 4, 6)
        + lines("LD 1,D1", "TBEDR 2,0,1", "LGDR 3,2")
        + cc_into(8)
        + lines("LD 1,DMTINY", "TBEDR 6,4,1", "LGDR 7,6")
        + cc_into(9)
        + lines("LD 1,DBIG", "TBEDR 4,4,1", "LGDR 5,4"),
        {
            3: high_word(0x3F800000),
            8: cc_word(2),
            7: high_word(0x80200000),
            9: cc_word(1),
            5: high_word(0x7F800000),
        },
        3,
    ),
    "TBDR": case_of(
        lines("LD 1,DTHIRD", "TBDR 2,6,1", "LGDR 3,2", "TBDR 2,5,1", "LGDR 4,2")
        + cc_into(8)
        + lines("LD 1,DMZERO", "TBDR 2,0,1", "LGDR 5,2"),
        {
            3: 0x3FD55555_55555556,
            4: 0x3FD55555_55555555,
            8: cc_word(2),
            5: 0x80000000_00000000,
        },
        0,
    ),
}

CASES: Mapping[str, Case] = {**TO_FIXED, **TO_BFP}


def expected(case: str) -> HlasmMachine:
    registers, cc = CASES[case][1:3]
    return HlasmMachine(
        HlasmRun(return_code=0, abend=COMPLETED, stdout=""), cc, registers
    )
