# pyright: standard
"""Load and store programs shared by the VM tests and the z390 differential tests."""

RETURN = "         BR    14\n"
RETURN_ZERO = "         LHI   15,0\n" + RETURN
ABEND = "         ABEND 1\n"
FILL = 0xA5A5A5A5A5A5A5A5
HIGH_FILL = 0xA5A5A5A5_00000000

DATA = (
    "         DS    0D\n"
    "FILL     DC    10X'A5A5A5A5A5A5A5A5'\n"
    "NEG      DC    X'80000001'\n"
    "POS      DC    X'7FFF7FFE'\n"
    "DNEG     DC    X'8000000000000081'\n"
    "DPOS     DC    X'7FFFFFFFFFFFFF7E'\n"
    "SRC      DC    X'0123456789ABCDEF'\n"
    "SRCP     DC    X'FEDCBA9876543210'\n"
    "ZERO     DC    X'00000000'\n"
    "WORDS    DC    F'1',F'2',F'3',F'4'\n"
    "HIGHS    DC    X'111111112222222233333333'\n"
    "LOWS     DC    X'444444445555555566666666'\n"
    "         DS    0D\n"
    "OUT      DC    8X'FFFFFFFFFFFFFFFF'\n"
)


def based_program(body: str, end: str) -> str:
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         LMG   2,11,FILL\n"
        f"{body}{end}{DATA}"
        "         END\n"
    )


def relative_program(body: str, end: str) -> str:
    return (
        "T        CSECT\n"
        f"{body}{end}"
        "         DC    X'00'\n"
        "D        CSECT\n"
        f"{DATA}"
        "         END   T\n"
    )


STORAGE_LOADS_32 = (
    "         L     2,NEG\n"
    "         LY    3,POS\n"
    "         LH    4,NEG\n"
    "         LA    5,4\n"
    "         LHY   5,NEG(5)\n"
    "         LB    6,NEG\n"
    "         LLC   7,NEG\n"
    "         LLH   8,NEG\n"
    "         LZRF  9,NEG\n"
    "         LRV   10,NEG\n"
    "         IC    11,NEG\n"
)
STORAGE_LOADS_32_RESULTS = {
    2: HIGH_FILL | 0x80000001,
    3: HIGH_FILL | 0x7FFF7FFE,
    4: HIGH_FILL | 0xFFFF8000,
    5: HIGH_FILL | 0x00007FFF,
    6: HIGH_FILL | 0xFFFFFF80,
    7: HIGH_FILL | 0x00000080,
    8: HIGH_FILL | 0x00008000,
    9: HIGH_FILL | 0x80000000,
    10: HIGH_FILL | 0x01000080,
    11: 0xA5A5A5A5_A5A5A580,
}

PARTIAL_INSERTS = (
    "         ICY   2,POS\n" "         LRVH  3,NEG\n" "         LRVH  4,POS+2\n"
)
PARTIAL_INSERTS_RESULTS = {
    2: 0xA5A5A5A5_A5A5A57F,
    3: 0xA5A5A5A5_A5A50080,
    4: 0xA5A5A5A5_A5A5FE7F,
}

STORAGE_LOADS_64 = (
    "         LG    2,DNEG\n"
    "         LGF   3,NEG\n"
    "         LGH   4,NEG\n"
    "         LGB   5,NEG\n"
    "         LLGC  6,NEG\n"
    "         LLGH  7,NEG\n"
    "         LLGF  8,NEG\n"
    "         LLGT  9,NEG\n"
    "         LZRG  10,DNEG\n"
    "         LLZRGF 11,NEG\n"
)
STORAGE_LOADS_64_RESULTS = {
    2: 0x80000000_00000081,
    3: 0xFFFFFFFF_80000001,
    4: 0xFFFFFFFF_FFFF8000,
    5: 0xFFFFFFFF_FFFFFF80,
    6: 0x00000000_00000080,
    7: 0x00000000_00008000,
    8: 0x00000000_80000001,
    9: 0x00000000_00000001,
    10: 0x80000000_00000000,
    11: 0x00000000_80000000,
}

