# pyright: standard
"""DFP conversion programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; results come back in GRs (FPRs through LGDR), intermediate CCs through IPM, and every program first clears the FPC. Expected values are worked from the Principles of Operation, chapter 20 (fixed point 20-24 to 20-32, figures 20-18 and 20-19), with images per figures 20-1 and 20-32."""

from collections.abc import Mapping

from tests.integration.hlasm.bfp_arithmetic_programs import (
    COMPLETED,
    DATA_EXCEPTION,
    INEXACT_FLAG,
    INVALID_FLAG,
    PRESET,
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
from tests.integration.hlasm.dfp_arithmetic_programs import (
    DATA,
    QUANTUM_FLAG,
    UNDERFLOW_FLAG,
)
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import (
    ABEND,
    FILL,
    HIGH_FILL,
    based_program,
)

OVERFLOW_FLAG = 0x00200000

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
    "D16      DC    X'263934B9C1E28E56'\n"
    "DINFP    DC    X'780000000A395BCF'\n"
    "DSNANP   DC    X'7E0000000A395BCF'\n"
    "SVAL     DC    X'A624D2E7'\n"
    "SINFX    DC    X'78000005'\n"
    "SSNAN    DC    X'FE000042'\n"
    "SQNAN    DC    X'7C000007'\n"
    "         DS    0D\n"
    "PK12345M DC    X'000000000012345D'\n"
    "PU16     DC    X'1234567890123456'\n"
    "PU32L    DC    X'7890123456789012'\n"
    "PKBAD    DC    X'00000000001A345C'\n"
    "PKSIGN   DC    X'0000000000123454'\n"
    "DM12345  DC    X'A2380000000049C5'\n"
    "XBIG     DC    X'A606D34B9C1E28E5',X'6F3C127177823534'\n"
    "DM0      DC    X'A238000000000000'\n"
    "P5M      DC    X'12345D'\n"
    "U3       DC    X'012345'\n"
    "PBIG     DC    X'012345678901234567',X'89012345678901234C'\n"
    "PUNUSED  DC    X'010000000000000000'\n"
    "Z5M      DC    X'F1F2F3F4D5'\n"
    "A5       DC    X'3030303432'\n"
    "ZBAD     DC    X'F1FAF3'\n"
    "         DS    0D\n"
    "BTENTH   DC    X'3FB999999999999A'\n"
    "BTEN     DC    X'40240000',X'00000000'\n"
    "BTWO3    DC    X'3FE5555555555555'\n"
    "BM1P5    DC    X'BFF8000000000000'\n"
    "B1E300   DC    X'7E37E43C8800759C'\n"
    "DTENTH   DC    X'25F8000000000000'\n"
    "H1       DC    X'41100000'\n"
    "D1E80    DC    X'2378000000000001'\n"
    "DM1EM80  DC    X'A0F8000000000001'\n"
    "XCDZT    CDZT  3,Z5M(1),8\n"
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

LENGTHEN_ROUND: Mapping[str, Case] = {
    "LDETR LXDTR": case_of(
        lines("LE 1,SVAL", "LDETR 2,1,0", "LXDTR 4,2,0")
        + lines("LGDR 3,2", "LGDR 4,4", "LGDR 5,6"),
        {3: 0xA22C0000_0014D2E7, 4: 0xA2074000_00000000, 5: 0x14D2E7},
        PRESET_CC,
    ),
    "LDETR keeps an infinity's digits and an SNaN only under XiC": case_of(
        lines("LE 1,SINFX", "LDETR 2,1,0", "LDETR 3,1,8", "LE 1,SSNAN")
        + lines("LDETR 4,1,8", "LE 1,SQNAN", "LDETR 5,1,0")
        + lines("LGDR 2,2", "LGDR 3,3", "LGDR 4,4", "LGDR 5,5"),
        {
            2: 0x78000000_00000000,
            3: 0x78000000_00000005,
            4: 0xFE000000_00000042,
            5: 0x7C000000_00000007,
        },
        PRESET_CC,
    ),
    "LDETR quiets an SNaN": case_of(
        lines("LE 1,SSNAN", "LDETR 2,1,0", "LGDR 2,2"),
        {2: 0xFC000000_00000042},
        PRESET_CC,
        INVALID_FLAG,
    ),
    "LEDTR LDXTR": case_of(
        lines("LD 1,D16", "LD 2,D1", "LEDTR 2,0,1,0", "LGDR 3,2")
        + extended_from(4, "X3")
        + lines("LDXTR 4,0,4,0", "LGDR 4,4", "LGDR 5,6"),
        {3: 0x26E4D2E8_00000001, 4: 0x22380000_00000003, 5: 3},
        PRESET_CC,
        INEXACT_FLAG,
    ),
    "LEDTR keeps an infinity's and an SNaN's last digits only under XiC": case_of(
        lines("LZDR 2", "LZDR 3", "LZDR 4", "LD 1,DINFP", "LEDTR 2,0,1,0")
        + lines("LEDTR 3,0,1,8", "LD 1,DSNANP", "LEDTR 4,0,1,8")
        + lines("LGDR 2,2", "LGDR 3,3", "LGDR 4,4"),
        {2: 0x78000000_00000000, 3: 0x78095BCF_00000000, 4: 0x7E095BCF_00000000},
        PRESET_CC,
    ),
}

REGISTER_DECIMAL: Mapping[str, Case] = {
    "CDSTR CDUTR": case_of(
        lines("LG 2,PK12345M", "CDSTR 1,2", "LG 3,PU16", "CDUTR 4,3")
        + lines("LGDR 2,1", "LGDR 3,4"),
        {2: 0xA2380000_000049C5, 3: 0x263934B9_C1E28E56},
        PRESET_CC,
    ),
    "CXSTR CXUTR": case_of(
        lines("LGHI 4,0", "LGHI 5,X'123C'", "CXSTR 8,4", "LGDR 2,8", "LGDR 3,10")
        + lines("LG 6,PU16", "LG 7,PU32L", "CXUTR 8,6", "LGDR 4,8", "LGDR 5,10"),
        {
            2: 0x22080000_00000000,
            3: 0xA3,
            4: 0x22080127_17782353,
            5: 0x4B9C1E28_E56F3C12,
        },
        PRESET_CC,
    ),
    "CSDTR CUDTR": case_of(
        lines("LD 1,DM12345", "CSDTR 2,1,0", "LD 1,D16", "CSDTR 3,1,1")
        + lines("CUDTR 4,1", "LD 1,DQNAN", "CUDTR 5,1"),
        {2: 0x12345D, 3: 0x23456789_0123456F, 4: 0x12345678_90123456, 5: 5},
        PRESET_CC,
    ),
    "CSXTR CUXTR": case_of(
        extended_from(8, "XBIG") + lines("CSXTR 4,8,0", "CUXTR 6,8"),
        {
            4: 0x45678901_23456789,
            5: 0x01234567_8901234D,
            6: 0x34567890_12345678,
            7: 0x90123456_78901234,
        },
        PRESET_CC,
    ),
}

DXC_PRESET = set_fpc(0x00000C00)
MASK_OFF = lines("LA 1,0", "SPM 1")


def _ended(body: str, cc: int, abend: str) -> Case:
    return (*case_of(body, {}, cc)[:3], abend, 0)


STORAGE_DECIMAL: Mapping[str, Case] = {
    "CDPT CXPT": case_of(
        lines("CDPT 1,P5M(3),8", "CDPT 2,U3(3),0", "CDPT 3,P5M(3),9")
        + lines("CXPT 4,PBIG(18),8", "LGDR 2,1", "LGDR 3,2", "LGDR 5,3")
        + lines("LGDR 6,4", "LGDR 7,6"),
        {
            2: 0xA2380000_000049C5,
            3: 0x22380000_000049C5,
            5: 0x22380000_000049C5,
            6: 0x2608134B_9C1E28E5,
            7: 0x6F3C1271_77823534,
        },
        PRESET_CC,
    ),
    "CDZT CXZT": case_of(
        lines("CDZT 1,Z5M(5),8", "CDZT 2,Z5M(5),0", "CXZT 4,A5(5),0")
        + lines("LGDR 2,1", "LGDR 3,2", "LGDR 5,4", "LGDR 6,6"),
        {
            2: 0xA2380000_000049C5,
            3: 0x22380000_000049C5,
            5: 0x22080000_00000000,
            6: 0x42,
        },
        PRESET_CC,
    ),
    "CPDT CPXT": case_of(
        MASK_OFF
        + lines("LD 1,DM12345", "CPDT 1,OUT(4),8")
        + cc_into(8)
        + lines("CPDT 1,OUT+4(4),0", "CPDT 1,OUT+8(2),0")
        + cc_into(9)
        + extended_from(4, "XBIG")
        + lines("CPXT 4,OUT+16(18),8", "LG 2,OUT", "LG 3,OUT+8")
        + lines("LG 4,OUT+16", "LG 5,OUT+24", "LG 6,OUT+32"),
        {
            8: cc_word(1),
            9: cc_word(3),
            2: 0x0012345D_00012345,
            3: 0x2345FFFF_FFFFFFFF,
            4: 0x01234567_89012345,
            5: 0x67890123_45678901,
            6: 0x234DFFFF_FFFFFFFF,
        },
        1,
    ),
    "CPDT converts specials with CC 3 and forces a plus zero": case_of(
        lines("LD 1,DINFX", "CPDT 1,OUT(2),8")
        + cc_into(8)
        + lines("LD 1,DM0", "CPDT 1,OUT+2(2),8", "CPDT 1,OUT+4(2),9")
        + lines("CPDT 1,OUT+6(2),11", "LG 2,OUT"),
        {8: cc_word(3), 2: 0x005C000D_000C000F},
        0,
    ),
    "CZDT CZXT": case_of(
        MASK_OFF
        + lines("LD 1,DM12345", "CZDT 1,OUT(5),8", "CZDT 1,OUT+8(5),12")
        + lines("CZDT 1,OUT+16(6),0", "LD 1,DM0", "CZDT 1,OUT+32(2),9")
        + extended_from(4, "XBIG")
        + lines("CZXT 4,OUT+24(3),2", "LG 2,OUT", "LG 3,OUT+8")
        + lines("LG 4,OUT+16", "LG 5,OUT+24", "LG 6,OUT+32"),
        {
            2: 0xF1F2F3F4_D5FFFFFF,
            3: 0x31323334_D5FFFFFF,
            4: 0xF0F1F2F3_F4F5FFFF,
            5: 0xF2F3F4FF_FFFFFFFF,
            6: 0xF0C0FFFF_FFFFFFFF,
        },
        3,
    ),
    "CPDT lost digits complete then abend S0CA": _ended(
        lines("LD 1,DM12345", "CPDT 1,OUT(2),0"), 3, "S0CA"
    ),
    "CDPT longer than 9 bytes abends S0C6": _ended(
        lines("CDPT 1,PBIG(10),0"), PRESET_CC, "S0C6"
    ),
    "CZXT longer than 34 bytes abends S0C6": _ended(
        lines("CZXT 0,OUT(35),0"), PRESET_CC, "S0C6"
    ),
}


PERFORM = "         PFPO\n"


def _pfpo(function: int, source: str) -> str:
    return lines("LG 1,FILL", source, f"IILF 0,X'{function:08X}'") + PERFORM


PFPO: Mapping[str, Case] = {
    "PFPO test bit sets CC 0 or 3 and a zero return code": case_of(
        lines("LG 1,FILL", "IILF 0,X'81090600'")
        + PERFORM
        + cc_into(8)
        + lines("LGR 2,1", "IILF 0,X'81070700'")
        + PERFORM
        + cc_into(9)
        + lines("IILF 0,X'81050630'")
        + PERFORM,
        {8: cc_word(0), 2: HIGH_FILL, 9: cc_word(3)},
        3,
    ),
    "PFPO BFP long to DFP long rounds by the DFP mode": case_of(
        _pfpo(0x01090600, "LD 4,BTENTH") + lines("LGDR 2,0", "LGR 3,1"),
        {2: 0x25F80000_00000000, 3: HIGH_FILL},
        1,
        INEXACT_FLAG,
    ),
    "PFPO DFP long to BFP long": case_of(
        _pfpo(0x01060900, "LD 4,DTENTH") + lines("LGDR 2,0"),
        {2: 0x3FB99999_9999999A},
        1,
        INEXACT_FLAG,
    ),
    "PFPO HFP short to BFP short and BFP long to HFP long are exact": case_of(
        _pfpo(0x01050000, "LE 4,H1")
        + lines("LGDR 2,0")
        + _pfpo(0x01010600, "LD 4,BM1P5")
        + lines("LGDR 3,0"),
        {2: 0x3F800000_00000000, 3: 0xC1180000_00000000},
        0,
    ),
    "PFPO turns a DFP NaN into plus Hmax": case_of(
        _pfpo(0x01000900, "LD 4,DQNAN") + lines("LGDR 2,0"),
        {2: 0x7FFFFFFF_00000000},
        1,
        INVALID_FLAG,
    ),
    "PFPO picks the exact DFP quantum by DPQC": case_of(
        _pfpo(0x01090600, "LD 4,BTEN")
        + lines("LGDR 2,0")
        + _pfpo(0x01090610, "LD 4,BTEN")
        + lines("LGDR 3,0"),
        {2: 0x223C0000_00000001, 3: 0x22380000_00000010},
        0,
    ),
    "PFPO rounds by the BFP mode for method 1": case_of(
        set_fpc(2) + _pfpo(0x01090601, "LD 4,BTWO3") + lines("LGDR 2,0"),
        {2: 0x39FB66D9_B66D9B67},
        1,
        INEXACT_FLAG | 2,
    ),
    "PFPO alternate action delivers the scaled overflow with CC 2": (
        set_fpc(0x20000000)
        + PRESET
        + lines("LZDR 0")
        + _pfpo(0x01080640, "LD 4,B1E300")
        + lines("LGDR 2,0", "LGR 3,1"),
        {2: 0x25F00000_00000000, 3: HIGH_FILL | 300},
        2,
        COMPLETED,
        0x20002800,
    ),
    "PFPO masked overflow gives infinity and a zero return code": case_of(
        _pfpo(0x01080600, "LD 4,B1E300") + lines("LGDR 2,0", "LGR 3,1"),
        {2: 0x78000000_00000000, 3: HIGH_FILL},
        1,
        0x00280000,
    ),
    "PFPO HFP short to DFP long": case_of(
        _pfpo(0x01090000, "LE 4,H1") + lines("LGDR 2,0"),
        {2: 0x22380000_00000001},
        0,
    ),
    "PFPO reports HFP overflow as invalid or as overflow by bit 58": case_of(
        _pfpo(0x01000900, "LD 4,D1E80")
        + lines("LGDR 2,0")
        + _pfpo(0x01000920, "LD 4,D1E80")
        + lines("LGDR 3,0"),
        {2: 0x7FFFFFFF_00000000, 3: 0x7FFFFFFF_00000000},
        1,
        INVALID_FLAG | OVERFLOW_FLAG | INEXACT_FLAG,
    ),
    "PFPO gives HFP underflow a signed true zero, unreported without bit 59": case_of(
        _pfpo(0x01000900, "LD 4,DM1EM80") + lines("LGDR 2,0"),
        {2: 0x80000000_00000000},
        1,
        INEXACT_FLAG,
    ),
    "PFPO reports HFP underflow under bit 59": case_of(
        _pfpo(0x01000910, "LD 4,DM1EM80") + lines("LGDR 2,0"),
        {2: 0x80000000_00000000},
        1,
        UNDERFLOW_FLAG | INEXACT_FLAG,
    ),
    "EX of CDZT takes the length from R1": case_of(
        lines("LA 1,4", "EX 1,XCDZT", "LGDR 2,3"), {2: 0xA2380000_000049C5}, PRESET_CC
    ),
    "PFPO with an invalid function abends S0C6": _ended(
        lines("IILF 0,X'01070600'") + PERFORM, PRESET_CC, "S0C6"
    ),
}

CASES: Mapping[str, Case] = {
    **FIXED,
    **LENGTHEN_ROUND,
    **REGISTER_DECIMAL,
    **STORAGE_DECIMAL,
    **PFPO,
}

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
    "LDETR invalid suppresses": trap_of(
        lines("LD 2,D1", "LE 1,SSNAN", "LDETR 2,1,0"),
        {2: 0x22380000_00000001},
        0x80008000,
    ),
    "LEDTR overflow delivers the scaled long result": trap_of(
        lines("LD 1,DMAX", "LEDTR 1,0,1,0"),
        {1: 0x41240000_00100000},
        0x20002C00,
    ),
    "CDSTR suppresses on a bad digit with DXC 0": trap_of(
        DXC_PRESET + lines("LD 1,D1", "LG 2,PKBAD", "CDSTR 1,2"),
        {1: 0x22380000_00000001},
        0,
    ),
    "CDSTR suppresses on a bad sign with DXC 0": trap_of(
        DXC_PRESET + lines("LD 1,D1", "LG 2,PKSIGN", "CDSTR 1,2"),
        {1: 0x22380000_00000001},
        0,
    ),
    "CDUTR suppresses on a bad digit with DXC 0": trap_of(
        DXC_PRESET + lines("LD 1,D1", "LG 2,PKBAD", "CDUTR 1,2"),
        {1: 0x22380000_00000001},
        0,
    ),
    "CDPT suppresses on a nonzero unused digit with DXC 0": trap_of(
        DXC_PRESET + lines("LD 1,D1", "CDPT 1,PUNUSED(9),0"),
        {1: 0x22380000_00000001},
        0,
    ),
    "CDZT suppresses on a bad digit with DXC 0": trap_of(
        DXC_PRESET + lines("LD 1,D1", "CDZT 1,ZBAD(3),0"), {1: 0x22380000_00000001}, 0
    ),
    "CDPT suppresses on a bad sign with DXC 0": trap_of(
        DXC_PRESET + lines("LD 1,D1", "CDPT 1,U3(3),8"), {1: 0x22380000_00000001}, 0
    ),
    "PFPO overflow traps after the scaled store": trap_of(
        lines("LZDR 0") + _pfpo(0x01080600, "LD 4,B1E300"),
        {0: 0x25F00000_00000000},
        0x20002800,
    ),
    "PFPO invalid suppresses": trap_of(
        lines("LZDR 0") + _pfpo(0x01060900, "LD 4,DSNAN"),
        {0: 0},
        0x80008000,
    ),
    "PFPO inexact traps with a zero return code": trap_of(
        _pfpo(0x01090600, "LD 4,BTENTH"), {0: 0x25F80000_00000000}, 0x08000800
    ),
    "PFPO quantum traps with a zero return code": trap_of(
        _pfpo(0x01090620, "LD 4,BTENTH"), {0: 0x25F80000_00000000}, 0x04080400
    ),
    "CDLGTR quantum traps after the store": trap_of(
        lines("LG 2,GU64", "CDLGTR 1,5,2,0"),
        {1: 0x264A4CDD_2077C2DD},
        0x04080400,
    ),
}


TRAP_RETURN_CODES: Mapping[str, int] = {
    "PFPO inexact traps with a zero return code": HIGH_FILL,
    "PFPO quantum traps with a zero return code": HIGH_FILL,
    "PFPO overflow traps after the scaled store": HIGH_FILL | 300,
    "PFPO invalid suppresses": FILL,
}


def expected_trap(case: str) -> tuple[HlasmRun, int, Mapping[int, int], int]:
    fprs, cc, fpc = TRAPS[case][1:]
    return HlasmRun(return_code=0, abend=DATA_EXCEPTION, stdout=""), cc, fprs, fpc


def expected(case: str) -> HlasmMachine:
    registers, cc, abend = CASES[case][1:4]
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)
