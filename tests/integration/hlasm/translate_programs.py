# pyright: standard
"""Translate programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import (
    ABEND,
    FILL,
    HIGH_FILL,
    based_program,
)

type Case = tuple[str, Mapping[int, int], int]

CC_NONE = 0
CC_FOUND = 1
CC_LAST = 2
CC_SET_BY_LTR = 1
SLR_EQUAL_CC = 2
SLR_NONZERO_CC = 3
BIT_32 = 0x80000000
NEGATIVE_CC = "         LTR   2,2\n"
SAVE_GR1 = "         LGR   7,1\n"
TABLE_ROW_BYTES = 16
TABLE_BYTES = 256


def _increment_table() -> str:
    rows = [
        bytes((start + i + 1) % TABLE_BYTES for i in range(TABLE_ROW_BYTES)).hex()
        for start in range(0, TABLE_BYTES, TABLE_ROW_BYTES)
    ]
    labels = ["TRTAB   "] + ["        "] * (len(rows) - 1)
    return "".join(
        f"{label} DC    X'{row.upper()}'\n"
        for label, row in zip(labels, rows, strict=True)
    )


TRANSLATE_DATA = (
    "         DS    0D\n"
    "FTAB     DC    64X'00',X'04',42X'00',X'08',148X'00'\n"
    "         DS    0D\n" + _increment_table() + "         DS    0D\n"
    "T11      DC    X'C1C2C3C4'\n"
    "         DS    0D\n"
    "T12      DC    X'00C100C200C300C4'\n"
    "         DS    0D\n"
    "ZT1      DC    X'00000500'\n"
    "         DS    0D\n"
    "ZT2      DC    X'0000000012340000'\n"
    "         DS    0D\n"
    "ZTL      DC    258X'00',X'0900'\n"
    "         DS    0D\n"
    "BIT32    DC    X'80000000'\n"
    "         DS    0D\n"
    "OUTT     DC    8X'FF'\n"
    "TXT      DC    C'AB,CD '\n"
    "OVL      DC    X'01020300'\n"
    "FLD      DC    X'0001020304050607'\n"
    "TRED     DC    X'0001024003'\n"
    "SRC1     DC    X'00010203'\n"
    "SRC2     DC    X'0000000100020003'\n"
    "ARGB     DC    X'000102'\n"
    "ARGH     DC    X'0000000100020003'\n"
    "ARGL     DC    X'01020002'\n"
)


def translate_program(body: str) -> str:
    return based_program(body, ABEND + TRANSLATE_DATA)


def _offset(register: int, address: str) -> str:
    return f"         LA    9,{address}\n" f"         SLR   {register},9\n"


def _pair(first: str, length: int, second: str) -> str:
    return (
        f"         LA    2,{first}\n"
        f"         LHI   3,{length}\n"
        f"         LA    4,{second}\n"
    )


def _characters(table: str, test: int, length: int, source: str) -> str:
    return f"         LA    1,{table}\n" f"         LHI   0,{test}\n" + _pair(
        "OUTT", length, source
    )


def _extended(table: str, argument: str, length: int) -> str:
    return (
        f"         LA    1,{table}\n"
        f"         LA    2,{argument}\n"
        f"         LHI   3,{length}\n"
    )


TRANSLATES: Mapping[str, Case] = {
    "TR": (
        NEGATIVE_CC + "         TR    FLD(8),TRTAB\n" "         LG    6,FLD\n",
        {6: 0x01020304_05060708},
        CC_SET_BY_LTR,
    ),
    "TR implicit length": (
        NEGATIVE_CC + "         TR    OVL,TRTAB\n" "         L     6,OVL\n",
        {6: HIGH_FILL | 0x02030401},
        CC_SET_BY_LTR,
    ),
    "TR explicit length 0 translates one byte": (
        NEGATIVE_CC + "         TR    FLD(0),TRTAB\n" "         LG    6,FLD\n",
        {6: 0x01010203_04050607},
        CC_SET_BY_LTR,
    ),
    "TR stores each byte before the next table fetch": (
        NEGATIVE_CC + "         TR    OVL(4),OVL\n" "         L     6,OVL\n",
        {6: HIGH_FILL | 0x02030002},
        CC_SET_BY_LTR,
    ),
}

TRANSLATE_AND_TESTS: Mapping[str, Case] = {
    "TRT found": (
        "         LG    1,FILL\n" "         TRT   TXT(6),FTAB\n",
        {2: FILL & ~0xFF | 0x08},
        CC_FOUND,
    ),
    "TRT found registers": (
        "         LG    1,FILL\n"
        "         TRT   TXT(6),FTAB\n" + _offset(1, "TXT+2") + SAVE_GR1,
        {7: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "TRT last byte": (
        "         LG    1,FILL\n" "         TRT   TXT(3),FTAB\n",
        {2: FILL & ~0xFF | 0x08},
        CC_LAST,
    ),
    "TRT none": (
        "         LG    1,FILL\n" "         TRT   TXT(2),FTAB\n" + SAVE_GR1,
        {2: FILL, 7: FILL},
        CC_NONE,
    ),
    "TRTR found": (
        "         LG    1,FILL\n" "         TRTR  TXT+5(6),FTAB\n",
        {2: FILL & ~0xFF | 0x04},
        CC_FOUND,
    ),
    "TRTR keeps bit 32": (
        "         LG    1,FILL\n"
        "         TRTR  TXT+5(6),FTAB\n" + _offset(1, "TXT+5") + SAVE_GR1,
        {7: HIGH_FILL | BIT_32},
        SLR_NONZERO_CC,
    ),
    "TRTR leftmost byte": (
        "         LG    1,FILL\n" "         TRTR  TXT+3(2),FTAB\n",
        {2: FILL & ~0xFF | 0x08},
        CC_LAST,
    ),
    "TRTR leftmost byte registers": (
        "         LG    1,FILL\n"
        "         TRTR  TXT+3(2),FTAB\n" + _offset(1, "TXT+2") + SAVE_GR1,
        {7: HIGH_FILL | BIT_32},
        SLR_NONZERO_CC,
    ),
    "TRTR none": (
        "         LG    1,FILL\n" "         TRTR  TXT+1(2),FTAB\n" + SAVE_GR1,
        {2: FILL, 7: FILL},
        CC_NONE,
    ),
}

TRANSLATE_EXTENDED: Mapping[str, Case] = {
    "TRE found": (
        "         LHI   0,X'7F40'\n"
        + _pair("TRED", 5, "TRTAB")
        + "         TRE   2,4\n"
        "         L     6,TRED\n",
        {3: HIGH_FILL | 2, 6: HIGH_FILL | 0x01020340},
        CC_FOUND,
    ),
    "TRE found registers": (
        "         LHI   0,X'7F40'\n"
        + _pair("TRED", 5, "TRTAB")
        + "         TRE   2,4\n"
        + _offset(2, "TRED+3"),
        {2: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "TRE exhausted": (
        "         LHI   0,X'FF'\n" + _pair("TRED", 5, "TRTAB") + "         TRE   2,4\n"
        "         L     6,TRED\n",
        {3: HIGH_FILL, 6: HIGH_FILL | 0x01020341},
        CC_NONE,
    ),
    "TRE exhausted registers": (
        "         LHI   0,X'FF'\n"
        + _pair("TRED", 5, "TRTAB")
        + "         O     2,BIT32\n"
        "         TRE   2,4\n" + _offset(2, "TRED+5"),
        {2: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "TRE length 0": (
        "         LHI   0,X'FF'\n" + _pair("TRED", 0, "TRTAB") + "         TRE   2,4\n"
        "         L     6,TRED\n",
        {3: HIGH_FILL, 6: HIGH_FILL | 0x00010240},
        CC_NONE,
    ),
}

TRANSLATE_CHARACTERS: Mapping[str, Case] = {
    "TROO exhausted": (
        _characters("T11", 0xFF, 4, "SRC1") + "         TROO  2,4\n"
        "         L     6,OUTT\n",
        {3: HIGH_FILL, 6: HIGH_FILL | 0xC1C2C3C4},
        CC_NONE,
    ),
    "TROO exhausted registers": (
        _characters("T11", 0xFF, 4, "SRC1")
        + "         TROO  2,4\n"
        + _offset(2, "OUTT+4")
        + _offset(4, "SRC1+4"),
        {2: HIGH_FILL, 4: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "TROO found": (
        _characters("T11", 0xC3, 4, "SRC1") + "         TROO  2,4\n"
        "         L     6,OUTT\n",
        {3: HIGH_FILL | 2, 6: HIGH_FILL | 0xC1C2FFFF},
        CC_FOUND,
    ),
    "TROO found registers": (
        _characters("T11", 0xC3, 4, "SRC1")
        + "         TROO  2,4\n"
        + _offset(2, "OUTT+2")
        + _offset(4, "SRC1+2"),
        {2: HIGH_FILL, 4: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "TROO without the test": (
        _characters("T11", 0xC3, 4, "SRC1") + "         TROO  2,4,1\n"
        "         L     6,OUTT\n",
        {3: HIGH_FILL, 6: HIGH_FILL | 0xC1C2C3C4},
        CC_NONE,
    ),
    "TROO table bits 61-63 ignored": (
        _characters("T11+5", 0xFF, 4, "SRC1") + "         TROO  2,4\n"
        "         L     6,OUTT\n",
        {3: HIGH_FILL, 6: HIGH_FILL | 0xC1C2C3C4},
        CC_NONE,
    ),
    "TROO length 0": (
        _characters("T11", 0xFF, 0, "SRC1") + "         TROO  2,4\n"
        "         L     6,OUTT\n",
        {3: HIGH_FILL, 6: HIGH_FILL | 0xFFFFFFFF},
        CC_NONE,
    ),
    "TROT found": (
        _characters("T12", 0xC3, 4, "SRC1") + "         TROT  2,4\n"
        "         LG    6,OUTT\n",
        {3: HIGH_FILL | 2, 6: 0x00C100C2_FFFFFFFF},
        CC_FOUND,
    ),
    "TROT found registers": (
        _characters("T12", 0xC3, 4, "SRC1")
        + "         TROT  2,4\n"
        + _offset(2, "OUTT+4")
        + _offset(4, "SRC1+2"),
        {2: HIGH_FILL, 4: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "TROT exhausted": (
        _characters("T12", 0xC3, 4, "SRC1") + "         TROT  2,4,1\n"
        "         LG    6,OUTT\n",
        {3: HIGH_FILL, 6: 0x00C100C2_00C300C4},
        CC_NONE,
    ),
    "TRTO exhausted": (
        _characters("T11", 0xFF, 8, "SRC2") + "         TRTO  2,4\n"
        "         L     6,OUTT\n",
        {3: HIGH_FILL, 6: HIGH_FILL | 0xC1C2C3C4},
        CC_NONE,
    ),
    "TRTO exhausted registers": (
        _characters("T11", 0xFF, 8, "SRC2")
        + "         TRTO  2,4\n"
        + _offset(2, "OUTT+4")
        + _offset(4, "SRC2+8"),
        {2: HIGH_FILL, 4: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "TRTO found": (
        _characters("T11", 0xC2, 8, "SRC2") + "         TRTO  2,4\n"
        "         L     6,OUTT\n",
        {3: HIGH_FILL | 6, 6: HIGH_FILL | 0xC1FFFFFF},
        CC_FOUND,
    ),
    "TRTT exhausted": (
        _characters("T12", 0xFF, 8, "SRC2") + "         TRTT  2,4\n"
        "         LG    6,OUTT\n",
        {3: HIGH_FILL, 6: 0x00C100C2_00C300C4},
        CC_NONE,
    ),
    "TRTT found first": (
        _characters("T12", 0xC1, 8, "SRC2") + "         TRTT  2,4\n"
        "         LG    6,OUTT\n",
        {3: HIGH_FILL | 8, 6: 0xFFFFFFFF_FFFFFFFF},
        CC_FOUND,
    ),
    "TRTT found registers": (
        _characters("T12", 0xC3, 8, "SRC2")
        + "         TRTT  2,4\n"
        + _offset(2, "OUTT+4")
        + _offset(4, "SRC2+4"),
        {2: HIGH_FILL, 4: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
}

TRANSLATE_AND_TEST_EXTENDED: Mapping[str, Case] = {
    "TRTE found": (
        _extended("FTAB", "TXT", 4) + "         TRTE  2,4\n",
        {3: HIGH_FILL | 2, 4: HIGH_FILL | 0x08},
        CC_FOUND,
    ),
    "TRTE found registers": (
        _extended("FTAB", "TXT", 4) + "         O     2,BIT32\n"
        "         TRTE  2,4\n" + _offset(2, "TXT+2"),
        {2: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "TRTE exhausted": (
        _extended("FTAB", "TXT", 2) + "         TRTE  2,4\n" + _offset(2, "TXT+2"),
        {2: HIGH_FILL, 3: HIGH_FILL, 4: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "TRTE exhausted CC": (
        _extended("FTAB", "TXT", 2) + "         TRTE  2,4\n",
        {3: HIGH_FILL, 4: HIGH_FILL},
        CC_NONE,
    ),
    "TRTE two-byte functions": (
        _extended("ZT2", "ARGB", 3) + "         TRTE  2,4,4\n",
        {3: HIGH_FILL | 1, 4: HIGH_FILL | 0x1234},
        CC_FOUND,
    ),
    "TRTE two-byte arguments": (
        _extended("ZT1", "ARGH", 8) + "         TRTE  2,4,8\n",
        {3: HIGH_FILL | 4, 4: HIGH_FILL | 0x05},
        CC_FOUND,
    ),
    "TRTE argument over 255 selects from the table": (
        _extended("ZTL", "ARGL", 4) + "         TRTE  2,4,8\n",
        {3: HIGH_FILL | 4, 4: HIGH_FILL | 0x09},
        CC_FOUND,
    ),
    "TRTE limit skips arguments over 255": (
        _extended("ZTL", "ARGL", 4) + "         TRTE  2,4,B'1010'\n",
        {3: HIGH_FILL, 4: HIGH_FILL},
        CC_NONE,
    ),
    "TRTE table bits 61-63 ignored": (
        _extended("FTAB+7", "TXT", 4) + "         TRTE  2,4\n",
        {3: HIGH_FILL | 2, 4: HIGH_FILL | 0x08},
        CC_FOUND,
    ),
    "TRTRE found": (
        _extended("FTAB", "TXT+3", 4) + "         TRTRE 2,4\n",
        {3: HIGH_FILL | 3, 4: HIGH_FILL | 0x08},
        CC_FOUND,
    ),
    "TRTRE found registers": (
        _extended("FTAB", "TXT+3", 4) + "         TRTRE 2,4\n" + _offset(2, "TXT+2"),
        {2: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "TRTRE exhausted": (
        _extended("FTAB", "TXT+1", 2) + "         TRTRE 2,4\n" + _offset(2, "TXT-1"),
        {2: HIGH_FILL, 3: HIGH_FILL, 4: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "TRTRE two-byte arguments and functions": (
        _extended("ZT2", "ARGH+6", 8) + "         TRTRE 2,4,12\n",
        {3: HIGH_FILL | 6, 4: HIGH_FILL | 0x1234},
        CC_FOUND,
    ),
    "TRTRE two-byte arguments and functions registers": (
        _extended("ZT2", "ARGH+6", 8)
        + "         TRTRE 2,4,12\n"
        + _offset(2, "ARGH+4"),
        {2: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
}

CASES: Mapping[str, Case] = {
    **TRANSLATES,
    **TRANSLATE_AND_TESTS,
    **TRANSLATE_EXTENDED,
    **TRANSLATE_CHARACTERS,
    **TRANSLATE_AND_TEST_EXTENDED,
}

SPECIFICATION_EXCEPTIONS: Mapping[str, Case] = {
    "TRTT odd length": (
        _characters("T12", 0xFF, 7, "SRC2") + "         TRTT  2,4\n",
        {3: HIGH_FILL | 7},
        CC_NONE,
    ),
    "TRTO odd length": (
        _characters("T11", 0xFF, 7, "SRC2") + "         TRTO  2,4\n",
        {3: HIGH_FILL | 7},
        CC_NONE,
    ),
    "TRTE two-byte arguments odd length": (
        _extended("ZT1", "ARGH", 7) + "         TRTE  2,4,8\n",
        {3: HIGH_FILL | 7},
        CC_NONE,
    ),
}
