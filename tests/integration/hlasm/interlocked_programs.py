# pyright: standard
"""Interlocked-update programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; data sits at fixed offsets so word, doubleword and quadword boundaries are known."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import ABEND, FILL, HIGH_FILL

type Case = tuple[str, Mapping[int, int], int]

SRC = 0x01234567_89ABCDEF
SRCP = 0xFEDCBA98_76543210
DPAIR = 0x11111111_22222222
QB_LOW = 0x33333333_44444444
ONES = 0xFFFFFFFF_FFFFFFFF
REPLACEMENT_WORD = 0xAAAAAAAA
REPLACEMENT = 0xAAAAAAAA_BBBBBBBB
REPLACEMENT_LOW = 0xCCCCCCCC_DDDDDDDD
STORE_VALUE = 0x11223344_55667788
STORE_VALUE_LOW = 0x99AABBCC_DDEEFF00

DATA = (
    "         ORG   T+X'400'\n"
    "FILL     DC    10X'A5A5A5A5A5A5A5A5'\n"
    "         ORG   T+X'480'\n"
    "WA       DC    X'00000005'\n"
    "WB       DC    X'0000000A'\n"
    "WMAX     DC    X'7FFFFFFF'\n"
    "WONES    DC    X'FFFFFFFF'\n"
    "DA       DC    X'0123456789ABCDEF'\n"
    "DB       DC    X'FEDCBA9876543210'\n"
    "DMAX     DC    X'7FFFFFFFFFFFFFFF'\n"
    "DONES    DC    X'FFFFFFFFFFFFFFFF'\n"
    "DPAIR    DC    X'1111111122222222'\n"
    "DHALF    DC    X'0123456700000000'\n"
    "QA       DC    X'0123456789ABCDEF',X'FEDCBA9876543210'\n"
    "QB       DC    X'1111111122222222',X'3333333344444444'\n"
    "QC       DC    X'0123456789ABCDEF',X'0000000000000000'\n"
    "OUTQ     DC    2X'FFFFFFFFFFFFFFFF'\n"
    "PL       DC    X'AAAAAAAABBBBBBBB',X'CCCCCCCCDDDDDDDD'\n"
    "         DC    X'1122334455667788',X'99AABBCCDDEEFF00'\n"
    "ZB       DC    X'00'\n"
    "NB       DC    X'80'\n"
    "SB       DC    X'7F'\n"
    "ONE      DC    X'01'\n"
    "         ORG   T+X'528'\n"
    "DZERO    DC    X'0000000000000000'\n"
)


DATA_SPAN = (0x480, 0x530)


def interlocked_program(body: str) -> str:
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         LMG   2,11,FILL\n"
        f"{body}{ABEND}{DATA}"
        "         END\n"
    )


def _lines(*lines: str) -> str:
    return "".join(f"         {line}\n" for line in lines)


def _low(value: int) -> int:
    return HIGH_FILL | value


COMPARE_AND_SWAP: Mapping[str, Case] = {
    "CS equal": (
        _lines("LHI   4,5", "LHI   5,9", "CS    4,5,WA", "L     6,WA"),
        {4: _low(5), 5: _low(9), 6: _low(9)},
        0,
    ),
    "CS unequal": (
        _lines("LHI   4,7", "LHI   5,9", "CS    4,5,WA", "L     6,WA"),
        {4: _low(5), 6: _low(5)},
        1,
    ),
    "CS base is R1": (
        _lines("LA    4,WA", "LHI   5,9", "CS    4,5,0(4)", "L     6,WA"),
        {4: _low(5), 6: _low(5)},
        1,
    ),
    "CSY equal": (
        _lines("LHI   4,5", "LHI   5,9", "CSY   4,5,WA", "L     6,WA"),
        {4: _low(5), 6: _low(9)},
        0,
    ),
    "CSY unequal": (
        _lines("LHI   4,6", "LHI   5,9", "CSY   4,5,WA", "L     6,WA"),
        {4: _low(5), 6: _low(5)},
        1,
    ),
    "CSG equal": (
        _lines("LG    4,DA", "LG    5,DB", "CSG   4,5,DA", "LG    6,DA"),
        {4: SRC, 5: SRCP, 6: SRCP},
        0,
    ),
    "CSG unequal": (
        _lines("LG    4,DB", "LG    5,DPAIR", "CSG   4,5,DA", "LG    6,DA"),
        {4: SRC, 6: SRC},
        1,
    ),
    "CDS equal": (
        _lines("LM    4,5,DA", "LM    6,7,DPAIR", "CDS   4,6,DA", "LG    8,DA"),
        {4: _low(0x01234567), 5: _low(0x89ABCDEF), 8: DPAIR},
        0,
    ),
    "CDS unequal in the odd register": (
        _lines("LM    4,5,DHALF", "LM    6,7,DPAIR", "CDS   4,6,DA", "LG    8,DA"),
        {4: _low(0x01234567), 5: _low(0x89ABCDEF), 8: SRC},
        1,
    ),
    "CDSY equal": (
        _lines("LM    4,5,DA", "LM    6,7,DPAIR", "CDSY  4,6,DA", "LG    8,DA"),
        {8: DPAIR},
        0,
    ),
    "CDSY unequal": (
        _lines("LM    4,5,DPAIR", "LM    6,7,DPAIR", "CDSY  4,6,DA", "LG    8,DA"),
        {4: _low(0x01234567), 5: _low(0x89ABCDEF), 8: SRC},
        1,
    ),
    "CDSG equal": (
        _lines("LMG   4,5,QA", "LMG   6,7,QB", "CDSG  4,6,QA", "LMG   8,9,QA"),
        {4: SRC, 5: SRCP, 8: DPAIR, 9: QB_LOW},
        0,
    ),
    "CDSG unequal in the odd register": (
        _lines("LMG   4,5,QC", "LMG   6,7,QB", "CDSG  4,6,QA", "LMG   8,9,QA"),
        {4: SRC, 5: SRCP, 8: SRC, 9: SRCP},
        1,
    ),
    "CS off a word": (_lines("LHI   4,5", "CS    4,5,WA+2"), {4: _low(5)}, 0),
    "CSG off a doubleword": (_lines("CSG   4,5,WB"), {4: FILL}, 0),
    "CDSG off a quadword": (_lines("CDSG  4,6,DB"), {4: FILL}, 0),
}

COMPARE_AND_LOAD: Mapping[str, Case] = {
    "CAL equal": (_lines("LHI   4,5", "CAL   4,WA,WB"), {4: _low(10)}, 0),
    "CAL unequal": (_lines("LHI   4,7", "CAL   4,WA,WB"), {4: _low(5)}, 1),
    "CAL unequal leaves a misaligned second operand unread": (
        _lines("LHI   4,7", "CAL   4,WA,WB+1"),
        {4: _low(5)},
        1,
    ),
    "CAL equal off a word": (_lines("LHI   4,5", "CAL   4,WA,WB+1"), {4: _low(5)}, 0),
    "CAL first operand off a word": (
        _lines("LHI   4,7", "CAL   4,WA+2,WB"),
        {4: _low(7)},
        0,
    ),
    "CALGF equal": (_lines("LHI   4,5", "CALGF 4,WA,DA"), {4: SRC}, 0),
    "CALGF unequal": (_lines("LHI   4,7", "CALGF 4,WA,DA"), {4: 5}, 1),
    "CALGF equal off a doubleword": (
        _lines("LHI   4,5", "CALGF 4,WA,WB"),
        {4: _low(5)},
        0,
    ),
    "CALG equal": (_lines("LG    4,DA", "CALG  4,DA,DB"), {4: SRCP}, 0),
    "CALG unequal": (_lines("LG    4,DB", "CALG  4,DA,DB"), {4: SRC}, 1),
}


def _csst(gr0: int, call: str, setup: tuple[str, ...], reads: tuple[str, ...]) -> str:
    return _lines(f"LA    0,X'{gr0:03X}'", "LA    1,PL", *setup, call, *reads)


WORD_SWAP = ("LHI   4,5",)
OUT_READ = ("LMG   8,9,OUTQ",)
WA_OUT_READ = ("L     6,WA", *OUT_READ)


def _stored(characteristic: int) -> Case:
    width = 1 << characteristic
    image = (STORE_VALUE << 64 | STORE_VALUE_LOW) >> (8 * (16 - width))
    stored = image << (8 * (16 - width)) | ((1 << (8 * (16 - width))) - 1)
    return (
        _csst(characteristic << 8, "CSST  WA,OUTQ,4", WORD_SWAP, WA_OUT_READ),
        {4: _low(5), 6: _low(REPLACEMENT_WORD), 8: stored >> 64, 9: stored & ONES},
        0,
    )


COMPARE_AND_SWAP_AND_STORE: Mapping[str, Case] = {
    **{f"CSST word, store characteristic {sc}": _stored(sc) for sc in range(5)},
    "CSST doubleword": (
        _csst(0x301, "CSST  DA,OUTQ,4", ("LG    4,DA",), ("LG    6,DA", *OUT_READ)),
        {4: SRC, 6: REPLACEMENT, 8: STORE_VALUE, 9: ONES},
        0,
    ),
    "CSST quadword": (
        _csst(0x402, "CSST  QA,OUTQ,4", ("LMG   4,5,QA",), ("LMG   6,7,QA", *OUT_READ)),
        {6: REPLACEMENT, 7: REPLACEMENT_LOW, 8: STORE_VALUE, 9: STORE_VALUE_LOW},
        0,
    ),
    "CSST word unequal": (
        _csst(0x200, "CSST  WA,OUTQ,4", ("LHI   4,7",), WA_OUT_READ),
        {4: _low(5), 6: _low(5), 8: ONES, 9: ONES},
        1,
    ),
    "CSST doubleword unequal": (
        _csst(0x301, "CSST  DA,OUTQ,4", ("LG    4,DB",), ("LG    6,DA", *OUT_READ)),
        {4: SRC, 6: SRC, 8: ONES},
        1,
    ),
    "CSST quadword unequal": (
        _csst(0x402, "CSST  QA,OUTQ,4", ("LMG   4,5,QC",), ("LMG   6,7,QA", *OUT_READ)),
        {4: SRC, 5: SRCP, 6: SRC, 7: SRCP, 8: ONES},
        1,
    ),
    "CSST function code 3": (
        _csst(0x203, "CSST  WA,OUTQ,4", WORD_SWAP, ()),
        {4: _low(5)},
        0,
    ),
    "CSST store characteristic 5": (
        _csst(0x500, "CSST  WA,OUTQ,4", WORD_SWAP, ()),
        {4: _low(5)},
        0,
    ),
    "CSST doubleword off its boundary": (
        _csst(0x301, "CSST  WB,OUTQ,4", ("LG    4,DA",), ()),
        {4: SRC},
        0,
    ),
    "CSST store off its boundary": (
        _csst(0x200, "CSST  WA,OUTQ+2,4", ("LHI   4,7",), ()),
        {4: _low(7)},
        0,
    ),
    "CSST quadword with an odd register": (
        _csst(0x402, "CSST  QA,OUTQ,5", (), ()),
        {5: FILL},
        0,
    ),
}

LOAD_AND: Mapping[str, Case] = {
    "LAA": (
        _lines("LHI   5,3", "LAA   4,5,WA", "L     6,WA"),
        {4: _low(5), 5: _low(3), 6: _low(8)},
        2,
    ),
    "LAA zero": (_lines("LHI   5,-5", "LAA   4,5,WA", "L     6,WA"), {6: _low(0)}, 0),
    "LAA negative": (
        _lines("LHI   5,-6", "LAA   4,5,WA", "L     6,WA"),
        {6: _low(0xFFFFFFFF)},
        1,
    ),
    "LAA overflow": (
        _lines("LHI   5,1", "LAA   4,5,WMAX", "L     6,WMAX"),
        {4: _low(0x7FFFFFFF), 6: _low(0x80000000)},
        3,
    ),
    "LAA into its own third register": (
        _lines("LHI   5,3", "LAA   5,5,WA", "L     6,WA"),
        {5: _low(5), 6: _low(8)},
        2,
    ),
    "LAAG": (
        _lines("LGHI  5,-1", "LAAG  4,5,DMAX", "LG    6,DMAX"),
        {4: 0x7FFFFFFF_FFFFFFFF, 6: 0x7FFFFFFF_FFFFFFFE},
        2,
    ),
    "LAAG overflow": (
        _lines("LGHI  5,1", "LAAG  4,5,DMAX", "LG    6,DMAX"),
        {4: 0x7FFFFFFF_FFFFFFFF, 6: 0x80000000_00000000},
        3,
    ),
    "LAAG zero": (
        _lines("LGHI  5,0", "LAAG  4,5,DZERO", "LG    6,DZERO"),
        {4: 0, 6: 0},
        0,
    ),
    "LAAG negative": (
        _lines("LGHI  5,-1", "LAAG  4,5,DZERO", "LG    6,DZERO"),
        {4: 0, 6: ONES},
        1,
    ),
    "LAAL carry": (
        _lines("LHI   5,1", "LAAL  4,5,WONES", "L     6,WONES"),
        {4: _low(0xFFFFFFFF), 6: _low(0)},
        2,
    ),
    "LAAL no carry": (
        _lines("LHI   5,1", "LAAL  4,5,WMAX", "L     6,WMAX"),
        {4: _low(0x7FFFFFFF), 6: _low(0x80000000)},
        1,
    ),
    "LAALG carry": (
        _lines("LGHI  5,2", "LAALG 4,5,DONES", "LG    6,DONES"),
        {4: ONES, 6: 1},
        3,
    ),
    "LAALG no carry": (
        _lines("LGHI  5,1", "LAALG 4,5,DA", "LG    6,DA"),
        {4: SRC, 6: SRC + 1},
        1,
    ),
    "LAN": (
        _lines("LHI   5,3", "LAN   4,5,WA", "L     6,WA"),
        {4: _low(5), 6: _low(1)},
        1,
    ),
    "LAN zero": (_lines("LHI   5,2", "LAN   4,5,WA", "L     6,WA"), {6: _low(0)}, 0),
    "LANG": (
        _lines("LG    5,DPAIR", "LANG  4,5,DA", "LG    6,DA"),
        {4: SRC, 6: SRC & DPAIR},
        1,
    ),
    "LANG zero": (
        _lines("LG    5,DB", "LANG  4,5,DA", "LG    6,DA"),
        {4: SRC, 6: 0},
        0,
    ),
    "LAO": (
        _lines("LHI   5,3", "LAO   4,5,WA", "L     6,WA"),
        {4: _low(5), 6: _low(7)},
        1,
    ),
    "LAOG": (
        _lines("LG    5,DB", "LAOG  4,5,DA", "LG    6,DA"),
        {4: SRC, 6: ONES},
        1,
    ),
    "LAOG zero": (
        _lines("LGHI  5,0", "LAOG  4,5,DZERO", "LG    6,DZERO"),
        {4: 0, 6: 0},
        0,
    ),
    "LAX": (
        _lines("LHI   5,5", "LAX   4,5,WA", "L     6,WA"),
        {4: _low(5), 6: _low(0)},
        0,
    ),
    "LAXG": (
        _lines("LG    5,DB", "LAXG  4,5,DA", "LG    6,DA"),
        {4: SRC, 6: ONES},
        1,
    ),
    "LAXG zero": (
        _lines("LG    5,DA", "LAXG  4,5,DA", "LG    6,DA"),
        {4: SRC, 6: 0},
        0,
    ),
    "LAA off a word": (_lines("LAA   4,5,WA+2"), {4: FILL}, 0),
    "LAAG off a doubleword": (_lines("LAAG  4,5,WB"), {4: FILL}, 0),
    "LAX off a word": (_lines("LAX   4,5,WA+1"), {4: FILL}, 0),
}

SET_CC_2 = "CLI   ONE,0"

LOAD_STORE_PAIR: Mapping[str, Case] = {
    "LPD": (_lines("LPD   4,WA,WB"), {4: _low(5), 5: _low(10)}, 0),
    "LPD base is the pair": (
        _lines("LA    4,WA", "LA    5,WB", "LPD   4,0(5),0(4)"),
        {4: _low(10), 5: _low(5)},
        0,
    ),
    "LPDG": (_lines("LPDG  4,DA,DB"), {4: SRC, 5: SRCP}, 0),
    "LPD off a word": (_lines("LPD   4,WA,WB+2"), {4: FILL, 5: FILL}, 0),
    "LPDG off a doubleword": (_lines("LPDG  4,WB,DA"), {4: FILL, 5: FILL}, 0),
    "LPQ": (_lines(SET_CC_2, "LPQ   4,QA"), {4: SRC, 5: SRCP}, 2),
    "LPQ off a quadword": (_lines("LPQ   4,DB"), {4: FILL, 5: FILL}, 0),
    "STPQ": (
        _lines("LMG   4,5,QB", SET_CC_2, "STPQ  4,OUTQ", "LMG   8,9,OUTQ"),
        {8: DPAIR, 9: QB_LOW},
        2,
    ),
    "STPQ off a quadword": (_lines("STPQ  4,DB"), {4: FILL, 5: FILL}, 0),
    "TS zero": (_lines("TS    ZB", "LLC   6,ZB"), {6: _low(0xFF)}, 0),
    "TS leftmost one": (_lines("TS    NB", "LLC   6,NB"), {6: _low(0xFF)}, 1),
    "TS leftmost zero": (_lines("TS    SB", "LLC   6,SB"), {6: _low(0xFF)}, 0),
}

CASES: Mapping[str, Case] = {
    **COMPARE_AND_SWAP,
    **COMPARE_AND_LOAD,
    **COMPARE_AND_SWAP_AND_STORE,
    **LOAD_AND,
    **LOAD_STORE_PAIR,
}

ABENDS: frozenset[str] = frozenset(
    {
        "CS off a word",
        "CSG off a doubleword",
        "CDSG off a quadword",
        "CAL equal off a word",
        "CAL first operand off a word",
        "CALGF equal off a doubleword",
        "CSST function code 3",
        "CSST store characteristic 5",
        "CSST doubleword off its boundary",
        "CSST store off its boundary",
        "CSST quadword with an odd register",
        "LAA off a word",
        "LAAG off a doubleword",
        "LAX off a word",
        "LPD off a word",
        "LPDG off a doubleword",
        "LPQ off a quadword",
        "STPQ off a quadword",
    }
)
