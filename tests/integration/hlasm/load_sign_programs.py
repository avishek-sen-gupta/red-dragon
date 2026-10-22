# pyright: standard
"""Load and test, complement, positive and negative programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import HIGH_FILL

type Case = tuple[str, Mapping[int, int], int]

CC_ZERO = 0
CC_NEGATIVE = 1
CC_POSITIVE = 2
CC_OVERFLOW = 3

MINIMUM_WORD_IN_3 = "         LHI   3,1\n" "         SLL   3,31\n"
MINIMUM_DOUBLEWORD_IN_3 = "         LGHI  3,1\n" "         SLLG  3,3,63\n"
MINIMUM_WORD = HIGH_FILL | 0x80000000
MINIMUM_DOUBLEWORD = 0x80000000_00000000

CASES: Mapping[str, Case] = {
    "LT": (
        "         LT    2,NEG\n",
        {2: HIGH_FILL | 0x80000001},
        CC_NEGATIVE,
    ),
    "LTR": (
        "         L     3,POS\n" "         LTR   4,3\n",
        {3: HIGH_FILL | 0x7FFF7FFE, 4: HIGH_FILL | 0x7FFF7FFE},
        CC_POSITIVE,
    ),
    "LTR zero": (
        "         LHI   3,0\n" "         LTR   4,3\n",
        {3: HIGH_FILL, 4: HIGH_FILL},
        CC_ZERO,
    ),
    "LTG": (
        "         LTG   2,DNEG\n",
        {2: 0x80000000_00000081},
        CC_NEGATIVE,
    ),
    "LTGR": (
        "         LG    3,DPOS\n" "         LTGR  4,3\n",
        {3: 0x7FFFFFFF_FFFFFF7E, 4: 0x7FFFFFFF_FFFFFF7E},
        CC_POSITIVE,
    ),
    "LTGR zero": (
        "         LGHI  3,0\n" "         LTGR  4,3\n",
        {3: 0, 4: 0},
        CC_ZERO,
    ),
    "LTGF": (
        "         LTGF  2,NEG\n",
        {2: 0xFFFFFFFF_80000001},
        CC_NEGATIVE,
    ),
    "LTGFR": (
        "         L     3,NEG\n" "         LTGFR 4,3\n",
        {3: HIGH_FILL | 0x80000001, 4: 0xFFFFFFFF_80000001},
        CC_NEGATIVE,
    ),
    "LCR": (
        "         L     3,POS\n" "         LCR   4,3\n",
        {3: HIGH_FILL | 0x7FFF7FFE, 4: HIGH_FILL | 0x80008002},
        CC_NEGATIVE,
    ),
    "LCR minimum": (
        MINIMUM_WORD_IN_3 + "         LCR   4,3\n",
        {3: MINIMUM_WORD, 4: MINIMUM_WORD},
        CC_OVERFLOW,
    ),
    "LCGR": (
        "         LG    3,DNEG\n" "         LCGR  4,3\n",
        {3: 0x80000000_00000081, 4: 0x7FFFFFFF_FFFFFF7F},
        CC_POSITIVE,
    ),
    "LCGR minimum": (
        MINIMUM_DOUBLEWORD_IN_3 + "         LCGR  4,3\n",
        {3: MINIMUM_DOUBLEWORD, 4: MINIMUM_DOUBLEWORD},
        CC_OVERFLOW,
    ),
    "LCGFR": (
        "         L     3,NEG\n" "         LCGFR 4,3\n",
        {3: HIGH_FILL | 0x80000001, 4: 0x00000000_7FFFFFFF},
        CC_POSITIVE,
    ),
    "LCGFR minimum": (
        MINIMUM_WORD_IN_3 + "         LCGFR 4,3\n",
        {3: MINIMUM_WORD, 4: 0x00000000_80000000},
        CC_POSITIVE,
    ),
    "LPR": (
        "         L     3,NEG\n" "         LPR   4,3\n",
        {3: HIGH_FILL | 0x80000001, 4: HIGH_FILL | 0x7FFFFFFF},
        CC_POSITIVE,
    ),
    "LPR minimum": (
        MINIMUM_WORD_IN_3 + "         LPR   4,3\n",
        {3: MINIMUM_WORD, 4: MINIMUM_WORD},
        CC_OVERFLOW,
    ),
    "LPGR": (
        "         LG    3,DNEG\n" "         LPGR  4,3\n",
        {3: 0x80000000_00000081, 4: 0x7FFFFFFF_FFFFFF7F},
        CC_POSITIVE,
    ),
    "LPGR minimum": (
        MINIMUM_DOUBLEWORD_IN_3 + "         LPGR  4,3\n",
        {3: MINIMUM_DOUBLEWORD, 4: MINIMUM_DOUBLEWORD},
        CC_OVERFLOW,
    ),
    "LPGFR": (
        "         L     3,NEG\n" "         LPGFR 4,3\n",
        {3: HIGH_FILL | 0x80000001, 4: 0x00000000_7FFFFFFF},
        CC_POSITIVE,
    ),
    "LNR": (
        "         L     3,POS\n" "         LNR   4,3\n",
        {3: HIGH_FILL | 0x7FFF7FFE, 4: HIGH_FILL | 0x80008002},
        CC_NEGATIVE,
    ),
    "LNR zero": (
        "         LHI   3,0\n" "         LNR   4,3\n",
        {3: HIGH_FILL, 4: HIGH_FILL},
        CC_ZERO,
    ),
    "LNR minimum": (
        MINIMUM_WORD_IN_3 + "         LNR   4,3\n",
        {3: MINIMUM_WORD, 4: MINIMUM_WORD},
        CC_NEGATIVE,
    ),
    "LNGR": (
        "         LG    3,DPOS\n" "         LNGR  4,3\n",
        {3: 0x7FFFFFFF_FFFFFF7E, 4: 0x80000000_00000082},
        CC_NEGATIVE,
    ),
    "LNGFR": (
        "         L     3,NEG\n" "         LNGFR 4,3\n",
        {3: HIGH_FILL | 0x80000001, 4: 0xFFFFFFFF_80000001},
        CC_NEGATIVE,
    ),
}
