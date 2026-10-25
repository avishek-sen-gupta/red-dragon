# pyright: standard
"""Miscellaneous and access-register programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; R2-R11 start at FILL and the clock is the fixed test clock."""

from collections.abc import Mapping

from tests.integration.hlasm.fixed_machine_clock import (
    FIXED_CPU_TIMER,
    FIXED_TOD_CLOCK,
)
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import (
    ABEND,
    FILL,
    HIGH_FILL,
    based_program,
)

type Case = tuple[str, Mapping[int, int], int, str]

COMPLETED = "U0001"
SPECIFICATION = "S0C6"
FIXED_POINT_OVERFLOW = "S0C8"
SPECIAL_OPERATION = "S0D3"
PRESET_CC = 2
PRESET = "         CLI   NEG,0\n"
ONES = 0xFFFFFFFF_FFFFFFFF
TOD_SHIFT = 40
STORED_CLOCK = FIXED_TOD_CLOCK >> TOD_SHIFT
EXTENDED_CLOCK = (FIXED_TOD_CLOCK | 1) << 16
NEXT_EXTENDED_CLOCK = ((FIXED_TOD_CLOCK | 1) + 2) << 16
FACILITIES_FIRST = 0xE1003F63_F47C8C24
FACILITIES_SECOND = 0x00008900_00000000
DNEG = 0x80000000_00000081
DPOS = 0x7FFFFFFF_FFFFFF7E
SRC_HIGH_ABEND_LOW = 0x01234567_00000001
OVERFLOW_ENABLED = "         IILF  0,X'08000000'\n         SPM   0\n"
TARGETS = "MCX      MC    0,0\nSPMX     SPM   0\n         ORG   T+X'400'\n"
OUT_SPAN = (0x4A8, 0x4E8)


def _line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<6} {operands}\n"


def program(body: str) -> str:
    return based_program(body, ABEND + TARGETS)


def _ran(body: str, results: Mapping[int, int], cc: int) -> Case:
    return (body, results, cc, COMPLETED)


def _kept(body: str, results: Mapping[int, int]) -> Case:
    return (PRESET + body, results, PRESET_CC, COMPLETED)


def _abends(body: str, results: Mapping[int, int], cc: int, abend: str) -> Case:
    return (body, results, cc, abend)


def _overflows(body: str, results: Mapping[int, int]) -> Case:
    return (OVERFLOW_ENABLED + body, results, 3, FIXED_POINT_OVERFLOW)


PROGRAM_STATUS: Mapping[str, Case] = {
    "SPM IPM": _ran(
        _line("IILF", "3,X'EBFFFFFF'") + _line("SPM", "3") + _line("IPM", "4"),
        {3: HIGH_FILL | 0xEBFFFFFF, 4: HIGH_FILL | 0x2BA5A5A5},
        2,
    ),
    "IPM initial mask": _kept(_line("IPM", "2"), {2: HIGH_FILL | 0x26A5A5A5}),
    "EX SPM": _ran(
        _line("IILF", "2,X'1A000000'")
        + _line("LHI", "3,X'20'")
        + _line("EX", "3,SPMX")
        + _line("IPM", "4"),
        {4: HIGH_FILL | 0x1AA5A5A5},
        1,
    ),
    "EPSW": _kept(
        _line("EPSW", "2,3"), {2: HIGH_FILL | 0x07852600, 3: HIGH_FILL | 0x80000000}
    ),
    "EPSW after SPM": _ran(
        _line("IILF", "3,X'1F000000'")
        + _line("SPM", "3")
        + _line("LGHI", "0,5")
        + _line("EPSW", "4,0")
        + _line("EPSW", "5,5"),
        {0: 5, 4: HIGH_FILL | 0x07851F00, 5: HIGH_FILL | 0x80000000},
        1,
    ),
}

