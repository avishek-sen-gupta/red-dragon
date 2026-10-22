# pyright: standard
"""Multiply and divide programs, one per mnemonic, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL

type Case = tuple[str, Mapping[int, int], int]

CC_ZERO = 0
CC_NEGATIVE = 1
CC_POSITIVE = 2
CC_OVERFLOW = 3
CC_KEPT = 1
SET_CC_ONE = "         CHI   11,0\n"

TRUNCATED_PRODUCTS: Mapping[str, Case] = {
    "MS": (
        SET_CC_ONE + "         L     2,NEG\n" "         MS    2,WORDS+4\n",
        {2: HIGH_FILL | 0x00000002},
        CC_KEPT,
    ),
    "MSY": (
        SET_CC_ONE + "         LHI   2,-3\n" "         MSY   2,WORDS+8\n",
        {2: HIGH_FILL | 0xFFFFFFF7},
        CC_KEPT,
    ),
    "MSR": (
        SET_CC_ONE
        + "         L     2,POS\n"
        + "         L     3,POS\n"
        + "         MSR   2,3\n",
        {2: HIGH_FILL | 0x40020004, 3: HIGH_FILL | 0x7FFF7FFE},
        CC_KEPT,
    ),
    "MSFI": (
        SET_CC_ONE + "         LHI   2,7\n" "         MSFI  2,-100000\n",
        {2: HIGH_FILL | 0xFFF551A0},
        CC_KEPT,
    ),
    "MH": (
        SET_CC_ONE + "         LHI   2,3\n" "         MH    2,NEG\n",
        {2: HIGH_FILL | 0xFFFE8000},
        CC_KEPT,
    ),
    "MHY": (
        SET_CC_ONE + "         L     2,POS\n" "         MHY   2,POS\n",
        {2: HIGH_FILL | 0x3FFF8002},
        CC_KEPT,
    ),
    "MHI": (
        SET_CC_ONE + "         LHI   2,-5\n" "         MHI   2,-6\n",
        {2: HIGH_FILL | 0x0000001E},
        CC_KEPT,
    ),
    "MSG": (
        SET_CC_ONE + "         LG    3,SRC\n" "         MSG   3,SRCP\n",
        {3: 0x2236D88F_E5618CF0},
        CC_KEPT,
    ),
    "MSGR": (
        SET_CC_ONE
        + "         LG    3,DNEG\n"
        + "         LGHI  4,-1\n"
        + "         MSGR  3,4\n",
        {3: 0x7FFFFFFF_FFFFFF7F, 4: 0xFFFFFFFF_FFFFFFFF},
        CC_KEPT,
    ),
    "MSGF": (
        SET_CC_ONE + "         LGHI  3,-2\n" "         MSGF  3,NEG\n",
        {3: 0x00000000_FFFFFFFE},
        CC_KEPT,
    ),
    "MSGFR": (
        SET_CC_ONE
        + "         LGHI  3,3\n"
        + "         L     4,NEG\n"
        + "         MSGFR 3,4\n",
        {3: 0xFFFFFFFE_80000003},
        CC_KEPT,
    ),
    "MSGFI": (
        SET_CC_ONE + "         LG    3,SRC\n" "         MSGFI 3,-1\n",
        {3: 0xFEDCBA98_76543211},
        CC_KEPT,
    ),
    "MGH": (
        SET_CC_ONE + "         LGHI  3,1000\n" "         MGH   3,NEG\n",
        {3: 0xFFFFFFFF_FE0C0000},
        CC_KEPT,
    ),
    "MGHI": (
        SET_CC_ONE + "         LG    3,DPOS\n" "         MGHI  3,2\n",
        {3: 0xFFFFFFFF_FFFFFEFC},
        CC_KEPT,
    ),
}

CHECKED_PRODUCTS: Mapping[str, Case] = {
    "MSC": (
        "         LHI   2,-6\n" "         MSC   2,WORDS+8\n",
        {2: HIGH_FILL | 0xFFFFFFEE},
        CC_NEGATIVE,
    ),
    "MSC overflow": (
        "         L     2,POS\n" "         MSC   2,WORDS+4\n",
        {2: HIGH_FILL | 0xFFFEFFFC},
        CC_OVERFLOW,
    ),
    "MSRKC": (
        "         LHI   3,0\n" "         MSRKC 5,3,4\n",
        {5: HIGH_FILL},
        CC_ZERO,
    ),
    "MSGC": (
        "         LGHI  3,-4\n" "         MSGC  3,SRC\n",
        {3: 0xFB72EA61_D950C844},
        CC_NEGATIVE,
    ),
    "MSGRKC": (
        "         LG    3,DNEG\n" "         LGHI  4,2\n" "         MSGRKC 5,4,3\n",
        {5: 0x00000000_00000102},
        CC_OVERFLOW,
    ),
}

PAIR_PRODUCTS: Mapping[str, Case] = {
    "M": (
        SET_CC_ONE + "         L     3,NEG\n" "         M     2,WORDS+8\n",
        {2: HIGH_FILL | 0xFFFFFFFE, 3: HIGH_FILL | 0x80000003},
        CC_KEPT,
    ),
    "MFY": (
        SET_CC_ONE + "         LHI   3,-1\n" "         MFY   2,NEG\n",
        {2: HIGH_FILL, 3: HIGH_FILL | 0x7FFFFFFF},
        CC_KEPT,
    ),
    "MR": (
        SET_CC_ONE
        + "         L     3,NEG\n"
        + "         L     5,NEG\n"
        + "         MR    2,5\n",
        {2: HIGH_FILL | 0x3FFFFFFF, 3: HIGH_FILL | 0x00000001},
        CC_KEPT,
    ),
    "ML": (
        SET_CC_ONE + "         L     3,NEG\n" "         ML    2,NEG\n",
        {2: HIGH_FILL | 0x40000001, 3: HIGH_FILL | 0x00000001},
        CC_KEPT,
    ),
    "MLR": (
        SET_CC_ONE
        + "         LHI   3,-1\n"
        + "         LHI   5,-1\n"
        + "         MLR   2,5\n",
        {2: HIGH_FILL | 0xFFFFFFFE, 3: HIGH_FILL | 0x00000001},
        CC_KEPT,
    ),
    "MG": (
        SET_CC_ONE + "         LG    5,DNEG\n" "         MG    4,SRCP\n",
        {4: 0x0091A2B3_C4D5E6F7, 5: 0x6D3A06D3_A06D3A10},
        CC_KEPT,
    ),
    "MGRK": (
        SET_CC_ONE
        + "         LG    3,DNEG\n"
        + "         LG    7,DNEG\n"
        + "         MGRK  4,3,7\n",
        {4: 0x3FFFFFFF_FFFFFF7F, 5: 0x00000000_00004101},
        CC_KEPT,
    ),
    "MLG": (
        SET_CC_ONE + "         LG    5,SRCP\n" "         MLG   4,SRCP\n",
        {4: 0xFDBAC097_C8DC5ACC, 5: 0xDEEC6CD7_A44A4100},
        CC_KEPT,
    ),
    "MLGR": (
        SET_CC_ONE
        + "         LGHI  5,-1\n"
        + "         LGHI  7,-1\n"
        + "         MLGR  4,7\n",
        {4: 0xFFFFFFFF_FFFFFFFE, 5: 0x00000000_00000001},
        CC_KEPT,
    ),
}

DIVIDES: Mapping[str, Case] = {
    "D": (
        SET_CC_ONE
        + "         LHI   2,-1\n"
        + "         LHI   3,-7\n"
        + "         D     2,WORDS+4\n",
        {2: HIGH_FILL | 0xFFFFFFFF, 3: HIGH_FILL | 0xFFFFFFFD},
        CC_KEPT,
    ),
    "DR": (
        SET_CC_ONE
        + "         LHI   2,0\n"
        + "         L     3,POS\n"
        + "         LHI   5,-10\n"
        + "         DR    2,5\n",
        {2: HIGH_FILL | 0x00000008, 3: HIGH_FILL | 0xF3334001},
        CC_KEPT,
    ),
    "DL": (
        SET_CC_ONE
        + "         LHI   2,1\n"
        + "         LHI   3,0\n"
        + "         DL    2,WORDS+8\n",
        {2: HIGH_FILL | 0x00000001, 3: HIGH_FILL | 0x55555555},
        CC_KEPT,
    ),
    "DLR": (
        SET_CC_ONE
        + "         LHI   2,-2\n"
        + "         LHI   3,-1\n"
        + "         LHI   5,-1\n"
        + "         DLR   2,5\n",
        {2: HIGH_FILL | 0xFFFFFFFE, 3: HIGH_FILL | 0xFFFFFFFF},
        CC_KEPT,
    ),
    "DLG": (
        SET_CC_ONE
        + "         LG    4,SRC\n"
        + "         LG    5,SRCP\n"
        + "         DLG   4,SRCP\n",
        {4: 0x7E3649CB_031697D0, 5: 0x01249249_24924924},
        CC_KEPT,
    ),
    "DLGR": (
        SET_CC_ONE
        + "         LGHI  4,0\n"
        + "         LGHI  5,-1\n"
        + "         LGHI  7,10\n"
        + "         DLGR  4,7\n",
        {4: 0x00000000_00000005, 5: 0x19999999_99999999},
        CC_KEPT,
    ),
    "DSG": (
        SET_CC_ONE + "         LG    5,DNEG\n" "         DSG   4,SRC\n",
        {4: 0xFF6E5D4C_3B2A1911, 5: 0xFFFFFFFF_FFFFFF90},
        CC_KEPT,
    ),
    "DSGR": (
        SET_CC_ONE
        + "         LGHI  5,-100\n"
        + "         LGHI  7,7\n"
        + "         DSGR  4,7\n",
        {4: 0xFFFFFFFF_FFFFFFFE, 5: 0xFFFFFFFF_FFFFFFF2},
        CC_KEPT,
    ),
    "DSGF": (
        SET_CC_ONE + "         LG    5,DPOS\n" "         DSGF  4,NEG\n",
        {4: 0x00000000_7FFFFF7F, 5: 0xFFFFFFFE_FFFFFFFF},
        CC_KEPT,
    ),
    "DSGFR": (
        SET_CC_ONE
        + "         LG    5,DNEG\n"
        + "         LHI   7,-3\n"
        + "         DSGFR 4,7\n",
        {4: 0xFFFFFFFF_FFFFFFFE, 5: 0x2AAAAAAA_AAAAAA7F},
        CC_KEPT,
    ),
}

DIVIDE_EXCEPTIONS: Mapping[str, Case] = {
    "D by zero": (
        SET_CC_ONE
        + "         LHI   2,0\n"
        + "         LHI   3,5\n"
        + "         D     2,ZERO\n",
        {2: HIGH_FILL, 3: HIGH_FILL | 0x00000005},
        CC_KEPT,
    ),
    "DR quotient beyond a signed word": (
        SET_CC_ONE
        + "         LHI   2,1\n"
        + "         LHI   3,0\n"
        + "         LHI   5,1\n"
        + "         DR    2,5\n",
        {2: HIGH_FILL | 0x00000001, 3: HIGH_FILL},
        CC_KEPT,
    ),
    "DL quotient beyond an unsigned word": (
        SET_CC_ONE
        + "         LHI   2,3\n"
        + "         LHI   3,0\n"
        + "         DL    2,WORDS+8\n",
        {2: HIGH_FILL | 0x00000003, 3: HIGH_FILL},
        CC_KEPT,
    ),
    "DLGR by zero": (
        SET_CC_ONE
        + "         LGHI  4,0\n"
        + "         LGHI  5,1\n"
        + "         LGHI  7,0\n"
        + "         DLGR  4,7\n",
        {4: 0, 5: 1},
        CC_KEPT,
    ),
    "DSGR minimum by minus one": (
        SET_CC_ONE
        + "         LLIHF 5,X'80000000'\n"
        + "         LGHI  7,-1\n"
        + "         DSGR  4,7\n",
        {4: FILL, 5: 0x80000000_00000000},
        CC_KEPT,
    ),
    "DSGF by zero": (
        SET_CC_ONE + "         LGHI  5,9\n" "         DSGF  4,ZERO\n",
        {4: FILL, 5: 9},
        CC_KEPT,
    ),
}

CASES: Mapping[str, Case] = {
    **TRUNCATED_PRODUCTS,
    **CHECKED_PRODUCTS,
    **PAIR_PRODUCTS,
    **DIVIDES,
}
