# pyright: standard
"""Shift and rotate programs, one per mnemonic and extended mnemonic, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL

type Case = tuple[str, Mapping[int, int], int]

CC_ZERO = 0
CC_NEGATIVE = 1
CC_POSITIVE = 2
CC_NONZERO = 1
CC_OVERFLOW = 3
CC_KEPT = 1
SET_CC_ONE = "         CHI   11,0\n"
SRC_INTO_3 = "         LG    3,SRC\n"
SRC_AND_SRCP = "         LG    3,SRC\n" "         LG    5,SRCP\n"

LOGICAL_SHIFTS: Mapping[str, Case] = {
    "SLL": (
        SET_CC_ONE + "         L     2,NEG\n" "         SLL   2,1\n",
        {2: HIGH_FILL | 0x00000002},
        CC_KEPT,
    ),
    "SLL amount modulo 64": (
        SET_CC_ONE + "         L     2,POS\n" "         SLL   2,65\n",
        {2: HIGH_FILL | 0xFFFEFFFC},
        CC_KEPT,
    ),
    "SLL amount 33 from a base register": (
        SET_CC_ONE
        + "         LHI   4,33\n"
        + "         L     2,NEG\n"
        + "         SLL   2,0(4)\n",
        {2: HIGH_FILL},
        CC_KEPT,
    ),
    "SLLK": (
        SET_CC_ONE + "         L     3,POS\n" "         SLLK  5,3,4\n",
        {3: HIGH_FILL | 0x7FFF7FFE, 5: HIGH_FILL | 0xFFF7FFE0},
        CC_KEPT,
    ),
    "SLLG": (
        SET_CC_ONE + SRC_INTO_3 + "         SLLG  5,3,8\n",
        {3: 0x01234567_89ABCDEF, 5: 0x23456789_ABCDEF00},
        CC_KEPT,
    ),
    "SRL": (
        SET_CC_ONE + "         L     2,NEG\n" "         SRL   2,31\n",
        {2: HIGH_FILL | 0x00000001},
        CC_KEPT,
    ),
    "SRLK": (
        SET_CC_ONE + "         L     3,NEG\n" "         SRLK  5,3,4\n",
        {5: HIGH_FILL | 0x08000000},
        CC_KEPT,
    ),
    "SRL amount 33": (
        SET_CC_ONE + "         L     2,NEG\n" "         SRL   2,33\n",
        {2: HIGH_FILL},
        CC_KEPT,
    ),
    "SRLK amount 32": (
        SET_CC_ONE + "         L     3,NEG\n" "         SRLK  5,3,32\n",
        {5: HIGH_FILL},
        CC_KEPT,
    ),
    "SLLK amount 40": (
        SET_CC_ONE + "         L     3,POS\n" "         SLLK  5,3,40\n",
        {5: HIGH_FILL},
        CC_KEPT,
    ),
    "SRLG": (
        SET_CC_ONE + "         LG    3,DNEG\n" "         SRLG  5,3,63\n",
        {5: 0x00000000_00000001},
        CC_KEPT,
    ),
}

ROTATES: Mapping[str, Case] = {
    "RLL": (
        SET_CC_ONE + "         L     3,NEG\n" "         RLL   5,3,1\n",
        {5: HIGH_FILL | 0x00000003},
        CC_KEPT,
    ),
    "RLL amount 33": (
        SET_CC_ONE + "         L     3,NEG\n" "         RLL   5,3,33\n",
        {5: HIGH_FILL | 0x00000003},
        CC_KEPT,
    ),
    "RLLG": (
        SET_CC_ONE + SRC_INTO_3 + "         RLLG  5,3,4\n",
        {5: 0x12345678_9ABCDEF0},
        CC_KEPT,
    ),
}

SIGNED_SHIFTS: Mapping[str, Case] = {
    "SRA": (
        "         L     2,NEG\n" "         SRA   2,1\n",
        {2: HIGH_FILL | 0xC0000000},
        CC_NEGATIVE,
    ),
    "SRAK": (
        "         L     3,POS\n" "         SRAK  5,3,31\n",
        {5: HIGH_FILL},
        CC_ZERO,
    ),
    "SRAG": (
        "         LG    3,DPOS\n" "         SRAG  5,3,4\n",
        {5: 0x07FFFFFF_FFFFFFF7},
        CC_POSITIVE,
    ),
    "SLA": (
        "         LHI   2,-3\n" "         SLA   2,2\n",
        {2: HIGH_FILL | 0xFFFFFFF4},
        CC_NEGATIVE,
    ),
    "SRA amount 40": (
        "         L     2,NEG\n" "         SRA   2,40\n",
        {2: HIGH_FILL | 0xFFFFFFFF},
        CC_NEGATIVE,
    ),
    "SLA amount 32": (
        "         LHI   2,1\n" "         SLA   2,32\n",
        {2: HIGH_FILL},
        CC_OVERFLOW,
    ),
    "SLA overflow": (
        "         L     2,POS\n" "         SLA   2,1\n",
        {2: HIGH_FILL | 0x7FFEFFFC},
        CC_OVERFLOW,
    ),
    "SLAK": (
        "         LHI   3,5\n" "         SLAK  5,3,3\n",
        {3: HIGH_FILL | 5, 5: HIGH_FILL | 40},
        CC_POSITIVE,
    ),
    "SLAG": (
        "         LG    3,DNEG\n" "         SLAG  5,3,1\n",
        {5: 0x80000000_00000102},
        CC_OVERFLOW,
    ),
}

DOUBLE_SHIFTS: Mapping[str, Case] = {
    "SLDL": (
        SET_CC_ONE
        + "         L     2,NEG\n"
        + "         L     3,POS\n"
        + "         SLDL  2,4\n",
        {2: HIGH_FILL | 0x00000017, 3: HIGH_FILL | 0xFFF7FFE0},
        CC_KEPT,
    ),
    "SRDL": (
        SET_CC_ONE
        + "         L     2,NEG\n"
        + "         L     3,POS\n"
        + "         SRDL  2,36\n",
        {2: HIGH_FILL, 3: HIGH_FILL | 0x08000000},
        CC_KEPT,
    ),
    "SRDA": (
        "         L     2,NEG\n" "         L     3,POS\n" "         SRDA  2,36\n",
        {2: HIGH_FILL | 0xFFFFFFFF, 3: HIGH_FILL | 0xF8000000},
        CC_NEGATIVE,
    ),
    "SLDA": (
        "         LHI   2,0\n" "         LHI   3,-1\n" "         SLDA  2,1\n",
        {2: HIGH_FILL | 0x00000001, 3: HIGH_FILL | 0xFFFFFFFE},
        CC_POSITIVE,
    ),
    "SLDA overflow": (
        "         L     2,POS\n" "         LHI   3,0\n" "         SLDA  2,2\n",
        {2: HIGH_FILL | 0x7FFDFFF8, 3: HIGH_FILL},
        CC_OVERFLOW,
    ),
}

INSERTS: Mapping[str, Case] = {
    "RISBG": (
        SRC_INTO_3 + "         RISBG 5,3,40,43,4\n",
        {5: 0xA5A5A5A5_A5B5A5A5},
        CC_NEGATIVE,
    ),
    "RISBG wrapping range": (
        SRC_INTO_3 + "         RISBG 5,3,62,1\n",
        {5: 0x25A5A5A5_A5A5A5A7},
        CC_POSITIVE,
    ),
    "RISBGZ": (
        SRC_INTO_3 + "         RISBGZ 5,3,40,43,4\n",
        {5: 0x00000000_00B00000},
        CC_POSITIVE,
    ),
    "RISBGZ zero": (
        SRC_INTO_3 + "         RISBGZ 5,3,0,6\n",
        {5: 0},
        CC_ZERO,
    ),
    "RISBGN": (
        SET_CC_ONE + SRC_INTO_3 + "         RISBGN 5,3,0,31,32\n",
        {5: 0x89ABCDEF_A5A5A5A5},
        CC_KEPT,
    ),
    "RISBGNZ": (
        SET_CC_ONE + SRC_INTO_3 + "         RISBGNZ 5,3,32,63,32\n",
        {5: 0x00000000_01234567},
        CC_KEPT,
    ),
    "RISBHG": (
        SET_CC_ONE + SRC_INTO_3 + "         RISBHG 5,3,8,15\n",
        {5: 0xA523A5A5_A5A5A5A5},
        CC_KEPT,
    ),
    "RISBHGZ wrapping range": (
        SET_CC_ONE + SRC_INTO_3 + "         RISBHGZ 5,3,24,7\n",
        {5: 0x01000067_A5A5A5A5},
        CC_KEPT,
    ),
    "RISBLG": (
        SET_CC_ONE + SRC_INTO_3 + "         RISBLG 5,3,8,15\n",
        {5: 0xA5A5A5A5_A5ABA5A5},
        CC_KEPT,
    ),
    "RISBLGZ": (
        SET_CC_ONE + SRC_INTO_3 + "         RISBLGZ 5,3,8,11\n",
        {5: 0xA5A5A5A5_00A00000},
        CC_KEPT,
    ),
}

HIGH_WORD_MOVES: Mapping[str, Case] = {
    mnemonic: (
        SET_CC_ONE + SRC_AND_SRCP + f"         {mnemonic:<7}5,3\n",
        {5: value},
        CC_KEPT,
    )
    for mnemonic, value in (
        ("LHHR", 0x01234567_76543210),
        ("LHLR", 0x89ABCDEF_76543210),
        ("LLHFR", 0xFEDCBA98_01234567),
        ("LLHHHR", 0x00004567_76543210),
        ("LLHHLR", 0x0000CDEF_76543210),
        ("LLHLHR", 0xFEDCBA98_00004567),
        ("LLCHHR", 0x00000067_76543210),
        ("LLCHLR", 0x000000EF_76543210),
        ("LLCLHR", 0xFEDCBA98_00000067),
    )
}

HIGH_WORD_SHIFTS: Mapping[str, Case] = {
    mnemonic: (
        SET_CC_ONE + SRC_AND_SRCP + f"         {mnemonic:<7}5,3,4\n",
        {5: value},
        CC_KEPT,
    )
    for mnemonic, value in (
        ("SLLHH", 0x12345670_76543210),
        ("SLLHL", 0x9ABCDEF0_76543210),
        ("SRLHH", 0x00123456_76543210),
        ("SRLHL", 0x089ABCDE_76543210),
        ("SLLLH", 0xFEDCBA98_12345670),
        ("SRLLH", 0xFEDCBA98_00123456),
    )
}

SELECTED_BITS: Mapping[str, Case] = {
    "RNSBG": (
        SRC_INTO_3 + "         RNSBG 5,3,32,63\n",
        {5: 0xA5A5A5A5_81A185A5},
        CC_NONZERO,
    ),
    "RNSBGT": (
        SRC_INTO_3 + "         RNSBGT 5,3,44,47\n",
        {5: FILL},
        CC_NONZERO,
    ),
    "NHHR": (
        SRC_AND_SRCP + "         NHHR  5,3\n",
        {5: 0x00000000_76543210},
        CC_ZERO,
    ),
    "NHLR": (
        SRC_AND_SRCP + "         NHLR  5,3\n",
        {5: 0x88888888_76543210},
        CC_NONZERO,
    ),
    "NLHR": (
        SRC_AND_SRCP + "         NLHR  5,3\n",
        {5: 0xFEDCBA98_00000000},
        CC_ZERO,
    ),
    "ROSBG": (
        SRC_INTO_3 + "         ROSBG 5,3,56,63\n",
        {5: 0xA5A5A5A5_A5A5A5EF},
        CC_NONZERO,
    ),
    "ROSBGT": (
        SRC_INTO_3 + "         ROSBGT 5,3,8,15\n",
        {5: FILL},
        CC_NONZERO,
    ),
    "OHHR": (
        SRC_AND_SRCP + "         OHHR  5,3\n",
        {5: 0xFFFFFFFF_76543210},
        CC_NONZERO,
    ),
    "OHLR": (
        SRC_INTO_3 + "         OHLR  5,3\n",
        {5: 0xADAFEDEF_A5A5A5A5},
        CC_NONZERO,
    ),
    "OLHR": (
        SRC_INTO_3 + "         OLHR  5,3\n",
        {5: 0xA5A5A5A5_A5A7E5E7},
        CC_NONZERO,
    ),
    "RXSBG": (
        SRC_INTO_3 + "         RXSBG 5,3,0,63\n",
        {5: 0xA486E0C2_2C0E684A},
        CC_NONZERO,
    ),
    "RXSBGT": (
        SRC_INTO_3 + "         RXSBGT 5,3,0,63,4\n",
        {5: FILL},
        CC_NONZERO,
    ),
    "XHHR": (
        "         LG    3,SRC\n" "         LG    5,SRC\n" "         XHHR  5,3\n",
        {5: 0x00000000_89ABCDEF},
        CC_ZERO,
    ),
    "XHLR": (
        SRC_AND_SRCP + "         XHLR  5,3\n",
        {5: 0x77777777_76543210},
        CC_NONZERO,
    ),
    "XLHR": (
        SRC_AND_SRCP + "         XLHR  5,3\n",
        {5: 0xFEDCBA98_77777777},
        CC_NONZERO,
    ),
}

CASES: Mapping[str, Case] = {
    **LOGICAL_SHIFTS,
    **ROTATES,
    **SIGNED_SHIFTS,
    **DOUBLE_SHIFTS,
    **INSERTS,
    **HIGH_WORD_MOVES,
    **HIGH_WORD_SHIFTS,
    **SELECTED_BITS,
}