ACCESS_REGISTERS: Mapping[str, Case] = {
    "SAR CPYA EAR": _kept(
        _line("IILF", "3,X'12345678'")
        + _line("SAR", "1,3")
        + _line("CPYA", "2,1")
        + _line("EAR", "4,2")
        + _line("EAR", "5,0"),
        {4: HIGH_FILL | 0x12345678, 5: HIGH_FILL},
    ),
    "LAE LAEY clear the access register": _ran(
        _line("IILF", "4,X'12345678'")
        + _line("SAR", "2,4")
        + _line("SAR", "3,4")
        + _line("LAE", "2,NEG")
        + _line("LAEY", "3,NEG")
        + _line("LA", "5,NEG")
        + _line("SR", "2,5")
        + _line("SR", "3,5")
        + _line("EAR", "6,2")
        + _line("EAR", "7,3"),
        {2: HIGH_FILL, 3: HIGH_FILL, 6: HIGH_FILL, 7: HIGH_FILL},
        0,
    ),
    "LAM STAM wrapping": _kept(
        _line("LAM", "14,1,WORDS")
        + _line("STAM", "15,0,OUT")
        + _line("LG", "2,OUT")
        + _line("EAR", "3,14")
        + _line("EAR", "4,1"),
        {2: 0x00000002_00000003, 3: HIGH_FILL | 1, 4: HIGH_FILL | 4},
    ),
    "LAMY STAMY": _kept(
        _line("LAMY", "3,4,HIGHS")
        + _line("STAMY", "4,4,OUT+4")
        + _line("LG", "2,OUT")
        + _line("EAR", "5,3"),
        {2: 0xFFFFFFFF_22222222, 5: HIGH_FILL | 0x11111111},
    ),
    "LAM off a word": _abends(
        PRESET + _line("LAM", "1,1,NEG+1") + _line("LHI", "2,0"),
        {2: FILL},
        PRESET_CC,
        SPECIFICATION,
    ),
    "STAM off a word": _abends(
        PRESET + _line("STAM", "1,1,OUT+2") + _line("LHI", "2,0"),
        {2: FILL},
        PRESET_CC,
        SPECIFICATION,
    ),
}

CHECKSUMS: Mapping[str, Case] = {
    "CKSM tail and carry": _ran(
        _line("LA", "4,SRC")
        + _line("LHI", "5,7")
        + _line("CKSM", "2,4")
        + _line("IPM", "7")
        + _line("LA", "6,SRC")
        + _line("SR", "4,6"),
        {
            2: HIGH_FILL | 0x3074B80D,
            4: HIGH_FILL | 7,
            5: HIGH_FILL,
            7: HIGH_FILL | 0x06A5A5A5,
        },
        2,
    ),
    "CKSM whole words": _ran(
        PRESET
        + _line("SR", "2,2")
        + _line("LA", "4,SRC")
        + _line("LHI", "5,8")
        + _line("CKSM", "2,4"),
        {2: HIGH_FILL | 0x8ACF1356, 5: HIGH_FILL},
        0,
    ),
    "CKSM zero length": _ran(
        PRESET + _line("LA", "4,SRC") + _line("LHI", "5,0") + _line("CKSM", "2,4"),
        {2: FILL, 5: HIGH_FILL},
        0,
    ),
}

CPU_ATTRIBUTES: Mapping[str, Case] = {
    "ECAG": _kept(
        _line("ECAG", "2,0,0")
        + _line("ECAG", "3,0,X'21'")
        + _line("ECAG", "4,0,X'34'")
        + _line("ECAG", "5,0,X'100'")
        + _line("ECAG", "6,0,X'18'")
        + _line("ECAG", "7,0,X'400'")
        + _line("ECAG", "8,0,X'200'")
        + _line("ECAG", "9,0,X'12'")
        + _line("ECAG", "10,0,X'0E'")
        + _line("ECAG", "11,0,X'1F'"),
        {
            2: 0x04070B0B_00000000,
            3: 131072,
            4: 48,
            5: 0x0000157C_0000157C,
            6: ONES,
            7: ONES,
            8: ONES,
            9: 256,
            10: 0x04070B0B_00000000,
            11: ONES,
        },
    ),
    "ECAG sizes and ways": _kept(
        _line("ECAG", "2,0,X'22'")
        + _line("ECAG", "3,0,X'24'")
        + _line("ECAG", "4,0,X'26'")
        + _line("ECAG", "5,0,X'30'")
        + _line("ECAG", "6,0,X'32'")
        + _line("ECAG", "7,0,X'36'")
        + _line("ECAG", "8,0,X'10F'")
        + _line("ECAG", "9,0,X'110'")
        + _line("ECAG", "10,0,X'40'"),
        {
            2: 37748736,
            3: 377487360,
            4: 3019898880,
            5: 8,
            6: 18,
            7: 48,
            8: 0x0000157C_0000157C,
            9: ONES,
            10: ONES,
        },
    ),
    "LCBB short": _ran(
        _line("LCBB", "2,X'7F8',0")
        + _line("LGHI", "5,X'F0'")
        + _line("LCBB", "3,1(5),2")
        + _line("LCBB", "4,X'FFF',6"),
        {2: HIGH_FILL | 8, 3: HIGH_FILL | 15, 4: HIGH_FILL | 1},
        3,
    ),
    "LCBB sixteen": _ran(
        _line("LCBB", "3,X'7F0',0") + _line("LCBB", "4,X'10',6"),
        {3: HIGH_FILL | 16, 4: HIGH_FILL | 16},
        0,
    ),
}

