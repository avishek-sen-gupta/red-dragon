# pyright: standard
"""Storage move programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import ABEND, HIGH_FILL, based_program

type Case = tuple[str, Mapping[int, int], int]

CC_ZERO = 0
CC_LOW = 1
CC_HIGH = 2
CC_OVERLAP = 3
CC_SET_BY_LTR = 1
CC_ZERO_DIFFERENCE = 2
NEGATIVE_CC = "         LTR   2,2\n"

MOVE_DATA = (
    "         DS    0F\n"
    "LEN8     DC    X'AB000008'\n"
    "PAD5     DC    X'40000005'\n"
    "PADBIG   DC    X'5C000000'\n"
    "MVOA     DC    X'7788990C'\n"
    "MVOB     DC    X'123456'\n"
    "MVOC     DC    X'990C'\n"
    "MVOX     DC    X'12345C00'\n"
    "MVOY     DC    X'123456789C00'\n"
    "STR      DC    X'C1C2C300C4'\n"
    "BIG      DC    264X'00'\n"
)


def move_program(body: str) -> str:
    return based_program(body, ABEND + MOVE_DATA)


IMMEDIATES: Mapping[str, Case] = {
    "MVI": (
        NEGATIVE_CC + "         MVI   OUT+1,X'C1'\n" "         LG    7,OUT\n",
        {7: 0xFFC1FFFF_FFFFFFFF},
        CC_SET_BY_LTR,
    ),
    "MVIY": (
        NEGATIVE_CC + "         MVIY  OUT+7,X'00'\n" "         LG    7,OUT\n",
        {7: 0xFFFFFFFF_FFFFFF00},
        CC_SET_BY_LTR,
    ),
    "MVHHI": (
        NEGATIVE_CC + "         MVHHI OUT+2,X'1234'\n" "         LG    7,OUT\n",
        {7: 0xFFFF1234_FFFFFFFF},
        CC_SET_BY_LTR,
    ),
    "MVHI": (
        "         XC    OUT(8),OUT\n" + NEGATIVE_CC + "         MVHI  OUT,-2\n"
        "         MVHI  OUT+4,5\n"
        "         LG    7,OUT\n",
        {7: 0xFFFFFFFE_00000005},
        CC_SET_BY_LTR,
    ),
    "MVGHI": (
        "         XC    OUT(16),OUT\n" + NEGATIVE_CC + "         MVGHI OUT,-3\n"
        "         MVGHI OUT+8,X'7FFF'\n"
        "         LG    7,OUT\n"
        "         LG    8,OUT+8\n",
        {7: 0xFFFFFFFF_FFFFFFFD, 8: 0x7FFF},
        CC_SET_BY_LTR,
    ),
}

CHARACTER_MOVES: Mapping[str, Case] = {
    "MVC": (
        NEGATIVE_CC + "         MVC   OUT(8),SRC\n"
        "         LG    7,OUT\n"
        "         LG    8,OUT+8\n",
        {7: 0x01234567_89ABCDEF, 8: 0xFFFFFFFF_FFFFFFFF},
        CC_SET_BY_LTR,
    ),
    "MVC length 0": (
        "         MVC   OUT(0),SRC\n" "         LG    7,OUT\n",
        {7: 0x01FFFFFF_FFFFFFFF},
        CC_ZERO,
    ),
    "MVC to the left": (
        "         MVC   SRC(7),SRC+1\n" "         LG    7,SRC\n",
        {7: 0x23456789_ABCDEFEF},
        CC_ZERO,
    ),
    "MVC propagates": (
        "         MVI   OUT,X'5A'\n"
        "         MVC   OUT+1(7),OUT\n"
        "         LG    7,OUT\n"
        "         LG    8,OUT+8\n",
        {7: 0x5A5A5A5A_5A5A5A5A, 8: 0xFFFFFFFF_FFFFFFFF},
        CC_ZERO,
    ),
    "MVC propagates 256": (
        "         MVI   BIG,X'77'\n"
        "         MVC   BIG+1(255),BIG\n"
        "         LG    7,BIG+248\n"
        "         LLC   8,BIG+256\n",
        {7: 0x77777777_77777777, 8: HIGH_FILL},
        CC_ZERO,
    ),
    "MVCIN": (
        NEGATIVE_CC + "         MVCIN OUT(8),SRC+7\n" "         LG    7,OUT\n",
        {7: 0xEFCDAB89_67452301},
        CC_SET_BY_LTR,
    ),
    "MVN": (
        NEGATIVE_CC + "         MVN   OUT(8),SRC\n" "         LG    7,OUT\n",
        {7: 0xF1F3F5F7_F9FBFDFF},
        CC_SET_BY_LTR,
    ),
    "MVZ": (
        NEGATIVE_CC + "         MVZ   OUT(8),SRC\n" "         LG    7,OUT\n",
        {7: 0x0F2F4F6F_8FAFCFEF},
        CC_SET_BY_LTR,
    ),
    "MVN propagates": (
        "         MVI   OUT,X'35'\n"
        "         MVN   OUT+1(7),OUT\n"
        "         LG    7,OUT\n",
        {7: 0x35F5F5F5_F5F5F5F5},
        CC_ZERO,
    ),
    "MVCIN overlaps one byte": (
        "         MVC   OUT(8),SRC\n"
        "         MVCIN OUT+3(4),OUT+3\n"
        "         LG    7,OUT\n",
        {7: 0x01234567_452301EF},
        CC_ZERO,
    ),
    "MVO onto itself": (
        "         MVO   MVOX(3),MVOX(3)\n" "         L     7,MVOX\n",
        {7: HIGH_FILL | 0x2345CC00},
        CC_ZERO,
    ),
    "MVO overlapping right": (
        "         MVO   MVOY(3),MVOY+1(3)\n" "         L     7,MVOY\n",
        {7: HIGH_FILL | 0x78678678},
        CC_ZERO,
    ),
    "MVZ propagates": (
        "         MVI   OUT,X'3C'\n"
        "         MVZ   OUT+1(7),OUT\n"
        "         LG    7,OUT\n",
        {7: 0x3C3F3F3F_3F3F3F3F},
        CC_ZERO,
    ),
    "MVO": (
        NEGATIVE_CC + "         MVO   MVOA(4),MVOB(3)\n" "         L     7,MVOA\n",
        {7: HIGH_FILL | 0x0123456C},
        CC_SET_BY_LTR,
    ),
    "MVO truncates": (
        "         MVO   MVOC(2),MVOB(3)\n" "         LLH   7,MVOC\n",
        {7: HIGH_FILL | 0x456C},
        CC_ZERO,
    ),
}

RIGHT_TO_LEFT: Mapping[str, Case] = {
    "MVCRL": (
        NEGATIVE_CC + "         LHI   0,7\n"
        "         MVCRL OUT,SRC\n"
        "         LG    7,OUT\n",
        {7: 0x01234567_89ABCDEF},
        CC_SET_BY_LTR,
    ),
    "MVCRL opens a hole": (
        "         MVC   OUT(8),SRC\n"
        "         LHI   0,6\n"
        "         MVCRL OUT+1,OUT\n"
        "         LG    7,OUT\n",
        {7: 0x01012345_6789ABCD},
        CC_ZERO,
    ),
}

LONG_MOVES: Mapping[str, Case] = {
    "MVCL": (
        "         LA    2,OUT\n"
        "         L     3,LEN8\n"
        "         LA    4,SRC\n"
        "         L     5,PAD5\n"
        "         MVCL  2,4\n"
        "         LG    7,OUT\n",
        {3: HIGH_FILL | 0xAB000000, 5: HIGH_FILL | 0x40000000, 7: 0x01234567_89404040},
        CC_HIGH,
    ),
    "MVCL registers": (
        "         LA    2,OUT\n"
        "         L     3,LEN8\n"
        "         LA    4,SRC\n"
        "         L     5,PAD5\n"
        "         MVCL  2,4\n"
        "         LA    9,OUT+8\n"
        "         SLR   2,9\n"
        "         LA    9,SRC+5\n"
        "         SLR   4,9\n",
        {2: HIGH_FILL, 4: HIGH_FILL},
        CC_ZERO_DIFFERENCE,
    ),
    "MVCL lengths equal": (
        "         LA    2,OUT\n"
        "         LHI   3,8\n"
        "         LA    4,SRC\n"
        "         LHI   5,8\n"
        "         MVCL  2,4\n"
        "         LG    7,OUT\n",
        {3: HIGH_FILL, 5: HIGH_FILL, 7: 0x01234567_89ABCDEF},
        CC_ZERO,
    ),
    "MVCL first shorter": (
        "         LA    2,OUT\n"
        "         LHI   3,4\n"
        "         LA    4,SRC\n"
        "         LHI   5,8\n"
        "         MVCL  2,4\n"
        "         LG    7,OUT\n",
        {3: HIGH_FILL, 5: HIGH_FILL | 4, 7: 0x01234567_FFFFFFFF},
        CC_LOW,
    ),
    "MVCL first length zero": (
        "         LA    2,OUT\n"
        "         LHI   3,0\n"
        "         LA    4,SRC\n"
        "         LHI   5,8\n"
        "         MVCL  2,4\n"
        "         LG    7,OUT\n",
        {3: HIGH_FILL, 5: HIGH_FILL | 8, 7: 0xFFFFFFFF_FFFFFFFF},
        CC_LOW,
    ),
    "MVCL destructive overlap": (
        "         MVC   OUT(8),SRC\n"
        "         LA    2,OUT+1\n"
        "         LHI   3,7\n"
        "         LA    4,OUT\n"
        "         LHI   5,7\n"
        "         MVCL  2,4\n"
        "         LG    7,OUT\n",
        {3: HIGH_FILL | 7, 5: HIGH_FILL | 7, 7: 0x01234567_89ABCDEF},
        CC_OVERLAP,
    ),
    "MVCL pads 256": (
        "         LA    2,BIG\n"
        "         LHI   3,256\n"
        "         LA    4,SRC\n"
        "         L     5,PADBIG\n"
        "         MVCL  2,4\n"
        "         LG    7,BIG+248\n"
        "         LLC   8,BIG+256\n",
        {7: 0x5C5C5C5C_5C5C5C5C, 8: HIGH_FILL},
        CC_HIGH,
    ),
    "MVCLE": (
        "         LA    2,OUT\n"
        "         LHI   3,8\n"
        "         LA    4,SRC\n"
        "         LHI   5,3\n"
        "         MVCLE 2,4,X'40'\n"
        "         LG    7,OUT\n",
        {3: HIGH_FILL, 5: HIGH_FILL, 7: 0x01234540_40404040},
        CC_HIGH,
    ),
    "MVCLE registers": (
        "         LA    2,OUT\n"
        "         LHI   3,8\n"
        "         LA    4,SRC\n"
        "         LHI   5,3\n"
        "         MVCLE 2,4,X'40'\n"
        "         LA    9,OUT+8\n"
        "         SLR   2,9\n"
        "         LA    9,SRC+3\n"
        "         SLR   4,9\n",
        {2: HIGH_FILL, 4: HIGH_FILL},
        CC_ZERO_DIFFERENCE,
    ),
    "MVCLE first shorter": (
        "         LA    2,OUT\n"
        "         LHI   3,2\n"
        "         LA    4,SRC\n"
        "         LHI   5,8\n"
        "         MVCLE 2,4,0\n"
        "         LG    7,OUT\n",
        {3: HIGH_FILL, 5: HIGH_FILL | 6, 7: 0x0123FFFF_FFFFFFFF},
        CC_LOW,
    ),
    "MVCLE lengths zero": (
        "         LA    2,OUT\n"
        "         LHI   3,0\n"
        "         LA    4,SRC\n"
        "         LHI   5,0\n"
        "         MVCLE 2,4,0\n"
        "         LG    7,OUT\n",
        {3: HIGH_FILL, 5: HIGH_FILL, 7: 0xFFFFFFFF_FFFFFFFF},
        CC_ZERO,
    ),
    "MVCLU": (
        "         LA    2,OUT\n"
        "         LHI   3,8\n"
        "         LA    4,SRC\n"
        "         LHI   5,2\n"
        "         MVCLU 2,4,X'0020'\n"
        "         LG    7,OUT\n",
        {3: HIGH_FILL, 5: HIGH_FILL, 7: 0x01230020_00200020},
        CC_HIGH,
    ),
    "MVCLU registers": (
        "         LA    2,OUT\n"
        "         LHI   3,8\n"
        "         LA    4,SRC\n"
        "         LHI   5,2\n"
        "         MVCLU 2,4,X'0020'\n"
        "         LA    9,OUT+8\n"
        "         SLR   2,9\n"
        "         LA    9,SRC+2\n"
        "         SLR   4,9\n",
        {2: HIGH_FILL, 4: HIGH_FILL},
        CC_ZERO_DIFFERENCE,
    ),
    "MVCLU lengths equal": (
        "         LA    2,OUT\n"
        "         LHI   3,4\n"
        "         LA    4,SRC\n"
        "         LHI   5,4\n"
        "         MVCLU 2,4,0\n"
        "         LG    7,OUT\n",
        {3: HIGH_FILL, 5: HIGH_FILL, 7: 0x01234567_FFFFFFFF},
        CC_ZERO,
    ),
}

STRING_MOVES: Mapping[str, Case] = {
    "MVST": (
        "         LHI   0,0\n"
        "         LA    2,OUT\n"
        "         LA    4,STR\n"
        "         MVST  2,4\n"
        "         LG    7,OUT\n",
        {7: 0xC1C2C300_FFFFFFFF},
        CC_LOW,
    ),
    "MVST registers": (
        "         LHI   0,X'C2'\n"
        "         LA    2,OUT\n"
        "         LA    4,STR\n"
        "         MVST  2,4\n"
        "         LG    7,OUT\n"
        "         LA    9,OUT+1\n"
        "         SLR   2,9\n"
        "         LA    9,STR\n"
        "         SLR   4,9\n",
        {2: HIGH_FILL, 4: HIGH_FILL, 7: 0xC1C2FFFF_FFFFFFFF},
        CC_ZERO_DIFFERENCE,
    ),
}

CASES: Mapping[str, Case] = {
    **IMMEDIATES,
    **CHARACTER_MOVES,
    **RIGHT_TO_LEFT,
    **LONG_MOVES,
    **STRING_MOVES,
}

SPECIFICATION_EXCEPTIONS: Mapping[str, Case] = {
    "MVCLU odd length": (
        "         LA    2,OUT\n"
        "         LHI   3,7\n"
        "         LA    4,SRC\n"
        "         LHI   5,2\n"
        "         MVCLU 2,4,0\n",
        {3: HIGH_FILL | 7, 5: HIGH_FILL | 2},
        CC_ZERO,
    ),
    "MVST reserved GR0 bits": (
        NEGATIVE_CC + "         LHI   0,X'100'\n"
        "         LA    2,OUT\n"
        "         LA    4,STR\n"
        "         MVST  2,4\n",
        {},
        CC_SET_BY_LTR,
    ),
}
