# pyright: standard
"""HFP arithmetic programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; FPRs come back through LGDR, intermediate CCs through IPM. Expected values are worked from the Principles of Operation, chapter 18."""

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
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import ABEND, based_program

type Case = tuple[str, Mapping[int, int], int]
type Trap = tuple[str, Mapping[int, int], int, str]

EXPONENT_OVERFLOW = "S0CC"
EXPONENT_UNDERFLOW = "S0CD"
SIGNIFICANCE = "S0CE"
HFP_DIVIDE = "S0CF"
SQUARE_ROOT = "S0DD"

DATA = (
    "         DS    0D\n"
    "E1       DC    X'41100000'\n"
    "E2       DC    X'41200000'\n"
    "E3       DC    X'41300000'\n"
    "EM1      DC    X'C1100000'\n"
    "EM2      DC    X'C1200000'\n"
    "EM4      DC    X'C1400000'\n"
    "EHALF    DC    X'40800000'\n"
    "EBELOW   DC    X'40FFFFFF'\n"
    "EBELOW2  DC    X'40FFFFFE'\n"
    "ETHIRD   DC    X'40555556'\n"
    "EM2P5    DC    X'C1280000'\n"
    "EUN      DC    X'42001000'\n"
    "E25      DC    X'42190000'\n"
    "EODD     DC    X'41800000'\n"
    "ENEXT    DC    X'41100001'\n"
    "EZ41     DC    X'41000000'\n"
    "EMAX     DC    X'7FFFFFFF'\n"
    "ETINY    DC    X'01100000'\n"
    "         DS    0D\n"
    "D1       DC    X'41100000',X'00000000'\n"
    "D2       DC    X'41200000',X'00000000'\n"
    "D3       DC    X'41300000',X'00000000'\n"
    "D4       DC    X'41400000',X'00000000'\n"
    "DM1      DC    X'C1100000',X'00000000'\n"
    "DM2      DC    X'C1200000',X'00000000'\n"
    "DHALF    DC    X'40800000',X'00000000'\n"
    "DTHIRD   DC    X'40555555',X'55555555'\n"
    "DMSUM    DC    X'C1155555',X'55555555'\n"
    "DBELOW   DC    X'40FFFFFF',X'FFFFFFFF'\n"
    "DUN      DC    X'42001000',X'00000000'\n"
    "DZ42     DC    X'42000000',X'00000000'\n"
    "DLOW1    DC    X'40000000',X'00000001'\n"
    "DNEXT    DC    X'41100000',X'00000001'\n"
    "DZERO1   DC    X'41000000',X'00000000'\n"
    "DMZ      DC    X'C1000000',X'00000000'\n"
    "D0       DC    X'00000000',X'00000000'\n"
    "DMZERO   DC    X'80000000',X'00000000'\n"
    "DBIG     DC    X'7F100000',X'00000000'\n"
    "DLOWBIT  DC    X'34100000',X'00000000'\n"
    "DMTINY   DC    X'A1100000',X'00000000'\n"
    "DM254    DC    X'C2FE0000',X'00000000'\n"
    "DPAT     DC    X'41100000',X'12345678'\n"
    "X1       DC    X'41100000',X'00000000',X'33100000',X'00000000'\n"
    "X2       DC    X'41200000',X'00000000',X'33000000',X'00000000'\n"
    "X3       DC    X'41300000',X'00000000',X'33000000',X'00000000'\n"
    "X4       DC    X'41400000',X'00000000',X'33000000',X'00000000'\n"
    "X2P5     DC    X'41280000',X'00000000',X'33000000',X'00000001'\n"
    "XM1      DC    X'C1100000',X'00000000',X'B3100000',X'00000000'\n"
    "XMZ      DC    X'C1000000',X'00000000',X'33000000',X'00000000'\n"
    "XODD     DC    X'41100000',X'00000000',X'80000000',X'00000001'\n"
    "XMAX     DC    X'7FFFFFFF',X'FFFFFFFF',X'71FFFFFF',X'FFFFFFFF'\n"
    "XTINY    DC    X'01100000',X'00000000',X'73000000',X'00000000'\n"
)


def program(body: str) -> str:
    return based_program(body, ABEND + DATA)


def program_mask(mask: int) -> str:
    return lines(f"IILF 7,X'0{mask:X}000000'", "SPM 7")