MORE_LOADS_64 = (
    "         LRVG  2,DNEG\n"
    "         LGF   5,POS\n"
    "         LGH   6,POS\n"
    "         LGB   7,POS\n"
)
MORE_LOADS_64_RESULTS = {
    2: 0x81000000_00000080,
    5: 0x00000000_7FFF7FFE,
    6: 0x00000000_00007FFF,
    7: 0x00000000_0000007F,
}

GUARDED_LOADS = "         LGG   3,DPOS\n" "         LLGFSG 4,NEG\n"
GUARDED_LOADS_RESULTS = {3: 0x00000000_7FFFFF7E, 4: 0x00000000_00000001}

REGISTER_LOADS = (
    "         LG    11,SRC\n"
    "         LG    10,SRCP\n"
    "         LGR   2,11\n"
    "         LBR   3,11\n"
    "         LGBR  4,11\n"
    "         LHR   5,11\n"
    "         LGHR  6,11\n"
    "         LGFR  7,11\n"
    "         LLCR  8,11\n"
    "         LLGCR 9,11\n"
    "         LR    10,11\n"
)
REGISTER_LOADS_RESULTS = {
    2: 0x01234567_89ABCDEF,
    3: HIGH_FILL | 0xFFFFFFEF,
    4: 0xFFFFFFFF_FFFFFFEF,
    5: HIGH_FILL | 0xFFFFCDEF,
    6: 0xFFFFFFFF_FFFFCDEF,
    7: 0xFFFFFFFF_89ABCDEF,
    8: HIGH_FILL | 0x000000EF,
    9: 0x00000000_000000EF,
    10: 0xFEDCBA98_89ABCDEF,
}

MORE_REGISTER_LOADS = (
    "         LG    11,SRC\n"
    "         LG    10,SRCP\n"
    "         LLHR  2,11\n"
    "         LLGHR 3,11\n"
    "         LLGFR 4,11\n"
    "         LLGTR 5,11\n"
    "         LRVR  6,11\n"
    "         LRVGR 7,11\n"
    "         LGFR  8,10\n"
    "         LBR   9,10\n"
)
MORE_REGISTER_LOADS_RESULTS = {
    2: HIGH_FILL | 0x0000CDEF,
    3: 0x00000000_0000CDEF,
    4: 0x00000000_89ABCDEF,
    5: 0x00000000_09ABCDEF,
    6: HIGH_FILL | 0xEFCDAB89,
    7: 0xEFCDAB89_67452301,
    8: 0x00000000_76543210,
    9: HIGH_FILL | 0x00000010,
}

RELATIVE_LOADS = (
    "         LGRL  2,FILL\n"
    "         LRL   2,NEG\n"
    "         LGRL  3,DNEG\n"
    "         LGFRL 4,NEG\n"
    "         LLGFRL 5,NEG\n"
    "         LGRL  6,FILL\n"
    "         LHRL  6,NEG\n"
    "         LGHRL 7,NEG\n"
    "         LGRL  8,FILL\n"
    "         LLHRL 8,NEG\n"
    "         LLGHRL 9,NEG\n"
)
RELATIVE_LOADS_RESULTS = {
    2: HIGH_FILL | 0x80000001,
    3: 0x80000000_00000081,
    4: 0xFFFFFFFF_80000001,
    5: 0x00000000_80000001,
    6: HIGH_FILL | 0xFFFF8000,
    7: 0xFFFFFFFF_FFFF8000,
    8: HIGH_FILL | 0x00008000,
    9: 0x00000000_00008000,
}

