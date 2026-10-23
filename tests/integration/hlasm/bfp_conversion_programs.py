# pyright: standard
"""BFP conversion programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; results come back in GRs (FPRs through LGDR), intermediate CCs through IPM, and every program first clears the FPC."""

from collections.abc import Mapping

from tests.integration.hlasm.bfp_arithmetic_programs import (
    DATA,
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
    high_word,
    lines,
    set_fpc,
    trap_of,
    zeroed_short,
)
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import (
    ABEND,
    FILL,
    HIGH_FILL,
    based_program,
)

BOTH_FLAGS = INVALID_FLAG | INEXACT_FLAG

CONVERSION_DATA = (
    "         DS    0D\n"
    "DMPH     DC    X'41DFFFFFFFE00000'\n"
    "DU32     DC    X'41EFFFFFFFE00000'\n"
    "D3P5     DC    X'400C000000000000'\n"
    "XM0      DC    X'80000000000000000000000000000000'\n"
    "XM1      DC    X'BFFF0000000000000000000000000000'\n"
    "XQNAN    DC    X'7FFF8000000000000000000000000000'\n"
    "XMINF    DC    X'FFFF0000000000000000000000000000'\n"
    "S2P63    DC    X'5F000000'\n"
    "SM2P63   DC    X'DF000000'\n"
    "S2P64    DC    X'5F800000'\n"
    "SMHALF   DC    X'BF000000'\n"
    "SSNAN    DC    X'7F800001'\n"
    "SMQNAN   DC    X'FFC00001'\n"
    "         DS    0D\n"
    "XTINY    DC    X'3BE50000000000000000000000000000'\n"
)


def program(body: str) -> str:
    return based_program(body, ABEND + DATA + CONVERSION_DATA)


def _low(value: int) -> int:
    return HIGH_FILL | value


def _trapped(body: str, registers: Mapping[int, int], cc: int, fpc: int) -> Case:
    trapping = set_fpc(fpc & 0xFF000000) + body
    return (*case_of(trapping, registers, cc)[:3], DATA_EXCEPTION, fpc)


