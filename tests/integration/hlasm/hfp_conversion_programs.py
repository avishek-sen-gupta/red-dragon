# pyright: standard
"""HFP conversion programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; results come back in GRs (FPRs through LGDR), intermediate CCs through IPM. Expected values are worked from the Principles of Operation, 18-11, 18-15, 18-17 and figures 9-18 and 9-20."""

from collections.abc import Mapping

from tests.integration.hlasm.bfp_arithmetic_programs import (
    COMPLETED,
    PRESET,
    PRESET_CC,
    cc_into,
    cc_word,
    extended_from,
    high_word,
    lines,
    zeroed_short,
)
from tests.integration.hlasm.hfp_arithmetic_programs import (
    DATA,
    EXPONENT_OVERFLOW,
    Case,
)
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import ABEND, HIGH_FILL, based_program

CONVERSION_DATA = (
    "         DS    0D\n"
    "BS1      DC    X'3F800000'\n"
    "BSMIN    DC    X'80000001'\n"
    "BSNAN    DC    X'FFC00000'\n"
    "BSMINF   DC    X'FF800000'\n"
    "BDTENTH  DC    X'3FB999999999999A'\n"
    "BDHMAX   DC    X'4FA0000000000000'\n"
    "BDOVER   DC    X'4FB0000000000000'\n"
    "BDHMIN   DC    X'2FB0000000000000'\n"
    "BDUNDER  DC    X'AFA0000000000000'\n"
    "DRND     DC    X'4110000080000000'\n"
    "DCARRY   DC    X'C1FFFFFF80000000'\n"
    "DMAXR    DC    X'7FFFFFFF80000000'\n"
    "XRND     DC    X'41100000000000003380000000000000'\n"
    "XCARRY   DC    X'41FFFFFFFFFFFFFF3380000000000000'\n"
    "XRNDE    DC    X'41100000800000003300000000000000'\n"
)


def program(body: str) -> str:
    return based_program(body, ABEND + DATA + CONVERSION_DATA)


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

FROM_FIXED: Mapping[str, Case] = {
    "CEFR CEGR": case_of(
        zeroed_short(1)
        + lines(
            "IILF 2,X'7FFFFFFF'",
            "CEFR 1,2",
            "LGDR 3,1",
            "LLIHF 2,X'80000000'",
            "CEGR 1,2",
            "LGDR 4,1",
        ),
        {3: high_word(0x487FFFFF), 4: high_word(0xD0800000)},
        PRESET_CC,
    ),
    "CDFR CDGR": case_of(
        lines(
            "IILF 2,X'FFFFFFFF'",
            "CDFR 1,2",
            "LGDR 3,1",
            "LLIHF 2,X'7FFFFFFF'",
            "IILF 2,X'FFFFFFFF'",
            "CDGR 1,2",
            "LGDR 4,1",
            "LGHI 2,0",
            "CDGR 1,2",
            "LGDR 5,1",
        ),
        {3: 0xC1100000_00000000, 4: 0x507FFFFF_FFFFFFFF, 5: 0},
        PRESET_CC,
    ),
    "CXFR CXGR": case_of(
        lines(
            "IILF 2,X'00000100'",
            "CXFR 4,2",
            "LGDR 3,4",
            "LGDR 5,6",
            "LLIHF 2,X'80000000'",
            "IILF 2,X'00000001'",
            "CXGR 4,2",
            "LGDR 7,4",
            "LGDR 8,6",
            "LGHI 2,0",
            "CXGR 4,2",
            "LGDR 9,4",
            "LGDR 10,6",
        ),
        {
            3: 0x43100000_00000000,
            5: 0x35000000_00000000,
            7: 0xD07FFFFF_FFFFFFFF,
            8: 0xC2FF0000_00000000,
            9: 0,
            10: 0,
        },
        PRESET_CC,
    ),
}