CLOCKS: Mapping[str, Case] = {
    "STCK unique": _ran(
        PRESET
        + _line("STCK", "OUT")
        + _line("STCK", "OUT+8")
        + _line("LMG", "2,3,OUT"),
        {2: STORED_CLOCK, 3: STORED_CLOCK + 1},
        0,
    ),
    "STCKF": _ran(
        PRESET
        + _line("STCKF", "OUT")
        + _line("STCKF", "OUT+8")
        + _line("LMG", "2,3,OUT"),
        {2: STORED_CLOCK, 3: STORED_CLOCK},
        0,
    ),
    "STCKE": _ran(
        PRESET + _line("STCKE", "OUT") + _line("LMG", "2,3,OUT"),
        {2: EXTENDED_CLOCK >> 64, 3: EXTENDED_CLOCK & ONES},
        0,
    ),
    "STCKE twice": _ran(
        PRESET
        + _line("STCKE", "OUT")
        + _line("STCKE", "OUT+16")
        + _line("LMG", "2,5,OUT"),
        {
            2: EXTENDED_CLOCK >> 64,
            3: EXTENDED_CLOCK & ONES,
            4: NEXT_EXTENDED_CLOCK >> 64,
            5: NEXT_EXTENDED_CLOCK & ONES,
        },
        0,
    ),
    "STCK after STCKE": _ran(
        PRESET
        + _line("STCKE", "OUT")
        + _line("STCK", "OUT+16")
        + _line("LMG", "2,4,OUT"),
        {2: EXTENDED_CLOCK >> 64, 3: EXTENDED_CLOCK & ONES, 4: STORED_CLOCK + 1},
        0,
    ),
    "ECTG": _kept(
        _line("LGHI", "0,7")
        + _line("LGHI", "1,9")
        + _line("LA", "3,DPOS")
        + _line("ECTG", "DNEG,SRC,3"),
        {0: (DNEG - FIXED_CPU_TIMER) % (1 << 64), 1: SRC_HIGH_ABEND_LOW, 3: DPOS},
    ),
}

FACILITY_LIST: Mapping[str, Case] = {
    "STFLE short": _ran(
        _line("LGHI", "0,0")
        + _line("STFLE", "OUT")
        + _line("LGR", "2,0")
        + _line("LMG", "3,4,OUT"),
        {2: 1, 3: FACILITIES_FIRST, 4: ONES},
        3,
    ),
    "STFLE complete": _ran(
        _line("LGHI", "0,X'1FF'")
        + _line("STFLE", "OUT")
        + _line("LGR", "2,0")
        + _line("LMG", "3,5,OUT"),
        {2: 0x101, 3: FACILITIES_FIRST, 4: FACILITIES_SECOND, 5: ONES},
        0,
    ),
    "STFLE exact": _ran(
        _line("LGHI", "0,1")
        + _line("STFLE", "OUT")
        + _line("LGR", "2,0")
        + _line("LMG", "3,5,OUT"),
        {2: 1, 3: FACILITIES_FIRST, 4: FACILITIES_SECOND, 5: ONES},
        0,
    ),
    "STFLE off a doubleword": _abends(
        PRESET + _line("LGHI", "0,1") + _line("STFLE", "OUT+4") + _line("LG", "2,OUT"),
        {0: 1, 2: FILL},
        PRESET_CC,
        SPECIFICATION,
    ),
}

HINTS_AND_TRAPS: Mapping[str, Case] = {
    "hints": _kept(
        _line("NIAI", "1,2") + _line("PFD", "1,OUT") + _line("PFDRL", "2,OUT"),
        {2: FILL},
    ),
    "MC": _kept(_line("MC", "OUT,5"), {2: FILL}),
    "EX MC class 15": _kept(_line("LHI", "3,X'0F'") + _line("EX", "3,MCX"), {}),
    "EX MC class over 15": _abends(
        PRESET + _line("LHI", "3,X'20'") + _line("EX", "3,MCX"),
        {},
        PRESET_CC,
        SPECIFICATION,
    ),
    "MC class over 15": _abends(
        PRESET + _line("MC", "OUT,X'15'"), {}, PRESET_CC, SPECIFICATION
    ),
    "TRAP2": _abends(
        PRESET + _line("TRAP2", "") + _line("LHI", "2,0"),
        {2: FILL},
        PRESET_CC,
        SPECIAL_OPERATION,
    ),
    "TRAP4": _abends(
        PRESET + _line("TRAP4", "OUT") + _line("LHI", "2,0"),
        {2: FILL},
        PRESET_CC,
        SPECIAL_OPERATION,
    ),
}

