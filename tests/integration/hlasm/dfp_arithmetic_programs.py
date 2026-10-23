# pyright: standard
"""DFP arithmetic programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; FPRs come back through LGDR, intermediate CCs through IPM, and every program first clears the FPC. Expected values are worked from the Principles of Operation, chapter 20, with images per figures 20-1 and 20-32."""

from collections.abc import Mapping

from tests.integration.hlasm.bfp_arithmetic_programs import (
    DATA_EXCEPTION,
    INEXACT_FLAG,
    PRESET_CC,
    Case,
    Trap,
    case_of,
    cc_into,
    cc_word,
    extended_from,
    lines,
    set_fpc,
    trap_of,
)
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import ABEND, based_program

QUANTUM_FLAG = 0x00040000
UNDERFLOW_FLAG = 0x00100000

ONE = 0x22380000_00000001
TWO = 0x22380000_00000002
THREE = 0x22380000_00000003
MINUS_ONE = 0xA2380000_00000001
MINUS_ZERO = 0xA2380000_00000000
QNAN = 0x7C000000_00000005
SNAN = 0x7E000000_00000009
THIRD = 0x2DF9B36C_DB36CDB3
LARGEST = 0x77FCFF3F_CFF3FCFF
EXTENDED_ONE = 0x22080000_00000000
EXTENDED_ZERO = 0x22080000_00000000

DATA = (
    "         DS    0D\n"
    "D1       DC    X'2238000000000001'\n"
    "D2       DC    X'2238000000000002'\n"
    "D3       DC    X'2238000000000003'\n"
    "DM1      DC    X'A238000000000001'\n"
    "D10      DC    X'2238000000000010'\n"
    "D1P23    DC    X'22300000000000A3'\n"
    "D0       DC    X'2238000000000000'\n"
    "DTHIRD   DC    X'2DF9B36CDB36CDB3'\n"
    "DQNAN    DC    X'7C00000000000005'\n"
    "DSNAN    DC    X'7E00000000000009'\n"
    "DINF     DC    X'7800000000000000'\n"
    "DMAX     DC    X'77FCFF3FCFF3FCFF'\n"
    "DTINY    DC    X'6400FF3FCFF3FCFF'\n"
    "DNINES   DC    X'6E38FF3FCFF3FCFF'\n"
    "DTIE     DC    X'21F8000000000005'\n"
    "D1P0     DC    X'2234000000000010'\n"
    "DINFX    DC    X'79FC000000000005'\n"
    "DNONC    DC    X'223800000000016E'\n"
    "D2P5     DC    X'2234000000000025'\n"
    "DM2P5    DC    X'A2340000',X'00000025'\n"
    "DQ16     DC    X'21F8000000000001'\n"
    "DSUB     DC    X'0000000000000001'\n"
    "DNMIN    DC    X'003C000000000001'\n"
    "DBELOW   DC    X'0038000000000001'\n"
    "DZEXT    DC    X'0000000000000000'\n"
    "S1       DC    X'22500001'\n"
    "X1       DC    X'22080000000000000000000000000001'\n"
    "X2       DC    X'22080000000000000000000000000002'\n"
    "X3       DC    X'22080000000000000000000000000003'\n"
    "XM1      DC    X'A2080000000000000000000000000001'\n"
    "XP0      DC    X'2207C000000000000000000000000010'\n"
)


def program(body: str) -> str:
    return based_program(body, ABEND + DATA)