STORES = (
    "         LG    2,SRC\n"
    "         ST    2,OUT\n"
    "         STY   2,OUT+8\n"
    "         STG   2,OUT+16\n"
    "         STH   2,OUT+24\n"
    "         STHY  2,OUT+32\n"
    "         STC   2,OUT+40\n"
    "         STCY  2,OUT+49\n"
    "         STRV  2,OUT+56\n"
    "         LMG   3,10,OUT\n"
)
STORES_RESULTS = {
    3: 0x89ABCDEF_FFFFFFFF,
    4: 0x89ABCDEF_FFFFFFFF,
    5: 0x01234567_89ABCDEF,
    6: 0xCDEFFFFF_FFFFFFFF,
    7: 0xCDEFFFFF_FFFFFFFF,
    8: 0xEFFFFFFF_FFFFFFFF,
    9: 0xFFEFFFFF_FFFFFFFF,
    10: 0xEFCDAB89_FFFFFFFF,
}

MORE_STORES = (
    "         LG    2,SRC\n"
    "         STRVG 2,OUT\n"
    "         STRVH 2,OUT+8\n"
    "         LMG   3,4,OUT\n"
)
MORE_STORES_RESULTS = {3: 0xEFCDAB89_67452301, 4: 0xEFCDFFFF_FFFFFFFF}

RELATIVE_STORES = (
    "         LGRL  2,SRC\n"
    "         STRL  2,OUT\n"
    "         STGRL 2,OUT+8\n"
    "         STHRL 2,OUT+16\n"
    "         LGRL  3,OUT\n"
    "         LGRL  4,OUT+8\n"
    "         LGRL  5,OUT+16\n"
)
RELATIVE_STORES_RESULTS = {
    3: 0x89ABCDEF_FFFFFFFF,
    4: 0x01234567_89ABCDEF,
    5: 0xCDEFFFFF_FFFFFFFF,
}

LOAD_MULTIPLE_WRAPPING = (
    "         LGR   9,14\n"
    "         LMG   14,1,FILL\n"
    "         LM    14,1,WORDS\n"
    "         LGR   8,14\n"
    "         LGR   14,9\n"
)
LOAD_MULTIPLE_WRAPPING_RESULTS = {
    15: HIGH_FILL | 2,
    0: HIGH_FILL | 3,
    8: HIGH_FILL | 1,
}

MULTIPLES = (
    "         LMY   2,3,WORDS\n"
    "         LMD   4,5,HIGHS,LOWS\n"
    "         STM   2,3,OUT\n"
    "         STMY  4,4,OUT+12\n"
    "         STMG  4,5,OUT+16\n"
    "         LMG   6,9,OUT\n"
    "         LMG   10,11,WORDS\n"
)
MULTIPLES_RESULTS = {
    2: HIGH_FILL | 1,
    3: HIGH_FILL | 2,
    4: 0x11111111_44444444,
    5: 0x22222222_55555555,
    6: 0x00000001_00000002,
    7: 0xFFFFFFFF_44444444,
    8: 0x11111111_44444444,
    9: 0x22222222_55555555,
    10: 0x00000001_00000002,
    11: 0x00000003_00000004,
}

STORE_MASKED = (
    "         LG    2,SRC\n"
    "         STCM  2,B'1010',OUT\n"
    "         STCMY 2,B'0111',OUT+8\n"
    "         STCM  2,B'0000',OUT+16\n"
    "         STCM  2,B'1111',OUT+24\n"
    "         LMG   3,6,OUT\n"
)
STORE_MASKED_RESULTS = {
    3: 0x89CDFFFF_FFFFFFFF,
    4: 0xABCDEFFF_FFFFFFFF,
    5: 0xFFFFFFFF_FFFFFFFF,
    6: 0x89ABCDEF_FFFFFFFF,
}

INSERT_MASKED_CASES = (
    ("         ICM   2,B'1010',NEG\n", 0xA5A5A5A5_80A500A5, 1),
    ("         ICMY  2,B'0011',POS\n", 0xA5A5A5A5_A5A57FFF, 2),
    ("         ICM   2,B'1111',ZERO\n", 0xA5A5A5A5_00000000, 0),
    ("         ICM   2,B'0001',NEG+3\n", 0xA5A5A5A5_A5A5A501, 2),
    (
        "         ICM   3,B'1000',NEG\n         ICM   2,B'0000',NEG\n",
        FILL,
        0,
    ),
)