TO_FIXED: Mapping[str, Case] = {
    "CFEBR CFEBRA": case_of(
        lines("LE 1,SM2P5", "CFEBR 2,0,1") + cc_into(8) + lines("CFEBRA 3,1,1,4"),
        {2: _low(0xFFFFFFFE), 8: cc_word(1), 3: _low(0xFFFFFFFD)},
        1,
        INEXACT_FLAG,
    ),
    "CFDBR CFDBRA": case_of(
        lines("LD 1,DMPH", "CFDBR 2,0,1") + cc_into(8) + lines("CFDBRA 3,5,1,0"),
        {2: _low(0x7FFFFFFF), 8: cc_word(3), 3: _low(0x7FFFFFFF)},
        2,
        BOTH_FLAGS,
    ),
    "CFXBR CFXBRA": case_of(
        extended_from(4, "XM0")
        + lines("CFXBR 2,0,4")
        + cc_into(8)
        + extended_from(4, "XQNAN")
        + lines("CFXBRA 3,0,4,4"),
        {2: _low(0), 8: cc_word(0), 3: _low(0x80000000)},
        3,
        INVALID_FLAG,
    ),
    "CGEBR CGEBRA": case_of(
        lines("LE 1,S2P63", "CGEBR 2,0,1")
        + cc_into(8)
        + lines("LE 1,SM2P63", "CGEBRA 3,0,1,0"),
        {2: 0x7FFFFFFF_FFFFFFFF, 8: cc_word(3), 3: 0x80000000_00000000},
        1,
        BOTH_FLAGS,
    ),
    "CGDBR CGDBRA in the current mode": case_of(
        set_fpc(1)
        + lines("LD 1,D3P5", "CGDBR 2,0,1")
        + cc_into(8)
        + lines("CGDBR 4,4,1", "LD 1,DM1", "CGDBRA 3,6,1,0"),
        {2: 3, 8: cc_word(2), 4: 4, 3: 0xFFFFFFFF_FFFFFFFF},
        1,
        INEXACT_FLAG | 1,
    ),
    "CGXBR CGXBRA": case_of(
        extended_from(4, "X3")
        + lines("CGXBR 2,0,4")
        + cc_into(8)
        + extended_from(4, "XMINF")
        + lines("CGXBRA 3,0,4,0"),
        {2: 3, 8: cc_word(2), 3: 0x80000000_00000000},
        3,
        BOTH_FLAGS,
    ),
    "CLFEBR": case_of(
        lines("LE 1,SMHALF", "CLFEBR 2,5,1,0")
        + cc_into(8)
        + lines("LE 1,S2P63", "CLFEBR 3,0,1,0"),
        {2: _low(0), 8: cc_word(1), 3: _low(0xFFFFFFFF)},
        3,
        BOTH_FLAGS,
    ),
    "CLFDBR": case_of(
        lines("LD 1,DU32", "CLFDBR 2,0,1,0")
        + cc_into(8)
        + lines("LD 1,DM1", "CLFDBR 3,0,1,4"),
        {2: _low(0xFFFFFFFF), 8: cc_word(2), 3: _low(0)},
        3,
        INVALID_FLAG,
    ),
    "CLFXBR": case_of(
        extended_from(4, "X3")
        + lines("CLFXBR 2,0,4,0")
        + cc_into(8)
        + extended_from(4, "XM1")
        + lines("CLFXBR 3,0,4,0"),
        {2: _low(3), 8: cc_word(2), 3: _low(0)},
        3,
        BOTH_FLAGS,
    ),
    "CLGEBR": case_of(
        lines("LE 1,S2P64", "CLGEBR 2,0,1,0")
        + cc_into(8)
        + lines("LE 1,S2P63", "CLGEBR 3,0,1,0"),
        {2: 0xFFFFFFFF_FFFFFFFF, 8: cc_word(3), 3: 0x80000000_00000000},
        2,
        BOTH_FLAGS,
    ),
    "CLGDBR": case_of(
        lines("LD 1,DQNAN", "CLGDBR 2,0,1,0")
        + cc_into(8)
        + lines("LD 1,D7", "CLGDBR 3,0,1,0"),
        {2: 0, 8: cc_word(3), 3: 7},
        2,
        BOTH_FLAGS,
    ),
    "CLGXBR": case_of(
        extended_from(4, "XM0")
        + lines("CLGXBR 2,0,4,0")
        + cc_into(8)
        + extended_from(4, "X3")
        + lines("CLGXBR 3,7,4,0"),
        {2: 0, 8: cc_word(0), 3: 3},
        2,
    ),
    "CFDBR of a negative NaN gives MN": case_of(
        lines("LD 1,DMQNAN", "CFDBR 2,0,1"),
        {2: _low(0x80000000)},
        3,
        BOTH_FLAGS,
    ),
    "CFDBR CGDBRA prepare for shorter precision": case_of(
        lines("LD 1,D2P5", "CFDBR 2,3,1", "LD 1,D3P5", "CGDBRA 3,3,1,0"),
        {2: _low(3), 3: 3},
        2,
        INEXACT_FLAG,
    ),
    "CLFDBR inexact control under an enabled mask": case_of(
        set_fpc(0x08000000) + lines("LD 1,D3P5", "CLFDBR 2,0,1,4"),
        {2: _low(4)},
        2,
        0x08000000,
    ),
    "CFDBR invalid suppresses": _trapped(
        lines("LD 1,DQNAN", "CFDBR 2,0,1"), {2: FILL}, PRESET_CC, 0x80008000
    ),
    "CGDBR masked invalid takes the inexact trap after the store": _trapped(
        lines("LD 1,DQNAN", "CGDBR 2,0,1"),
        {2: 0x80000000_00000000},
        3,
        0x08800800,
    ),
    "CFDBR inexact traps after the store": _trapped(
        lines("LD 1,D3P5", "CFDBR 2,0,1"), {2: _low(4)}, 2, 0x08000C00
    ),
}