ARITHMETIC: Mapping[str, Case] = {
    "ADTR ADTRA": case_of(
        lines("LD 1,D1", "LD 2,D2", "ADTR 3,1,2", "LGDR 2,3")
        + cc_into(8)
        + lines("LD 5,D1P23", "LD 6,DM1", "ADTRA 4,5,6,1", "LGDR 3,4"),
        {2: THREE, 8: cc_word(2), 3: 0x22300000_00000023},
        2,
    ),
    "AXTR AXTRA": case_of(
        extended_from(1, "X1")
        + extended_from(4, "X2")
        + lines("AXTR 8,1,4", "LGDR 2,8", "LGDR 3,10")
        + cc_into(9)
        + extended_from(4, "XM1")
        + lines("AXTRA 8,1,4,3", "LGDR 4,8", "LGDR 5,10"),
        {2: 0x22080000_00000000, 3: 3, 9: cc_word(2), 4: EXTENDED_ZERO, 5: 0},
        0,
    ),
    "SDTR SDTRA": case_of(
        lines("LD 1,D1", "LD 2,D2", "SDTR 3,1,2", "LGDR 2,3")
        + cc_into(8)
        + lines("SDTRA 4,1,1,7", "LGDR 3,4"),
        {2: MINUS_ONE, 8: cc_word(1), 3: MINUS_ZERO},
        0,
    ),
    "SXTR SXTRA": case_of(
        extended_from(1, "X3")
        + extended_from(4, "X1")
        + lines("SXTR 8,1,4", "LGDR 2,8", "LGDR 3,10")
        + cc_into(9)
        + lines("SXTRA 8,4,1,1", "LGDR 4,8", "LGDR 5,10"),
        {2: EXTENDED_ONE, 3: 2, 9: cc_word(2), 4: 0xA2080000_00000000, 5: 2},
        1,
    ),
    "MDTR MDTRA": case_of(
        lines("LD 1,D1P23", "LD 2,D10", "MDTR 3,1,2", "LGDR 2,3")
        + lines("LD 4,DTHIRD", "MDTRA 5,1,4,5", "LGDR 3,5"),
        {2: 0x22300000_00000530, 3: 0x31F85F3F_CFF3FCFF},
        PRESET_CC,
        INEXACT_FLAG | QUANTUM_FLAG,
    ),
    "MXTR MXTRA": case_of(
        extended_from(1, "X2")
        + extended_from(4, "X3")
        + lines("MXTR 8,1,4", "LGDR 2,8", "LGDR 3,10")
        + lines("MXTRA 8,4,4,9", "LGDR 4,8", "LGDR 5,10"),
        {2: EXTENDED_ONE, 3: 6, 4: EXTENDED_ONE, 5: 9},
        PRESET_CC,
    ),
    "DDTR DDTRA": case_of(
        lines("LD 1,D1", "LD 2,D3", "DDTR 3,1,2", "LGDR 2,3")
        + lines("LD 4,D2", "DDTRA 5,4,2,1", "LGDR 3,5"),
        {2: THIRD, 3: 0x39FB66D9_B66D9B67},
        PRESET_CC,
        INEXACT_FLAG | QUANTUM_FLAG,
    ),
    "DXTR DXTRA": case_of(
        extended_from(1, "X3")
        + extended_from(4, "X1")
        + lines("DXTR 8,1,4", "LGDR 2,8", "LGDR 3,10")
        + extended_from(4, "XM1")
        + lines("DXTRA 8,1,4,12", "LGDR 4,8", "LGDR 5,10"),
        {2: EXTENDED_ONE, 3: 3, 4: 0xA2080000_00000000, 5: 3},
        PRESET_CC,
    ),
    "DDTR rounds a tiny quotient up to Nmin": case_of(
        lines("LD 1,DTINY", "LD 2,D10", "DDTR 3,1,2", "LGDR 2,3"),
        {2: 0x04000000_00000000},
        PRESET_CC,
        UNDERFLOW_FLAG | INEXACT_FLAG,
    ),
    "ADTR NaNs and infinity set CC 3 and 2": case_of(
        lines("LD 1,DQNAN", "LD 2,D1", "ADTR 3,2,1", "LGDR 2,3")
        + cc_into(8)
        + lines("LD 1,DINF", "SDTR 3,2,1", "LGDR 3,3")
        + cc_into(9)
        + lines("LD 1,DSNAN", "ADTR 3,1,2", "LGDR 4,3"),
        {
            2: QNAN,
            8: cc_word(3),
            3: 0xF8000000_00000000,
            9: cc_word(1),
            4: 0x7C000000_00000009,
        },
        3,
        0x00800000,
    ),
    "ADTR rounds a tie by the FPC DFP mode": case_of(
        set_fpc(0x40) + lines("LD 1,D1", "LD 2,DTIE", "ADTR 3,1,2", "LGDR 2,3"),
        {2: 0x25FC0000_00000001},
        2,
        INEXACT_FLAG | 0x40,
    ),
    "MDTRA keeps an exact product off its quantum": case_of(
        lines("LD 1,DNINES", "LD 2,D10", "MDTRA 3,1,2,4", "LGDR 2,3"),
        {2: 0x6E3CFF3F_CFF3FCFF},
        PRESET_CC,
        QUANTUM_FLAG,
    ),
}

GR_MODULUS = 1 << 64