FROM_BFP: Mapping[str, Case] = {
    "THDER": case_of(
        lines("LE 1,BS1", "THDER 2,1", "LGDR 3,2")
        + cc_into(8)
        + lines("LE 1,BSMIN", "THDER 2,1", "LGDR 4,2")
        + cc_into(9)
        + lines("LE 1,BSMINF", "THDER 2,1", "LGDR 5,2")
        + cc_into(10)
        + lines("LE 1,BSNAN", "THDER 2,1", "LGDR 6,2"),
        {
            3: 0x41100000_00000000,
            8: cc_word(2),
            4: 0x9B800000_00000000,
            9: cc_word(1),
            5: 0xFFFFFFFF_FFFFFFFF,
            10: cc_word(3),
            6: 0x7FFFFFFF_FFFFFFFF,
        },
        3,
    ),
    "THDR": case_of(
        lines("LD 1,BDTENTH", "THDR 2,1", "LGDR 3,2")
        + cc_into(8)
        + lines("LD 1,BDHMAX", "THDR 2,1", "LGDR 4,2")
        + lines("LD 1,BDOVER", "THDR 2,1", "LGDR 5,2")
        + cc_into(9)
        + lines("LD 1,BDHMIN", "THDR 2,1", "LGDR 6,2")
        + lines("LD 1,BDUNDER", "THDR 2,1", "LGDR 7,2")
        + cc_into(10)
        + lines("LD 1,DMZERO", "THDR 2,1", "LGDR 11,2"),
        {
            3: 0x40199999_9999999A,
            8: cc_word(2),
            4: 0x7F800000_00000000,
            5: 0x7FFFFFFF_FFFFFFFF,
            9: cc_word(3),
            6: 0x00100000_00000000,
            7: 0x80000000_00000000,
            10: cc_word(1),
            11: 0x80000000_00000000,
        },
        0,
    ),
}

LENGTHENED: Mapping[str, Case] = {
    "LDER LDE": case_of(
        lines("LE 2,EM2", "LD 1,DPAT", "LDER 1,2", "LGDR 3,1")
        + lines("LD 1,DPAT", "LDE 1,EZ41", "LGDR 4,1"),
        {3: 0xC1200000_00000000, 4: 0x41000000_00000000},
        PRESET_CC,
    ),
    "LXDR LXD": case_of(
        lines("LD 1,DMZERO", "LXDR 4,1", "LGDR 2,4", "LGDR 3,6")
        + lines("LXD 8,DPAT", "LGDR 5,8", "LGDR 6,10")
        + lines("LXD 8,DZ42", "LGDR 7,8", "LGDR 8,10"),
        {
            2: 0x80000000_00000000,
            3: 0x80000000_00000000,
            5: 0x41100000_12345678,
            6: 0x33000000_00000000,
            7: 0,
            8: 0,
        },
        PRESET_CC,
    ),
    "LXER LXE": case_of(
        lines("LE 1,EM1", "LXER 4,1", "LGDR 2,4", "LGDR 3,6")
        + lines("LXE 8,EZ41", "LGDR 5,8", "LGDR 6,10"),
        {2: 0xC1100000_00000000, 3: 0xB3000000_00000000, 5: 0, 6: 0},
        PRESET_CC,
    ),
}

ROUNDED: Mapping[str, Case] = {
    "LEDR LRER": case_of(
        lines("LD 1,DRND", "LD 2,DPAT", "LEDR 2,1", "LGDR 3,2")
        + lines("LD 1,DCARRY", "LD 2,DPAT", "LRER 2,1", "LGDR 4,2"),
        {3: 0x41100001_12345678, 4: 0xC2100000_12345678},
        PRESET_CC,
    ),
    "LDXR LRDR": case_of(
        extended_from(4, "XRND")
        + lines("LDXR 1,4", "LGDR 2,1")
        + extended_from(8, "XCARRY")
        + lines("LRDR 3,8", "LGDR 3,3"),
        {2: 0x41100000_00000001, 3: 0x42100000_00000000},
        PRESET_CC,
    ),
    "LEXR": case_of(
        extended_from(4, "XRNDE") + lines("LD 1,DPAT", "LEXR 1,4", "LGDR 2,1"),
        {2: 0x41100001_12345678},
        PRESET_CC,
    ),
}

CASES: Mapping[str, Case] = {
    **TO_FIXED,
    **TO_BFP,
    **FROM_FIXED,
    **FROM_BFP,
    **LENGTHENED,
    **ROUNDED,
}

TRAPS: Mapping[str, Case] = {
    "LEDR exponent overflow stores the wrapped characteristic": (
        PRESET + zeroed_short(2) + lines("LD 1,DMAXR", "LEDR 2,1"),
        {2: high_word(0x00100000)},
        PRESET_CC,
    ),
}


def expected_trap(case: str) -> tuple[HlasmRun, int, Mapping[int, int]]:
    fprs, cc = TRAPS[case][1:]
    return HlasmRun(return_code=0, abend=EXPONENT_OVERFLOW, stdout=""), cc, fprs


def expected(case: str) -> HlasmMachine:
    registers, cc = CASES[case][1:3]
    return HlasmMachine(
        HlasmRun(return_code=0, abend=COMPLETED, stdout=""), cc, registers
    )