def case_of(body: str, registers: Mapping[int, int], cc: int) -> Case:
    return (PRESET + body, registers, cc)


ADD_SUBTRACT: Mapping[str, Case] = {
    "AER AE": case_of(
        zeroed_short(1, 2)
        + lines("LE 1,E1", "LE 2,E2", "AER 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("AE 1,EM4", "LGDR 3,1"),
        {2: high_word(0x41300000), 8: cc_word(2), 3: high_word(0xC1100000)},
        1,
    ),
    "ADR AD": case_of(
        lines("LD 1,D1", "LD 2,DTHIRD", "ADR 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("AD 1,DMSUM", "LGDR 3,1"),
        {2: 0x41155555_55555555, 8: cc_word(2), 3: 0},
        0,
    ),
    "AXR": case_of(
        extended_from(1, "X1")
        + extended_from(4, "X2")
        + lines("AXR 1,4", "LGDR 2,1", "LGDR 3,3"),
        {2: 0x41300000_00000000, 3: 0x33100000_00000000},
        2,
    ),
    "SER SE": case_of(
        zeroed_short(1, 2)
        + lines("LE 1,E3", "LE 2,E1", "SER 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("SE 1,E3", "LGDR 3,1"),
        {2: high_word(0x41200000), 8: cc_word(2), 3: high_word(0xC1100000)},
        1,
    ),
    "SDR SD": case_of(
        lines("LD 1,D1", "LD 2,DBELOW", "SDR 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("SD 1,D1", "LGDR 3,1"),
        {2: 0x33100000_00000000, 8: cc_word(2), 3: 0xC0FFFFFF_FFFFFFFF},
        1,
    ),
    "SXR": case_of(
        extended_from(1, "X2")
        + extended_from(4, "X1")
        + lines("SXR 1,4", "LGDR 2,1", "LGDR 3,3"),
        {2: 0x40FFFFFF_FFFFFFFF, 3: 0x32000000_00000000},
        2,
    ),
    "AUR AU": case_of(
        zeroed_short(1)
        + lines("LE 1,EUN", "AUR 1,1", "LGDR 2,1")
        + cc_into(8)
        + lines("AU 1,E1", "LGDR 3,1"),
        {2: high_word(0x42002000), 8: cc_word(2), 3: high_word(0x42012000)},
        2,
    ),
    "AWR AW": case_of(
        lines("LD 1,DUN", "AWR 1,1", "LGDR 2,1")
        + cc_into(8)
        + lines("AW 1,DM1", "LGDR 3,1"),
        {2: 0x42002000_00000000, 8: cc_word(2), 3: 0xC200E000_00000000},
        1,
    ),
    "SUR SU": case_of(
        zeroed_short(1, 2)
        + lines("LE 1,E3", "LE 2,E1", "SUR 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("SU 1,EBELOW", "LGDR 3,1"),
        {2: high_word(0x41200000), 8: cc_word(2), 3: high_word(0x41100000)},
        2,
    ),
    "SU zero without the guard digit is a true zero": case_of(
        zeroed_short(1) + lines("LE 1,E1", "SU 1,EBELOW", "LGDR 2,1"),
        {2: 0},
        0,
    ),
    "SWR SW": case_of(
        lines("LD 1,D1", "LD 2,DTHIRD", "SWR 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("SW 1,D1", "LGDR 3,1"),
        {2: 0x410AAAAA_AAAAAAAA, 8: cc_word(2), 3: 0xC1055555_55555556},
        1,
    ),
}

COMPARES: Mapping[str, Case] = {
    "CER CE": case_of(
        zeroed_short(1, 2)
        + lines("LE 1,E1", "LE 2,EBELOW", "CER 1,2")
        + cc_into(8)
        + lines("CE 1,E3")
        + cc_into(9)
        + lines("CER 1,1"),
        {8: cc_word(2), 9: cc_word(1)},
        0,
    ),
    "CDR CD": case_of(
        lines("LD 1,D1", "LD 2,DM1", "CDR 1,2")
        + cc_into(8)
        + lines("LD 3,DZ42", "CD 3,DLOW1"),
        {8: cc_word(2)},
        0,
    ),
    "CXR": case_of(
        extended_from(1, "X1") + extended_from(4, "X2") + lines("CXR 1,4"), {}, 1
    ),
}

MULTIPLY_DIVIDE: Mapping[str, Case] = {
    "MEER MEE": case_of(
        lines("LD 1,DPAT", "MEER 1,1", "LGDR 2,1")
        + zeroed_short(3, 4)
        + lines("LE 3,E3", "LE 4,ETHIRD", "MEER 3,4", "MEE 3,EM2", "LGDR 3,3"),
        {2: 0x41100000_12345678, 3: high_word(0xC1200000)},
        PRESET_CC,
    ),
    "MDR MD": case_of(
        lines("LD 1,D3", "LD 2,DTHIRD", "MDR 1,2", "LGDR 2,1", "MD 1,DM2", "LGDR 3,1"),
        {2: 0x40FFFFFF_FFFFFFFF, 3: 0xC11FFFFF_FFFFFFFF},
        PRESET_CC,
    ),
    "MXR": case_of(
        extended_from(1, "X1")
        + extended_from(4, "X2")
        + lines("MXR 1,4", "LGDR 2,1", "LGDR 3,3"),
        {2: 0x41200000_00000000, 3: 0x33200000_00000000},
        PRESET_CC,
    ),
    "MDER MDE": case_of(
        zeroed_short(1, 2)
        + lines("LE 1,E3", "LE 2,ETHIRD", "MDER 1,2", "LGDR 2,1")
        + lines("MDE 1,EM2", "LGDR 3,1"),
        {2: 0x41100000_20000000, 3: 0xC1200000_00000000},
        PRESET_CC,
    ),
    "MER ME": case_of(
        zeroed_short(1, 2)
        + lines("LE 1,E2", "LE 2,E2", "MER 1,2", "LGDR 2,1", "ME 1,E3", "LGDR 3,1"),
        {2: 0x41400000_00000000, 3: 0x41C00000_00000000},
        PRESET_CC,
    ),
    "MXDR MXD": case_of(
        lines("LD 1,DNEXT", "MXDR 1,1", "LGDR 2,1", "LGDR 3,3")
        + lines("LD 4,D2", "MXD 4,DM1", "LGDR 4,4", "LGDR 5,6"),
        {
            2: 0x41100000_00000002,
            3: 0x33000000_00000010,
            4: 0xC1200000_00000000,
            5: 0xB3000000_00000000,
        },
        PRESET_CC,
    ),
    "DER DE": case_of(
        zeroed_short(1, 2)
        + lines("LE 1,E1", "LE 2,E3", "DER 1,2", "LGDR 2,1", "DE 1,EHALF", "LGDR 3,1"),
        {2: high_word(0x40555555), 3: high_word(0x40AAAAAA)},
        PRESET_CC,
    ),
    "DDR DD": case_of(
        lines("LD 1,D1", "LD 2,D3", "DDR 1,2", "LGDR 2,1", "DD 1,DM2", "LGDR 3,1"),
        {2: 0x40555555_55555555, 3: 0xC02AAAAA_AAAAAAAA},
        PRESET_CC,
    ),
    "DXR": case_of(
        extended_from(1, "X3")
        + extended_from(4, "X2")
        + lines("DXR 1,4", "LGDR 2,1", "LGDR 3,3"),
        {2: 0x41180000_00000000, 3: 0x33000000_00000000},
        PRESET_CC,
    ),
}

UNARY: Mapping[str, Case] = {
    "HER HDR": case_of(
        zeroed_short(1, 2)
        + lines("LE 2,ENEXT", "HER 1,2", "LGDR 2,1", "LD 4,DNEXT", "HDR 3,4")
        + lines("LGDR 3,3", "LD 5,DMZ", "HDR 5,5", "LGDR 4,5"),
        {2: high_word(0x40800008), 3: 0x40800000_00000008, 4: 0},
        PRESET_CC,
    ),
    "SQER SQE": case_of(
        zeroed_short(1, 2, 3)
        + lines("LE 2,E25", "SQER 1,2", "LGDR 2,1", "SQE 3,EODD", "LGDR 3,3"),
        {2: high_word(0x41500000), 3: high_word(0x412D413D)},
        PRESET_CC,
    ),
    "SQDR SQD": case_of(
        lines("LD 2,D4", "SQDR 1,2", "LGDR 2,1", "SQD 3,D2", "LGDR 3,3")
        + lines("SQD 4,DMZ", "LGDR 4,4"),
        {2: 0x41200000_00000000, 3: 0x4116A09E_667F3BCD, 4: 0},
        PRESET_CC,
    ),
    "SQXR": case_of(
        extended_from(4, "X4") + lines("SQXR 1,4", "LGDR 2,1", "LGDR 3,3"),
        {2: 0x41200000_00000000, 3: 0x33000000_00000000},
        PRESET_CC,
    ),
    "FIER FIDR FIXR": case_of(
        zeroed_short(1, 2)
        + lines("LE 2,EM2P5", "FIER 1,2", "LGDR 2,1", "LD 4,DHALF", "FIDR 3,4")
        + lines("LGDR 3,3")
        + extended_from(8, "X2P5")
        + lines("FIXR 12,8", "LGDR 4,12", "LGDR 5,14"),
        {
            2: high_word(0xC1200000),
            3: 0,
            4: 0x41200000_00000000,
            5: 0x33000000_00000000,
        },
        PRESET_CC,
    ),
}

FUSED: Mapping[str, Case] = {
    "MAER MAE": case_of(
        zeroed_short(1, 2, 3)
        + lines("LE 1,E1", "LE 3,E2", "LE 2,E3", "MAER 1,3,2", "LGDR 2,1")
        + lines("MAE 1,3,E1", "LGDR 3,1"),
        {2: high_word(0x41700000), 3: high_word(0x41900000)},
        PRESET_CC,
    ),
    "MSER MSE": case_of(
        zeroed_short(1, 3)
        + lines("LE 1,EBELOW2", "LE 3,EBELOW", "MSER 1,3,3", "LGDR 2,1")
        + lines("MSE 1,3,E1", "LGDR 3,1"),
        {2: high_word(0x35100000), 3: high_word(0x40FFFFFE)},
        PRESET_CC,
    ),
    "MADR MAD": case_of(
        lines("LD 1,DM1", "LD 3,D2", "LD 2,D3", "MADR 1,3,2", "LGDR 2,1")
        + lines("MAD 1,3,D1", "LGDR 3,1"),
        {2: 0x41500000_00000000, 3: 0x41700000_00000000},
        PRESET_CC,
    ),
    "MSDR MSD": case_of(
        lines("LD 1,D1", "LD 3,D2", "LD 2,D3", "MSDR 1,3,2", "LGDR 2,1")
        + lines("MSD 1,3,D3", "LGDR 3,1"),
        {2: 0x41500000_00000000, 3: 0x41100000_00000000},
        PRESET_CC,
    ),
}

UNNORMALIZED_MULTIPLIES: Mapping[str, Case] = {
    "MYR MY": case_of(
        lines("LD 2,D1", "LD 3,D2", "MYR 4,3,2", "LGDR 4,4", "LGDR 5,6")
        + lines("MY 8,3,DM1", "LGDR 6,8", "LGDR 7,10")
        + lines("LD 9,D0", "MYR 12,9,9", "LGDR 8,12", "LGDR 9,14"),
        {
            4: 0x42020000_00000000,
            5: 0x34000000_00000000,
            6: 0xC2020000_00000000,
            7: 0xB4000000_00000000,
            8: 0x40000000_00000000,
            9: 0x32000000_00000000,
        },
        PRESET_CC,
    ),
    "MYR wraps the characteristic": case_of(
        lines("LD 2,DBIG", "MYR 4,2,2", "LGDR 4,4", "LGDR 5,6"),
        {4: 0x3E010000_00000000, 5: 0x30000000_00000000},
        PRESET_CC,
    ),
    "MYHR MYH": case_of(
        lines("LD 2,DNEXT", "MYHR 4,2,2", "LGDR 4,4")
        + lines("LD 3,D2", "MYH 5,3,DM1", "LGDR 5,5"),
        {4: 0x42010000_00000000, 5: 0xC2020000_00000000},
        PRESET_CC,
    ),
    "MYLR MYL": case_of(
        lines("LD 2,DNEXT", "MYLR 4,2,2", "LGDR 4,4")
        + lines("LD 3,DNEXT", "MYL 5,3,DM1", "LGDR 5,5"),
        {4: 0x34200000_00000001, 5: 0xB4100000_00000000},
        PRESET_CC,
    ),
    "MAYR MAY": case_of(
        lines("LD 2,D1", "LD 3,D2", "LD 6,D3", "MAYR 6,3,2", "LGDR 4,4", "LGDR 5,6")
        + lines("LD 1,D1", "MAY 1,3,DM1", "LGDR 6,1", "LGDR 7,3"),
        {
            4: 0x42050000_00000000,
            5: 0x34000000_00000000,
            6: 0xC2010000_00000000,
            7: 0xB4000000_00000000,
        },
        PRESET_CC,
    ),
    "MAYHR MAYH": case_of(
        lines("LD 2,D1", "LD 3,D2", "LD 7,D3", "MAYHR 7,3,2", "LGDR 4,7")
        + lines("MAYH 7,3,D1", "LGDR 5,7"),
        {4: 0x42050000_00000000, 5: 0x42070000_00000000},
        PRESET_CC,
    ),
    "MAY MAYL with a zero window keep the sum's sign": case_of(
        lines("LD 2,DM1", "LD 3,D2", "LD 6,DM254", "MAYR 6,3,2", "LGDR 4,4")
        + lines("LGDR 5,6", "LD 7,DM254", "MAYL 7,3,DM1", "LGDR 6,7"),
        {4: 0xC2000000_00000000, 5: 0xB4000000_00000000, 6: 0xB4000000_00000000},
        PRESET_CC,
    ),
    "MAYLR MAYL": case_of(
        lines("LD 2,D1", "LD 3,D2", "LD 8,DLOWBIT", "MAYLR 8,3,2", "LGDR 4,8")
        + lines("LD 9,DMTINY", "MAYL 9,3,D1", "LGDR 5,9"),
        {4: 0x34100000_00000000, 5: 0x34FFFFFF_FFFFFFFF},
        PRESET_CC,
    ),
}

SIGN_FORMS: Mapping[str, Case] = {
    "LTER LTDR LTXR": case_of(
        zeroed_short(1, 2)
        + lines("LE 2,EM1", "LTER 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("LD 4,DZERO1", "LTDR 3,4", "LGDR 3,3")
        + cc_into(9)
        + extended_from(12, "XMZ")
        + lines("LTXR 8,12", "LGDR 4,8", "LGDR 5,10")
        + cc_into(10)
        + extended_from(12, "XODD")
        + lines("LTXR 12,12", "LGDR 6,12", "LGDR 7,14"),
        {
            2: high_word(0xC1100000),
            8: cc_word(1),
            3: 0x41000000_00000000,
            9: cc_word(0),
            4: 0x80000000_00000000,
            5: 0x80000000_00000000,
            10: cc_word(0),
            6: 0x41100000_00000000,
            7: 0x33000000_00000001,
        },
        2,
    ),
    "LCER LCDR LCXR": case_of(
        zeroed_short(1, 2)
        + lines("LE 2,E1", "LCER 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("LD 4,D0", "LCDR 3,4", "LGDR 3,3")
        + cc_into(9)
        + extended_from(12, "X1")
        + lines("LCXR 8,12", "LGDR 4,8", "LGDR 5,10"),
        {
            2: high_word(0xC1100000),
            8: cc_word(1),
            3: 0x80000000_00000000,
            9: cc_word(0),
            4: 0xC1100000_00000000,
            5: 0xB3100000_00000000,
        },
        1,
    ),
    "LNER LNDR LNXR": case_of(
        zeroed_short(1, 2)
        + lines("LE 2,EM1", "LNER 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("LD 4,D2", "LNDR 3,4", "LGDR 3,3")
        + cc_into(9)
        + extended_from(12, "XMZ")
        + lines("LNXR 8,12", "LGDR 4,8", "LGDR 5,10"),
        {
            2: high_word(0xC1100000),
            8: cc_word(1),
            3: 0xC1200000_00000000,
            9: cc_word(1),
            4: 0x80000000_00000000,
            5: 0x80000000_00000000,
        },
        0,
    ),
    "LPER LPDR LPXR": case_of(
        zeroed_short(1, 2)
        + lines("LE 2,EM1", "LPER 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("LD 4,DMZERO", "LPDR 3,4", "LGDR 3,3")
        + cc_into(9)
        + extended_from(12, "XMZ")
        + lines("LPXR 8,12", "LGDR 4,8", "LGDR 5,10"),
        {
            2: high_word(0x41100000),
            8: cc_word(2),
            3: 0,
            9: cc_word(0),
            4: 0,
            5: 0,
        },
        0,
    ),
}

MASKED: Mapping[str, Case] = {
    "underflow with the mask off gives a true zero": (
        program_mask(0)
        + zeroed_short(1)
        + lines("LE 1,ETINY", "MEER 1,1", "LGDR 2,1")
        + extended_from(4, "XTINY")
        + lines("MXR 4,4", "LGDR 3,4", "LGDR 4,6"),
        {2: 0, 3: 0, 4: 0},
        0,
    ),
}

CASES: Mapping[str, Case] = {
    **ADD_SUBTRACT,
    **COMPARES,
    **MULTIPLY_DIVIDE,
    **UNARY,
    **FUSED,
    **UNNORMALIZED_MULTIPLIES,
    **SIGN_FORMS,
    **MASKED,
}


def trap_of(body: str, fprs: Mapping[int, int], cc: int, abend: str) -> Trap:
    return (PRESET + body, fprs, cc, abend)


TRAPS: Mapping[str, Trap] = {
    "exponent overflow stores the wrapped sum": trap_of(
        zeroed_short(1) + lines("LE 1,EMAX", "AER 1,1"),
        {1: high_word(0x001FFFFF)},
        2,
        EXPONENT_OVERFLOW,
    ),
    "extended exponent overflow keeps the low characteristic": trap_of(
        extended_from(1, "XMAX") + lines("AXR 1,1"),
        {1: 0x001FFFFF_FFFFFFFF, 3: 0x72FFFFFF_FFFFFFFF},
        2,
        EXPONENT_OVERFLOW,
    ),
    "exponent underflow with the mask on stores the wrapped product": trap_of(
        zeroed_short(1) + lines("LE 1,ETINY", "MEER 1,1"),
        {1: high_word(0x41100000)},
        PRESET_CC,
        EXPONENT_UNDERFLOW,
    ),
    "unnormalized significance with the mask on keeps the characteristic": trap_of(
        program_mask(1) + zeroed_short(1) + lines("LE 1,E1", "SU 1,EBELOW"),
        {1: high_word(0x41000000)},
        0,
        SIGNIFICANCE,
    ),
    "normalized significance with the mask on keeps the characteristic": trap_of(
        program_mask(1) + zeroed_short(1) + lines("LE 1,E3", "SER 1,1"),
        {1: high_word(0x41000000)},
        0,
        SIGNIFICANCE,
    ),
    "extended significance with the mask on keeps both characteristics": trap_of(
        program_mask(1)
        + extended_from(1, "X1")
        + extended_from(4, "XM1")
        + lines("AXR 1,4"),
        {1: 0x41000000_00000000, 3: 0x33000000_00000000},
        0,
        SIGNIFICANCE,
    ),
    "short HFP divide suppresses": trap_of(
        zeroed_short(1, 2) + lines("LE 1,E1", "LE 2,EZ41", "DER 1,2"),
        {1: high_word(0x41100000)},
        PRESET_CC,
        HFP_DIVIDE,
    ),
    "extended HFP divide suppresses": trap_of(
        extended_from(1, "X1") + extended_from(4, "XMZ") + lines("DXR 1,4"),
        {1: 0x41100000_00000000, 3: 0x33100000_00000000},
        PRESET_CC,
        HFP_DIVIDE,
    ),
    "HFP divide suppresses": trap_of(
        lines("LD 1,D1", "LD 2,DZERO1", "DDR 1,2"),
        {1: 0x41100000_00000000},
        PRESET_CC,
        HFP_DIVIDE,
    ),
    "square root of a negative suppresses": trap_of(
        lines("LD 1,D1", "SQD 1,DM2"),
        {1: 0x41100000_00000000},
        PRESET_CC,
        SQUARE_ROOT,
    ),
}


def expected(case: str) -> HlasmMachine:
    registers, cc = CASES[case][1:3]
    return HlasmMachine(
        HlasmRun(return_code=0, abend=COMPLETED, stdout=""), cc, registers
    )


def expected_trap(case: str) -> tuple[HlasmRun, int, Mapping[int, int]]:
    fprs, cc, abend = TRAPS[case][1:]
    return HlasmRun(return_code=0, abend=abend, stdout=""), cc, fprs