COMPARE_EXPONENT: Mapping[str, Case] = {
    "CDTR KDTR": case_of(
        lines("LD 1,D1", "LD 2,D2", "CDTR 1,2")
        + cc_into(8)
        + lines("LD 2,D1P0", "CDTR 1,2")
        + cc_into(9)
        + lines("LD 2,DQNAN", "CDTR 1,2")
        + cc_into(10)
        + lines("KDTR 1,2"),
        {8: cc_word(1), 9: cc_word(0), 10: cc_word(3)},
        3,
        0x00800000,
    ),
    "CXTR KXTR": case_of(
        extended_from(1, "X2")
        + extended_from(4, "X1")
        + lines("CXTR 1,4")
        + cc_into(8)
        + lines("KXTR 4,1"),
        {8: cc_word(2)},
        1,
    ),
    "CEDTR CEXTR": case_of(
        lines("LD 1,D1", "LD 2,D1P0", "CEDTR 1,2")
        + cc_into(8)
        + lines("LD 1,DINF", "CEDTR 1,1")
        + cc_into(9)
        + lines("LD 1,DQNAN", "LD 2,DSNAN", "CEDTR 1,2")
        + cc_into(10)
        + lines("LD 1,D1", "LD 2,DINF", "CEDTR 1,2")
        + cc_into(11)
        + extended_from(4, "XP0")
        + extended_from(1, "X1")
        + lines("CEXTR 4,1"),
        {8: cc_word(2), 9: cc_word(0), 10: cc_word(0), 11: cc_word(3)},
        1,
    ),
    "LTDTR LTXTR": case_of(
        lines("LD 1,DINFX", "LTDTR 3,1", "LGDR 2,3")
        + cc_into(8)
        + lines("LD 1,DNONC", "LTDTR 3,1", "LGDR 3,3")
        + cc_into(9)
        + extended_from(4, "XM1")
        + lines("LTXTR 8,4", "LGDR 4,8", "LGDR 5,10")
        + cc_into(10)
        + lines("LD 1,DSNAN", "LTDTR 3,1", "LGDR 6,3"),
        {
            2: 0x78000000_00000000,
            8: cc_word(2),
            3: 0x22380000_0000006E,
            9: cc_word(2),
            4: 0xA2080000_00000000,
            5: 1,
            10: cc_word(1),
            6: 0x7C000000_00000009,
        },
        3,
        0x00800000,
    ),
    "EEDTR EEXTR": case_of(
        lines("LD 1,D1", "EEDTR 2,1", "LD 1,DSNAN", "EEDTR 3,1")
        + lines("LD 1,DINF", "EEDTR 4,1")
        + extended_from(8, "X1")
        + lines("EEXTR 5,8"),
        {2: 398, 3: GR_MODULUS - 3, 4: GR_MODULUS - 1, 5: 6176},
        PRESET_CC,
    ),
    "ESDTR ESXTR": case_of(
        lines("LD 1,D1P23", "ESDTR 2,1", "LD 1,D0", "ESDTR 3,1")
        + lines("LD 1,DQNAN", "ESDTR 4,1", "LD 1,DNINES", "ESDTR 5,1")
        + extended_from(8, "X3")
        + lines("ESXTR 6,8"),
        {2: 3, 3: 0, 4: GR_MODULUS - 2, 5: 16, 6: 1},
        PRESET_CC,
    ),
    "IEDTR IEXTR": case_of(
        lines("LD 1,D1P23", "LGHI 2,397", "IEDTR 3,1,2", "LGDR 4,3")
        + lines("LGHI 2,-1", "IEDTR 3,1,2", "LGDR 5,3")
        + lines("LGHI 2,-3", "IEDTR 3,1,2", "LGDR 6,3")
        + lines("LGHI 2,768", "IEDTR 3,1,2", "LGDR 7,3")
        + extended_from(8, "X3")
        + lines("LGHI 2,6175", "IEXTR 12,8,2", "LGDR 8,12", "LGDR 9,14"),
        {
            4: 0x22340000_000000A3,
            5: 0x78000000_000000A3,
            6: 0x7E000000_000000A3,
            7: 0x7C000000_000000A3,
            8: 0x2207C000_00000000,
            9: 3,
        },
        PRESET_CC,
    ),
}