FROM_FIXED: Mapping[str, Case] = {
    "CEFBR CEFBRA": case_of(
        zeroed_short(1, 4)
        + lines("IILF 2,X'01000001'", "CEFBR 1,2", "LGDR 3,1")
        + lines("CEFBRA 4,6,2,4", "LGDR 5,4"),
        {3: high_word(0x4B800000), 5: high_word(0x4B800001)},
        PRESET_CC,
        INEXACT_FLAG,
    ),
    "CEGBR CEGBRA": case_of(
        zeroed_short(1, 4)
        + lines("LLIHF 2,X'80000000'", "CEGBR 1,2", "LGDR 3,1")
        + lines("LLIHF 2,X'7FFFFFFF'", "IILF 2,X'FFFFFFFF'", "CEGBRA 4,5,2,0")
        + lines("LGDR 5,4"),
        {3: high_word(0xDF000000), 5: high_word(0x5EFFFFFF)},
        PRESET_CC,
        INEXACT_FLAG,
    ),
    "CDGBR CDGBRA": case_of(
        lines("LLIHF 2,X'00200000'", "IILF 2,1", "CDGBR 1,2", "LGDR 4,1")
        + lines("LCGR 3,2", "CDGBRA 5,7,3,0", "LGDR 5,5"),
        {4: 0x43400000_00000000, 5: 0xC3400000_00000001},
        1,
        INEXACT_FLAG,
    ),
    "CELFBR CELGBR CDLGBR": case_of(
        zeroed_short(1, 4)
        + lines("IILF 2,X'FFFFFFFF'", "CELFBR 1,0,2,0", "LGDR 2,1")
        + lines("LGHI 3,-1", "CELGBR 4,0,3,4", "LGDR 4,4")
        + lines("CDLGBR 5,5,3,0", "LGDR 5,5"),
        {2: high_word(0x4F800000), 4: high_word(0x5F800000), 5: 0x43EFFFFF_FFFFFFFF},
        PRESET_CC,
        INEXACT_FLAG,
    ),
    "CEFBRA prepare for shorter precision": case_of(
        zeroed_short(1) + lines("IILF 2,X'01000001'", "CEFBRA 1,3,2,0", "LGDR 3,1"),
        {3: high_word(0x4B800001)},
        PRESET_CC,
        INEXACT_FLAG,
    ),
    "CDFBR CDFBRA": case_of(
        lines("IILF 2,X'FFFFFFFF'", "CDFBR 1,2", "LGDR 2,1")
        + lines("IILF 3,X'80000000'", "CDFBRA 4,7,3,0", "LGDR 3,4")
        + lines("IILF 5,0", "CDFBR 6,5", "LGDR 4,6"),
        {2: 0xBFF00000_00000000, 3: 0xC1E00000_00000000, 4: 0},
        PRESET_CC,
    ),
    "CDLFBR": case_of(
        lines("IILF 2,X'FFFFFFFF'", "CDLFBR 1,0,2,0", "LGDR 2,1"),
        {2: 0x41EFFFFF_FFE00000},
        PRESET_CC,
    ),
    "CXFBR CXFBRA": case_of(
        lines("IILF 2,7", "CXFBR 1,2", "LGDR 2,1", "LGDR 3,3")
        + lines("IILF 4,X'80000000'", "CXFBRA 4,3,4,0", "LGDR 4,4", "LGDR 5,6"),
        {2: 0x4001C000_00000000, 3: 0, 4: 0xC01E0000_00000000, 5: 0},
        PRESET_CC,
    ),
    "CXGBR CXGBRA": case_of(
        lines("LLIHF 2,X'80000000'", "CXGBR 1,2", "LGDR 2,1", "LGDR 3,3")
        + lines("LLIHF 4,X'7FFFFFFF'", "IILF 4,X'FFFFFFFF'", "CXGBRA 8,0,4,4")
        + lines("LGDR 4,8", "LGDR 5,10"),
        {
            2: 0xC03E0000_00000000,
            3: 0,
            4: 0x403DFFFF_FFFFFFFF,
            5: 0xFFFC0000_00000000,
        },
        PRESET_CC,
    ),
    "CXLFBR CXLGBR": case_of(
        lines("IILF 2,X'FFFFFFFF'", "CXLFBR 1,0,2,0", "LGDR 2,1", "LGDR 3,3")
        + lines("LGHI 4,-1", "CXLGBR 8,0,4,0", "LGDR 4,8", "LGDR 5,10"),
        {
            2: 0x401EFFFF_FFFE0000,
            3: 0,
            4: 0x403EFFFF_FFFFFFFF,
            5: 0xFFFE0000_00000000,
        },
        PRESET_CC,
    ),
}

