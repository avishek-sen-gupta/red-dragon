# pyright: standard
"""Logical add and subtract programs, one per mnemonic, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import HIGH_FILL

type Case = tuple[str, Mapping[int, int], int]

CC_ZERO_NO_CARRY = 0
CC_NONZERO_NO_CARRY = 1
CC_ZERO_CARRY = 2
CC_NONZERO_CARRY = 3
CC_ZERO_BORROW = 0
CC_NONZERO_BORROW = 1
CC_ZERO_NO_BORROW = 2
CC_NONZERO_NO_BORROW = 3

ADDS: Mapping[str, Case] = {
    "AL": (
        "         L     2,NEG\n" "         AL    2,NEG\n",
        {2: HIGH_FILL | 0x00000002},
        CC_NONZERO_CARRY,
    ),
    "ALY": (
        "         L     3,POS\n" "         ALY   3,ZERO\n",
        {3: HIGH_FILL | 0x7FFF7FFE},
        CC_NONZERO_NO_CARRY,
    ),
    "ALR": (
        "         LHI   4,-1\n" "         LHI   5,1\n" "         ALR   4,5\n",
        {4: HIGH_FILL | 0x00000000, 5: HIGH_FILL | 0x00000001},
        CC_ZERO_CARRY,
    ),
    "ALRK": (
        "         L     3,POS\n" "         LHI   4,2\n" "         ALRK  5,3,4\n",
        {
            3: HIGH_FILL | 0x7FFF7FFE,
            4: HIGH_FILL | 0x00000002,
            5: HIGH_FILL | 0x7FFF8000,
        },
        CC_NONZERO_NO_CARRY,
    ),
    "ALG": (
        "         LG    2,DNEG\n" "         ALG   2,DNEG\n",
        {2: 0x00000000_00000102},
        CC_NONZERO_CARRY,
    ),
    "ALGR": (
        "         LGHI  3,0\n" "         LGHI  4,0\n" "         ALGR  3,4\n",
        {3: 0, 4: 0},
        CC_ZERO_NO_CARRY,
    ),
    "ALGRK": (
        "         LGHI  3,-1\n" "         LGHI  4,1\n" "         ALGRK 5,3,4\n",
        {3: 0xFFFFFFFF_FFFFFFFF, 4: 1, 5: 0},
        CC_ZERO_CARRY,
    ),
    "ALGF": (
        "         LG    2,SRC\n" "         ALGF  2,NEG\n",
        {2: 0x01234568_09ABCDF0},
        CC_NONZERO_NO_CARRY,
    ),
    "ALGFR": (
        "         LGHI  3,-1\n" "         L     4,NEG\n" "         ALGFR 3,4\n",
        {3: 0x00000000_80000000},
        CC_NONZERO_CARRY,
    ),
    "ALFI": (
        "         L     5,POS\n" "         ALFI  5,X'80008002'\n",
        {5: HIGH_FILL | 0x00000000},
        CC_ZERO_CARRY,
    ),
    "ALGFI": (
        "         LGHI  4,-1\n" "         ALGFI 4,X'FFFFFFFF'\n",
        {4: 0x00000000_FFFFFFFE},
        CC_NONZERO_CARRY,
    ),
    "ALHSIK": (
        "         L     3,NEG\n" "         ALHSIK 6,3,-2\n",
        {3: HIGH_FILL | 0x80000001, 6: HIGH_FILL | 0x7FFFFFFF},
        CC_NONZERO_CARRY,
    ),
    "ALGHSIK": (
        "         LGHI  3,1\n" "         ALGHSIK 5,3,-1\n",
        {3: 1, 5: 0},
        CC_ZERO_CARRY,
    ),
    "ALSI": (
        "         LHI   2,0\n"
        "         ST    2,OUT\n"
        "         ALSI  OUT,-1\n"
        "         L     7,OUT\n",
        {7: HIGH_FILL | 0xFFFFFFFF},
        CC_NONZERO_NO_CARRY,
    ),
    "ALGSI": (
        "         ALGSI OUT,255\n" "         LG    7,OUT\n",
        {7: 0xFFFFFFFF_FFFFFFFE},
        CC_NONZERO_CARRY,
    ),
}

CARRIES: Mapping[str, Case] = {
    "ALC": (
        "         LHI   2,-1\n"
        "         LHI   3,1\n"
        "         ALR   2,3\n"
        "         ALC   2,ZERO\n",
        {2: HIGH_FILL | 0x00000001},
        CC_NONZERO_NO_CARRY,
    ),
    "ALCR": (
        "         LHI   4,-1\n"
        "         ALR   4,4\n"
        "         LHI   5,1\n"
        "         ALCR  4,5\n",
        {4: HIGH_FILL | 0x00000000, 5: HIGH_FILL | 0x00000001},
        CC_ZERO_CARRY,
    ),
    "ALCG": (
        "         LGHI  2,5\n" "         ALGR  2,2\n" "         ALCG  2,DPOS\n",
        {2: 0x7FFFFFFF_FFFFFF88},
        CC_NONZERO_NO_CARRY,
    ),
    "ALCGR": (
        "         LGHI  3,0\n"
        "         LGHI  4,0\n"
        "         ALGR  3,4\n"
        "         ALCGR 3,4\n",
        {3: 0, 4: 0},
        CC_ZERO_NO_CARRY,
    ),
}

SUBTRACTS: Mapping[str, Case] = {
    "SL": (
        "         L     2,NEG\n" "         SL    2,POS\n",
        {2: HIGH_FILL | 0x00008003},
        CC_NONZERO_NO_BORROW,
    ),
    "SLY": (
        "         L     3,POS\n" "         SLY   3,POS\n",
        {3: HIGH_FILL | 0x00000000},
        CC_ZERO_NO_BORROW,
    ),
    "SLR": (
        "         LHI   4,0\n" "         LHI   5,1\n" "         SLR   4,5\n",
        {4: HIGH_FILL | 0xFFFFFFFF, 5: HIGH_FILL | 0x00000001},
        CC_NONZERO_BORROW,
    ),
    "SLRK": (
        "         L     3,POS\n" "         L     4,NEG\n" "         SLRK  5,3,4\n",
        {
            3: HIGH_FILL | 0x7FFF7FFE,
            4: HIGH_FILL | 0x80000001,
            5: HIGH_FILL | 0xFFFF7FFD,
        },
        CC_NONZERO_BORROW,
    ),
    "SLG": (
        "         LG    2,DPOS\n" "         SLG   2,DNEG\n",
        {2: 0xFFFFFFFF_FFFFFEFD},
        CC_NONZERO_BORROW,
    ),
    "SLGR": (
        "         LGHI  3,7\n" "         LGHI  4,7\n" "         SLGR  3,4\n",
        {3: 0, 4: 7},
        CC_ZERO_NO_BORROW,
    ),
    "SLGRK": (
        "         LGHI  3,-1\n" "         LGHI  4,1\n" "         SLGRK 5,3,4\n",
        {3: 0xFFFFFFFF_FFFFFFFF, 4: 1, 5: 0xFFFFFFFF_FFFFFFFE},
        CC_NONZERO_NO_BORROW,
    ),
    "SLGF": (
        "         LG    2,SRC\n" "         SLGF  2,NEG\n",
        {2: 0x01234567_09ABCDEE},
        CC_NONZERO_NO_BORROW,
    ),
    "SLGFR": (
        "         LGHI  3,0\n" "         L     4,NEG\n" "         SLGFR 3,4\n",
        {3: 0xFFFFFFFF_7FFFFFFF},
        CC_NONZERO_BORROW,
    ),
    "SLFI": (
        "         L     5,POS\n" "         SLFI  5,X'FFFFFFFF'\n",
        {5: HIGH_FILL | 0x7FFF7FFF},
        CC_NONZERO_BORROW,
    ),
    "SLGFI": (
        "         LG    4,DPOS\n" "         SLGFI 4,X'FFFFFFFF'\n",
        {4: 0x7FFFFFFE_FFFFFF7F},
        CC_NONZERO_NO_BORROW,
    ),
}

BORROWS: Mapping[str, Case] = {
    "SLB": (
        "         LHI   2,0\n" "         ALR   2,2\n" "         SLB   2,NEG\n",
        {2: HIGH_FILL | 0x7FFFFFFE},
        CC_NONZERO_BORROW,
    ),
    "SLBR": (
        "         LHI   4,0\n"
        "         LHI   5,1\n"
        "         SLR   4,5\n"
        "         LHI   4,0\n"
        "         LHI   5,-1\n"
        "         SLBR  4,5\n",
        {4: HIGH_FILL | 0x00000000, 5: HIGH_FILL | 0xFFFFFFFF},
        CC_ZERO_BORROW,
    ),
    "SLBG": (
        "         LGHI  2,5\n"
        "         LGHI  3,5\n"
        "         SLGR  2,3\n"
        "         SLBG  2,DPOS\n",
        {2: 0x80000000_00000082},
        CC_NONZERO_BORROW,
    ),
    "SLBGR": (
        "         LGHI  3,-1\n"
        "         LGHI  4,1\n"
        "         SLGR  3,4\n"
        "         LGHI  4,-2\n"
        "         SLBGR 3,4\n",
        {3: 0, 4: 0xFFFFFFFF_FFFFFFFE},
        CC_ZERO_NO_BORROW,
    ),
}

CASES: Mapping[str, Case] = {**ADDS, **CARRIES, **SUBTRACTS, **BORROWS}