ROUNDING: Mapping[str, Case] = {
    "FIDTR FIXTR": case_of(
        lines("LD 1,D2P5", "FIDTR 3,0,1,0", "LD 1,DM2P5", "FIDTR 4,5,1,4")
        + extended_from(8, "XP0")
        + lines("FIXTR 12,0,8,0", "LGDR 2,3", "LGDR 3,4", "LGDR 4,12", "LGDR 5,14"),
        {2: TWO, 3: 0xA2380000_00000002, 4: EXTENDED_ONE, 5: 1},
        PRESET_CC,
        INEXACT_FLAG | QUANTUM_FLAG,
    ),
    "QADTR QAXTR": case_of(
        lines("LD 1,D1P23", "LD 2,D1P0", "QADTR 3,1,2,0", "LD 5,D1", "QADTR 4,1,5,1")
        + lines("LD 7,DQ16", "QADTR 6,1,7,0")
        + extended_from(8, "X3")
        + extended_from(12, "XP0")
        + lines("QAXTR 0,8,12,0", "LGDR 2,3", "LGDR 3,4", "LGDR 4,6")
        + lines("LGDR 5,0", "LGDR 6,2"),
        {
            2: 0x22340000_00000012,
            3: ONE,
            4: 0x7C000000_00000000,
            5: 0x2207C000_00000000,
            6: 0x30,
        },
        PRESET_CC,
        0x00800000 | INEXACT_FLAG | QUANTUM_FLAG,
    ),
    "RRDTR RRXTR": case_of(
        lines("LD 1,D1P23", "LGHI 2,66", "RRDTR 3,1,2,0", "LGHI 2,0", "RRDTR 4,1,2,0")
        + extended_from(8, "X3")
        + lines("LGHI 2,5", "RRXTR 12,8,2,0", "LGDR 4,3", "LGDR 5,4")
        + lines("LGDR 6,12", "LGDR 7,14"),
        {4: 0x22340000_00000012, 5: 0x22300000_000000A3, 6: EXTENDED_ONE, 7: 3},
        PRESET_CC,
        INEXACT_FLAG,
    ),
}


def _tests(mnemonic: str, tests: tuple[tuple[str, str, int], ...]) -> str:
    return "".join(
        lines(f"{load} 1,{label}", f"{mnemonic} 1,X'{mask:03X}'") + cc_into(2 + at)
        for at, (load, label, mask) in enumerate(tests)
    )


DIGITS: Mapping[str, Case] = {
    "SLDT SLXT": case_of(
        lines("LD 1,D1P23", "SLDT 3,1,66", "LGDR 2,3", "SLDT 3,1,15", "LGDR 3,3")
        + lines("LD 1,DQNAN", "SLDT 3,1,1", "LGDR 4,3")
        + lines("LD 1,DINFX", "SLDT 3,1,2", "LGDR 5,3")
        + extended_from(8, "X3")
        + lines("SLXT 12,8,33", "LGDR 6,12", "LGDR 7,14"),
        {
            2: 0x22300000_00004980,
            3: 0x2E300000_00000000,
            4: 0x7C000000_00000050,
            5: 0x78000000_00000280,
            6: 0x2E080000_00000000,
            7: 0,
        },
        PRESET_CC,
    ),
    "SRDT SRXT": case_of(
        lines("LD 1,D1P23", "SRDT 3,1,1", "LGDR 2,3", "SRDT 3,1,66", "LGDR 3,3")
        + lines("LD 1,DQNAN", "SRDT 3,1,1", "LGDR 4,3")
        + extended_from(8, "X3")
        + lines("SRXT 12,8,1", "LGDR 5,12", "LGDR 6,14"),
        {
            2: 0x22300000_00000012,
            3: 0x22300000_00000001,
            4: 0x7C000000_00000000,
            5: EXTENDED_ZERO,
            6: 0,
        },
        PRESET_CC,
    ),
    "TDCDT TDCET TDCXT": case_of(
        _tests(
            "TDCDT",
            (
                ("LD", "D1", 0x080),
                ("LD", "DM1", 0x080),
                ("LD", "DSUB", 0x200),
                ("LD", "DSNAN", 0x002),
                ("LD", "DQNAN", 0xFF7),
                ("LD", "DINF", 0x020),
                ("LD", "DNMIN", 0x080),
                ("LD", "DBELOW", 0x200),
            ),
        )
        + lines("LE 1,S1", "TDCET 1,X'080'")
        + cc_into(10)
        + extended_from(4, "XM1")
        + lines("TDCXT 4,X'040'"),
        {
            2: cc_word(1),
            3: cc_word(0),
            4: cc_word(1),
            5: cc_word(1),
            6: cc_word(0),
            7: cc_word(1),
            8: cc_word(1),
            9: cc_word(1),
            10: cc_word(1),
        },
        1,
    ),
    "TDGDT TDGET TDGXT": case_of(
        _tests(
            "TDGDT",
            (
                ("LD", "D0", 0x800),
                ("LD", "DZEXT", 0x200),
                ("LD", "DSUB", 0x080),
                ("LD", "D1", 0x020),
                ("LD", "DNINES", 0x008),
                ("LD", "DINF", 0x002),
                ("LD", "DMAX", 0x080),
            ),
        )
        + lines("LE 1,S1", "TDGET 1,X'020'")
        + cc_into(9)
        + extended_from(4, "XM1")
        + lines("TDGXT 4,X'010'"),
        {r: cc_word(1) for r in range(2, 10)},
        1,
    ),
}