FIXED_POINT_OVERFLOWS: Mapping[str, Case] = {
    "AR": _overflows(
        _line("IILF", "2,X'7FFFFFFF'") + _line("IILF", "3,1") + _line("AR", "2,3"),
        {2: HIGH_FILL | 0x80000000},
    ),
    "AGR": _overflows(
        _line("LG", "2,DPOS") + _line("LGHI", "3,X'100'") + _line("AGR", "2,3"),
        {2: 0x80000000_0000007E},
    ),
    "LCR": _overflows(
        _line("IILF", "2,X'80000000'") + _line("LCR", "3,2"),
        {3: HIGH_FILL | 0x80000000},
    ),
    "LCGR": _overflows(
        _line("LLIHF", "2,X'80000000'") + _line("LCGR", "3,2"),
        {3: 0x80000000_00000000},
    ),
    "LPR": _overflows(
        _line("IILF", "2,X'80000000'") + _line("LPR", "3,2"),
        {3: HIGH_FILL | 0x80000000},
    ),
    "LPGR": _overflows(
        _line("LLIHF", "2,X'80000000'") + _line("LPGR", "3,2"),
        {3: 0x80000000_00000000},
    ),
    "MSC": _overflows(
        _line("IILF", "2,X'40000000'") + _line("MSC", "2,WORDS+4"),
        {2: HIGH_FILL | 0x80000000},
    ),
    "MSRKC": _overflows(
        _line("IILF", "3,X'40000000'") + _line("IILF", "4,2") + _line("MSRKC", "2,3,4"),
        {2: HIGH_FILL | 0x80000000},
    ),
    "MSGC": _overflows(
        _line("LLIHF", "2,X'40000000'") + _line("MSGC", "2,WORDS"),
        {2: 0x80000000_00000000},
    ),
    "MSGRKC": _overflows(
        _line("LLIHF", "3,X'40000000'")
        + _line("LGHI", "4,2")
        + _line("MSGRKC", "2,3,4"),
        {2: 0x80000000_00000000},
    ),
    "SLA": _overflows(
        _line("IILF", "2,X'40000000'") + _line("SLA", "2,1"), {2: HIGH_FILL}
    ),
    "SLAK": _overflows(
        _line("IILF", "2,X'40000000'") + _line("SLAK", "3,2,1"), {3: HIGH_FILL}
    ),
    "SLAG": _overflows(
        _line("LLIHF", "2,X'40000000'") + _line("SLAG", "3,2,1"), {3: 0}
    ),
    "SLDA": _overflows(
        _line("IILF", "2,X'40000000'") + _line("IILF", "3,0") + _line("SLDA", "2,1"),
        {2: HIGH_FILL, 3: HIGH_FILL},
    ),
    "AHHHR": _overflows(
        _line("IIHF", "3,X'7FFFFFFF'") + _line("IIHF", "4,1") + _line("AHHHR", "2,3,4"),
        {2: 0x80000000_A5A5A5A5},
    ),
    "AIH": _overflows(
        _line("IIHF", "2,X'7FFFFFFF'") + _line("AIH", "2,1"),
        {2: 0x80000000_A5A5A5A5},
    ),
    "LAA": _overflows(
        _line("IILF", "4,X'7FFFFFFF'")
        + _line("ST", "4,OUT")
        + _line("IILF", "3,1")
        + _line("LAA", "2,3,OUT"),
        {2: HIGH_FILL | 0x7FFFFFFF},
    ),
    "LAAG": _overflows(
        _line("LG", "4,DPOS")
        + _line("STG", "4,OUT")
        + _line("LGHI", "3,X'100'")
        + _line("LAAG", "2,3,OUT"),
        {2: DPOS},
    ),
    "SPM mask off": _ran(
        _line("IILF", "0,0")
        + _line("SPM", "0")
        + _line("IILF", "2,X'7FFFFFFF'")
        + _line("IILF", "3,1")
        + _line("AR", "2,3"),
        {2: HIGH_FILL | 0x80000000},
        3,
    ),
}

CASES: Mapping[str, Case] = {
    **PROGRAM_STATUS,
    **ACCESS_REGISTERS,
    **CHECKSUMS,
    **CPU_ATTRIBUTES,
    **CLOCKS,
    **FACILITY_LIST,
    **HINTS_AND_TRAPS,
    **FIXED_POINT_OVERFLOWS,
}


def expected(case: str) -> HlasmMachine:
    _, registers, cc, abend = CASES[case]
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)
