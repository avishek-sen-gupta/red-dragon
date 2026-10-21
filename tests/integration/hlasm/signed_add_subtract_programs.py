# pyright: standard
"""Signed add and subtract programs, one per mnemonic, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import HIGH_FILL

type Case = tuple[str, Mapping[int, int], int]

CC_ZERO = 0
CC_NEGATIVE = 1
CC_POSITIVE = 2
CC_OVERFLOW = 3

CASES: Mapping[str, Case] = {
    "A": (
        "         L     2,NEG\n" "         A     2,NEG\n",
        {2: HIGH_FILL | 0x00000002},
        CC_OVERFLOW,
    ),
    "AY": (
        "         L     3,NEG\n" "         AY    3,POS\n",
        {3: HIGH_FILL | 0xFFFF7FFF},
        CC_NEGATIVE,
    ),
    "AR": (
        "         LHI   4,5\n" "         LHI   5,-5\n" "         AR    4,5\n",
        {4: HIGH_FILL | 0x00000000, 5: HIGH_FILL | 0xFFFFFFFB},
        CC_ZERO,
    ),
    "ARK": (
        "         L     3,POS\n" "         LHI   4,2\n" "         ARK   5,3,4\n",
        {
            3: HIGH_FILL | 0x7FFF7FFE,
            4: HIGH_FILL | 0x00000002,
            5: HIGH_FILL | 0x7FFF8000,
        },
        CC_POSITIVE,
    ),
    "AH": (
        "         L     2,NEG\n" "         AH    2,NEG\n",
        {2: HIGH_FILL | 0x7FFF8001},
        CC_OVERFLOW,
    ),
    "AHY": (
        "         L     3,POS\n" "         AHY   3,POS\n",
        {3: HIGH_FILL | 0x7FFFFFFD},
        CC_POSITIVE,
    ),
    "AHI": (
        "         LHI   4,-1\n" "         AHI   4,-32768\n",
        {4: HIGH_FILL | 0xFFFF7FFF},
        CC_NEGATIVE,
    ),
    "AFI": (
        "         L     5,POS\n" "         AFI   5,X'80008002'\n",
        {5: HIGH_FILL | 0x00000000},
        CC_ZERO,
    ),
    "AHIK": (
        "         L     3,NEG\n" "         AHIK  6,3,-2\n",
        {3: HIGH_FILL | 0x80000001, 6: HIGH_FILL | 0x7FFFFFFF},
        CC_OVERFLOW,
    ),
    "ASI": (
        "         L     2,POS\n"
        "         ST    2,OUT\n"
        "         ASI   OUT,-128\n"
        "         L     7,OUT\n",
        {7: HIGH_FILL | 0x7FFF7F7E},
        CC_POSITIVE,
    ),
    "AG": (
        "         LG    2,DPOS\n" "         AG    2,DPOS\n",
        {2: 0xFFFFFFFF_FFFFFEFC},
        CC_OVERFLOW,
    ),
    "AGR": (
        "         LG    3,DNEG\n" "         LG    4,DPOS\n" "         AGR   3,4\n",
        {3: 0xFFFFFFFF_FFFFFFFF},
        CC_NEGATIVE,
    ),
    "AGRK": (
        "         LGHI  3,7\n" "         LGHI  4,-7\n" "         AGRK  5,3,4\n",
        {3: 7, 4: 0xFFFFFFFF_FFFFFFF9, 5: 0},
        CC_ZERO,
    ),
    "AGF": (
        "         LG    2,SRC\n" "         AGF   2,NEG\n",
        {2: 0x01234567_09ABCDF0},
        CC_POSITIVE,
    ),
    "AGFR": (
        "         LG    3,DPOS\n" "         L     4,NEG\n" "         AGFR  3,4\n",
        {3: 0x7FFFFFFF_7FFFFF7F},
        CC_POSITIVE,
    ),
    "AGH": (
        "         LG    2,DNEG\n" "         AGH   2,NEG\n",
        {2: 0x7FFFFFFF_FFFF8081},
        CC_OVERFLOW,
    ),
    "AGHI": (
        "         LGHI  3,-5\n" "         AGHI  3,5\n",
        {3: 0},
        CC_ZERO,
    ),
    "AGFI": (
        "         LG    4,DNEG\n" "         AGFI  4,-129\n",
        {4: 0x80000000_00000000},
        CC_NEGATIVE,
    ),
    "AGHIK": (
        "         LGHI  3,-1\n" "         AGHIK 5,3,2\n",
        {3: 0xFFFFFFFF_FFFFFFFF, 5: 1},
        CC_POSITIVE,
    ),
    "AGSI": (
        "         AGSI  OUT,255\n" "         LG    7,OUT\n",
        {7: 0xFFFFFFFF_FFFFFFFE},
        CC_NEGATIVE,
    ),
    "S": (
        "         L     2,NEG\n" "         S     2,WORDS+4\n",
        {2: HIGH_FILL | 0x7FFFFFFF},
        CC_OVERFLOW,
    ),
    "SY": (
        "         L     3,POS\n" "         SY    3,POS\n",
        {3: HIGH_FILL | 0x00000000},
        CC_ZERO,
    ),
    "SR": (
        "         LHI   4,3\n" "         LHI   5,5\n" "         SR    4,5\n",
        {4: HIGH_FILL | 0xFFFFFFFE},
        CC_NEGATIVE,
    ),
    "SRK": (
        "         L     3,POS\n" "         LHI   4,-2\n" "         SRK   5,3,4\n",
        {
            3: HIGH_FILL | 0x7FFF7FFE,
            4: HIGH_FILL | 0xFFFFFFFE,
            5: HIGH_FILL | 0x7FFF8000,
        },
        CC_POSITIVE,
    ),
    "SH": (
        "         L     2,POS\n" "         SH    2,NEG\n",
        {2: HIGH_FILL | 0x7FFFFFFE},
        CC_POSITIVE,
    ),
    "SHY": (
        "         L     3,NEG\n" "         SHY   3,POS\n",
        {3: HIGH_FILL | 0x7FFF8002},
        CC_OVERFLOW,
    ),
    "SG": (
        "         LG    2,DNEG\n" "         SG    2,DPOS\n",
        {2: 0x00000000_00000103},
        CC_OVERFLOW,
    ),
    "SGR": (
        "         LG    3,SRC\n" "         LG    4,SRCP\n" "         SGR   3,4\n",
        {3: 0x02468ACF_13579BDF},
        CC_POSITIVE,
    ),
    "SGRK": (
        "         LG    3,SRC\n" "         LG    4,SRC\n" "         SGRK  5,3,4\n",
        {3: 0x01234567_89ABCDEF, 5: 0},
        CC_ZERO,
    ),
    "SGF": (
        "         LGHI  2,-1\n" "         SGF   2,POS\n",
        {2: 0xFFFFFFFF_80008001},
        CC_NEGATIVE,
    ),
    "SGFR": (
        "         LG    3,DNEG\n" "         L     4,POS\n" "         SGFR  3,4\n",
        {3: 0x7FFFFFFF_80008083},
        CC_OVERFLOW,
    ),
    "SGH": (
        "         LGHI  2,1\n" "         SGH   2,WORDS+2\n",
        {2: 0},
        CC_ZERO,
    ),
}