LENGTHEN_ROUND: Mapping[str, Case] = {
    "LDEBR LDEB": case_of(
        lines("LE 2,SM1P5", "LDEBR 1,2", "LGDR 2,1", "LDEB 3,STINY3", "LGDR 3,3")
        + lines("LDEB 4,SQNAN", "LGDR 4,4"),
        {2: 0xBFF80000_00000000, 3: 0x36B80000_00000000, 4: 0x7FF80000_00000000},
        PRESET_CC,
    ),
    "LDEB LXDB LXEB keep the sign of -0 and NaNs and normalise a subnormal": case_of(
        lines("LDEB 1,SM0", "LGDR 2,1", "LDEB 3,SMQNAN", "LGDR 3,3")
        + lines("LXDB 4,DMQNAN", "LGDR 4,4", "LGDR 5,6")
        + lines("LXEB 8,STINY3", "LGDR 6,8", "LGDR 7,10"),
        {
            2: 0x80000000_00000000,
            3: 0xFFF80000_20000000,
            4: 0xFFFF8000_00000000,
            5: 0x50000000_00000000,
            6: 0x3F6B8000_00000000,
            7: 0,
        },
        PRESET_CC,
    ),
    "LDEBR quiets a masked SNaN": case_of(
        lines("LE 2,SSNAN", "LDEBR 1,2", "LGDR 2,1"),
        {2: 0x7FF80000_20000000},
        PRESET_CC,
        INVALID_FLAG,
    ),
    "LXDBR LXDB": case_of(
        lines("LD 2,DSUB", "LXDBR 4,2", "LGDR 2,4", "LGDR 3,6")
        + lines("LXDB 8,DMINF", "LGDR 4,8", "LGDR 5,10"),
        {2: 0x3BCD0000_00000000, 3: 0, 4: 0xFFFF0000_00000000, 5: 0},
        PRESET_CC,
    ),
    "LXEBR LXEB": case_of(
        lines("LE 2,SM8", "LXEBR 4,2", "LGDR 2,4", "LGDR 3,6")
        + lines("LXEB 8,SQNAN", "LGDR 4,8", "LGDR 5,10"),
        {2: 0xC0020000_00000000, 3: 0, 4: 0x7FFF8000_00000000, 5: 0},
        PRESET_CC,
    ),
    "LEDBR LEDBRA": case_of(
        lines("LD 1,DTHIRD", "LEDBR 1,1", "LGDR 2,1")
        + lines("LD 3,DTHIRD", "LEDBRA 3,5,3,0", "LGDR 3,3")
        + lines("LD 4,DMAX", "LEDBR 4,4", "LGDR 4,4"),
        {2: 0x3EAAAAAB_55555555, 3: 0x3EAAAAAA_55555555, 4: 0x7F800000_FFFFFFFF},
        PRESET_CC,
        0x00280000,
    ),
    "LDXBR LDXBRA": case_of(
        extended_from(4, "X1")
        + lines("LDXBR 4,4", "LGDR 2,4", "LGDR 3,6")
        + extended_from(8, "X1")
        + lines("LDXBRA 8,6,8,0", "LGDR 4,8"),
        {2: 0x3FF00000_00000000, 3: 0x1000, 4: 0x3FF00000_00000001},
        PRESET_CC,
        INEXACT_FLAG,
    ),
    "LEXBR LEXBRA": case_of(
        extended_from(4, "XM2P5")
        + lines("LEXBR 4,4", "LGDR 2,4", "LGDR 3,6")
        + extended_from(8, "X1")
        + lines("LEXBRA 8,7,8,4", "LGDR 4,8", "LGDR 5,10"),
        {2: 0xC0200000_00000000, 3: 0, 4: 0x3F800000_00000000, 5: 0x1000},
        PRESET_CC,
    ),
}

CASES: Mapping[str, Case] = {**TO_FIXED, **FROM_FIXED, **LENGTHEN_ROUND}

TRAPS: Mapping[str, Trap] = {
    "CEFBR inexact traps after the store": trap_of(
        zeroed_short(1) + lines("IILF 2,X'01000001'", "CEFBR 1,2"),
        {1: high_word(0x4B800000)},
        0x08000800,
    ),
    "LXDBR invalid suppresses": trap_of(
        lines("LD 2,DSNAN", "LXDBR 4,2"), {4: 0, 6: 0}, 0x80008000
    ),
    "LEDBR overflow delivers the scaled long result": trap_of(
        lines("LD 1,DMAX", "LEDBR 1,1"), {1: 0x5FF00000_00000000}, 0x20002C00
    ),
    "LDXBR underflow delivers the scaled extended result": trap_of(
        extended_from(4, "XTINY") + lines("LDXBR 4,4"),
        {4: 0x5BE50000_00000000, 6: 0},
        0x10001000,
    ),
}


def expected_trap(case: str) -> tuple[HlasmRun, int, Mapping[int, int], int]:
    fprs, cc, fpc = TRAPS[case][1:]
    return HlasmRun(return_code=0, abend=DATA_EXCEPTION, stdout=""), cc, fprs, fpc


def expected(case: str) -> HlasmMachine:
    registers, cc, abend = CASES[case][1:4]
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)
