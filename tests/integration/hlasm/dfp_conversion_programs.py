# pyright: standard
"""DFP conversion programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; results come back in GRs (FPRs through LGDR), intermediate CCs through IPM, and every program first clears the FPC. Expected values are worked from the Principles of Operation, chapter 20 (fixed point 20-24 to 20-32, figures 20-18 and 20-19), with images per figures 20-1 and 20-32."""

from collections.abc import Mapping

from tests.integration.hlasm.bfp_arithmetic_programs import (
    DATA_EXCEPTION,
    INEXACT_FLAG,
    INVALID_FLAG,
    PRESET_CC,
    Case,
    Trap,
    case_of,
    cc_into,
    cc_word,
    extended_from,
    lines,
    trap_of,
)
from tests.integration.hlasm.dfp_arithmetic_programs import DATA, QUANTUM_FLAG
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import (
    ABEND,
    HIGH_FILL,
    based_program,
)

CONVERSION_DATA = (
    "         DS    0D\n"
    "G17      DC    X'002BDC545D6B4B87'\n"
    "GMIN     DC    X'8000000000000000'\n"
    "GU64     DC    X'FFFFFFFFFFFFFFFF'\n"
    "D1E20    DC    X'2288000000000001'\n"
    "DM0P4    DC    X'A234000000000004'\n"
    "XM2P5    DC    X'A207C000000000000000000000000025'\n"
    "XU32P5   DC    X'2207C0000000000000000010AAFDCADD'\n"
    "XQNAN    DC    X'7C000000000000000000000000000000'\n"
    "XZERO    DC    X'22080000000000000000000000000000'\n"
)


def program(body: str) -> str:
    return based_program(body, ABEND + DATA + CONVERSION_DATA)


def _low(value: int) -> int:
    return HIGH_FILL | value


FIXED: Mapping[str, Case] = {
    "CDFTR CXFTR": case_of(
        lines("LGHI 2,-7", "CDFTR 1,0,2,0", "CXFTR 4,0,2,0")
        + lines("LGDR 3,1", "LGDR 4,4", "LGDR 5,6"),
        {3: 0xA2380000_00000007, 4: 0xA2080000_00000000, 5: 7},
        PRESET_CC,
    ),
    "CDGTR CDGTRA": case_of(
        lines("LG 2,G17", "CDGTR 1,2", "CDGTRA 3,9,2,0", "LGDR 4,1", "LGDR 5,3"),
        {4: 0x263D34B9_C1E28E57, 5: 0x263D34B9_C1E28E56},
        PRESET_CC,
        INEXACT_FLAG,
    ),
    "CXGTR CXGTRA": case_of(
        lines("LG 2,GMIN", "CXGTR 4,2", "CXGTRA 8,9,2,4")
        + lines("LGDR 4,4", "LGDR 5,6", "LGDR 6,8", "LGDR 7,10"),
        {
            4: 0xA2080000_00000000,
            5: 0x948DF20D_A5CFD42E,
            6: 0xA2080000_00000000,
            7: 0x948DF20D_A5CFD42E,
        },
        PRESET_CC,
    ),
    "CDLFTR CXLFTR": case_of(
        lines("LG 2,GU64", "CDLFTR 1,0,2,0", "CXLFTR 4,0,2,0")
        + lines("LGDR 3,1", "LGDR 4,4", "LGDR 5,6"),
        {3: 0x22380001_15AFB55B, 4: 0x22080000_00000000, 5: 0x00000001_15AFB55B},
        PRESET_CC,
    ),
    "CDLGTR CXLGTR": case_of(
        lines("LG 2,GU64", "CDLGTR 1,5,2,0", "CXLGTR 4,0,2,0")
        + lines("LGDR 3,1", "LGDR 4,4", "LGDR 5,6"),
        {3: 0x264A4CDD_2077C2DD, 4: 0x22080000_00000001, 5: 0x891BC41C_F89B4715},
        PRESET_CC,
        INEXACT_FLAG | QUANTUM_FLAG,
    ),
    "CFDTR CFXTR": case_of(
        lines("LD 1,DM2P5", "CFDTR 2,0,1,0")
        + cc_into(8)
        + extended_from(4, "XM2P5")
        + lines("CFXTR 3,1,4,0"),
        {2: _low(0xFFFFFFFE), 8: cc_word(1), 3: _low(0xFFFFFFFD)},
        1,
        INEXACT_FLAG,
    ),
    "CGDTR CGDTRA": case_of(
        lines("LD 1,D1E20", "CGDTR 2,0,1")
        + cc_into(8)
        + lines("LD 1,D2P5", "CGDTRA 3,0,1,4"),
        {2: 0x7FFFFFFF_FFFFFFFF, 8: cc_word(3), 3: 2},
        2,
        INVALID_FLAG,
    ),
    "CGXTR CGXTRA": case_of(
        extended_from(4, "XQNAN")
        + lines("CGXTR 2,0,4")
        + cc_into(8)
        + extended_from(4, "XM2P5")
        + lines("CGXTRA 3,9,4,0"),
        {2: 0x80000000_00000000, 8: cc_word(3), 3: 0xFFFFFFFF_FFFFFFFE},
        1,
        INVALID_FLAG | INEXACT_FLAG,
    ),
    "CLFDTR CLFXTR": case_of(
        lines("LD 1,DM0P4", "CLFDTR 2,0,1,0")
        + cc_into(8)
        + extended_from(4, "XU32P5")
        + lines("CLFXTR 3,9,4,0"),
        {2: _low(0), 8: cc_word(1), 3: _low(0xFFFFFFFF)},
        2,
        INEXACT_FLAG,
    ),
    "CLGDTR CLGXTR": case_of(
        lines("LD 1,DM1", "CLGDTR 2,0,1,0")
        + cc_into(8)
        + extended_from(4, "XZERO")
        + lines("CLGXTR 3,0,4,0"),
        {2: 0, 8: cc_word(3), 3: 0},
        0,
        INVALID_FLAG,
    ),
}

CASES: Mapping[str, Case] = {**FIXED}

TRAPS: Mapping[str, Trap] = {
    "CGDTR invalid suppresses and leaves the CC": trap_of(
        lines("LD 1,DQNAN", "CGDTR 2,0,1"), {}, 0x80008000
    ),
    "CFDTR inexact traps after the store": trap_of(
        lines("LD 1,DM2P5", "CFDTR 2,0,1,0"),
        {},
        0x08000800,
        1,
    ),
    "CDGTR inexact traps after the store": trap_of(
        lines("LG 2,G17", "CDGTR 1,2"), {1: 0x263D34B9_C1E28E57}, 0x08000C00
    ),
    "CDLGTR quantum traps after the store": trap_of(
        lines("LG 2,GU64", "CDLGTR 1,5,2,0"),
        {1: 0x264A4CDD_2077C2DD},
        0x04080400,
    ),
}


def expected_trap(case: str) -> tuple[HlasmRun, int, Mapping[int, int], int]:
    fprs, cc, fpc = TRAPS[case][1:]
    return HlasmRun(return_code=0, abend=DATA_EXCEPTION, stdout=""), cc, fprs, fpc


def expected(case: str) -> HlasmMachine:
    registers, cc, abend = CASES[case][1:4]
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)