CASES: Mapping[str, Case] = {**ARITHMETIC, **COMPARE_EXPONENT, **ROUNDING, **DIGITS}

TRAPS: Mapping[str, Trap] = {
    "compare suppresses on an SNaN and leaves the CC": trap_of(
        lines("LD 1,D1", "LD 2,DSNAN", "CDTR 1,2"), {}, 0x80008000
    ),
    "compare and signal traps on a QNaN": trap_of(
        lines("LD 1,D1", "LD 2,DQNAN", "KDTR 1,2"), {}, 0x80008000
    ),
    "load FP integer traps inexact": trap_of(
        lines("LD 1,D2P5", "FIDTR 3,0,1,0"), {3: TWO}, 0x08000800
    ),
    "load FP integer with XxC traps the quantum": trap_of(
        lines("LD 1,D2P5", "FIDTR 3,5,1,4"), {3: TWO}, 0x04000400
    ),
    "quantize invalid suppresses": trap_of(
        lines("LD 3,D2", "LD 1,D1P23", "LD 7,DQ16", "QADTR 3,1,7,0"),
        {3: TWO},
        0x80008000,
    ),
    "load and test suppresses on an SNaN": trap_of(
        lines("LD 3,D2", "LD 1,DSNAN", "LTDTR 3,1"), {3: TWO}, 0x80008000
    ),
    "invalid suppresses": trap_of(
        lines("LD 1,DSNAN", "LD 2,D1", "LD 3,D2", "ADTR 3,1,2"), {3: TWO}, 0x80008000
    ),
    "division by zero suppresses": trap_of(
        lines("LD 1,D1", "LD 2,D0", "LD 3,D2", "DDTR 3,1,2"), {3: TWO}, 0x40004000
    ),
    "overflow delivers the scaled result": trap_of(
        lines("LD 1,DMAX", "LD 2,D10", "MDTR 3,1,2"),
        {3: 0x6700FF3F_CFF3FCFF},
        0x20002000,
    ),
    "underflow delivers the scaled result": trap_of(
        lines("LD 1,DTINY", "LD 2,D10", "DDTR 3,1,2"),
        {3: 0x74FCFF3F_CFF3FCFF},
        0x10001000,
    ),
    "add overflow sets the cc from the scaled result": trap_of(
        lines("LD 1,DMAX", "ADTR 3,1,1"),
        {3: 0x0B000000_00000000},
        0x20002C00,
        2,
    ),
    "inexact traps after the store": trap_of(
        lines("LD 1,D1", "LD 2,D3", "DDTR 3,1,2"), {3: THIRD}, 0x08000800
    ),
    "quantum traps after the store on an A form": trap_of(
        lines("LD 1,D1", "LD 2,D3", "DDTRA 3,1,2,4"), {3: THIRD}, 0x04080400
    ),
    "an inexact trap takes the place of the quantum trap": trap_of(
        lines("LD 1,D1", "LD 2,D3", "DDTRA 3,1,2,4"), {3: THIRD}, 0x0C000800
    ),
    "quantum traps on an exact product off its quantum": trap_of(
        lines("LD 1,DNINES", "LD 2,D10", "MDTRA 3,1,2,4"),
        {3: 0x6E3CFF3F_CFF3FCFF},
        0x04000400,
    ),
}


def expected_trap(case: str) -> tuple[HlasmRun, int, Mapping[int, int], int]:
    fprs, cc, fpc = TRAPS[case][1:]
    return HlasmRun(return_code=0, abend=DATA_EXCEPTION, stdout=""), cc, fprs, fpc


def expected(case: str) -> HlasmMachine:
    registers, cc, abend = CASES[case][1:4]
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)
