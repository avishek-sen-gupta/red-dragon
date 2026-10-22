# pyright: standard
"""Conditional load and store, select and bit-count programs, one or more per mnemonic and extended suffix, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL

type Case = tuple[str, Mapping[int, int], int]

LOW_FILL = 0x00000000_A5A5A5A5
HIGH_SRC = 0x01234567_00000000
HIGH_SRCP = 0xFEDCBA98_00000000
OUT_UNTOUCHED = 0xFFFFFFFF_FFFFFFFF
SRC = 0x01234567_89ABCDEF
SRCP = 0xFEDCBA98_76543210
DNEG = 0x80000000_00000081
POS_LOW = HIGH_FILL | 0x7FFF7FFE
NEG_LOW = HIGH_FILL | 0x80000001

SET_CC: Mapping[int, str] = {
    0: "         CLI   ZERO,0\n",
    1: "         CLI   ZERO,1\n",
    2: "         CLI   NEG,0\n",
    3: "         TM    NEG,X'80'\n",
}


def _line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<8} {operands}\n"


def _at(cc: int, *lines: str) -> str:
    return "".join(lines[:-1]) + SET_CC[cc] + lines[-1]


def _case(cc: int, lines: tuple[str, ...], results: Mapping[int, int]) -> Case:
    return (_at(cc, *lines), results, cc)


POS_INTO_5 = _line("L", "5,POS")
DNEG_INTO_5 = _line("LG", "5,DNEG")
SRC_INTO_5 = _line("LG", "5,SRC")
POS_NEG = (_line("L", "5,POS"), _line("L", "6,NEG"))
SRC_SRCP = (_line("LG", "5,SRC"), _line("LG", "6,SRCP"))
OUT_INTO_6 = _line("LG", "6,OUT")


def _loaded(cc: int, setup: str, load: str, r4: int) -> Case:
    return _case(cc, (setup, load), {4: r4})


def _stored(cc: int, setup: str, store: str, out: int) -> Case:
    return (_at(cc, setup, store) + OUT_INTO_6, {6: out}, cc)


def _selected(cc: int, select: str, results: Mapping[int, int]) -> Case:
    return _case(cc, (*POS_NEG, select), results)


def _selected_64(cc: int, select: str, results: Mapping[int, int]) -> Case:
    return _case(cc, (*SRC_SRCP, select), results)


LOAD_ON_CONDITION: Mapping[str, Case] = {
    "LOCR": _loaded(2, POS_INTO_5, _line("LOCR", "4,5,2"), POS_LOW),
    "LOCR not selected": _loaded(2, POS_INTO_5, _line("LOCR", "4,5,13"), FILL),
    "LOCR mask 0": _loaded(0, POS_INTO_5, _line("LOCR", "4,5,0"), FILL),
    "LOCR mask 15": _loaded(3, POS_INTO_5, _line("LOCR", "4,5,15"), POS_LOW),
    "LOCRE": _loaded(0, POS_INTO_5, _line("LOCRE", "4,5"), POS_LOW),
    "LOCRNE": _loaded(0, POS_INTO_5, _line("LOCRNE", "4,5"), FILL),
    "LOCRO": _loaded(3, POS_INTO_5, _line("LOCRO", "4,5"), POS_LOW),
    "LOCRNE at CC 3": _loaded(3, POS_INTO_5, _line("LOCRNE", "4,5"), POS_LOW),
    "LOCRNO": _loaded(3, POS_INTO_5, _line("LOCRNO", "4,5"), FILL),
    "LOCGR": _loaded(1, DNEG_INTO_5, _line("LOCGR", "4,5,4"), DNEG),
    "LOCGRH": _loaded(2, DNEG_INTO_5, _line("LOCGRH", "4,5"), DNEG),
    "LOCGRL": _loaded(2, DNEG_INTO_5, _line("LOCGRL", "4,5"), FILL),
    "LOCGRNH": _loaded(1, DNEG_INTO_5, _line("LOCGRNH", "4,5"), DNEG),
    "LOCFHR": _loaded(0, SRC_INTO_5, _line("LOCFHR", "4,5,8"), HIGH_SRC | LOW_FILL),
    "LOCFHRP": _loaded(2, SRC_INTO_5, _line("LOCFHRP", "4,5"), HIGH_SRC | LOW_FILL),
    "LOCFHRM": _loaded(2, SRC_INTO_5, _line("LOCFHRM", "4,5"), FILL),
    "LOCFHRNZ": _loaded(0, SRC_INTO_5, _line("LOCFHRNZ", "4,5"), FILL),
    "LOC": _loaded(0, "", _line("LOC", "4,POS,8"), POS_LOW),
    "LOC not selected": _loaded(1, "", _line("LOC", "4,POS,8"), FILL),
    "LOCZ": _loaded(0, "", _line("LOCZ", "4,POS"), POS_LOW),
    "LOCNZ": _loaded(1, "", _line("LOCNZ", "4,POS"), POS_LOW),
    "LOCM": _loaded(1, "", _line("LOCM", "4,NEG"), NEG_LOW),
    "LOC from a base register": _loaded(
        2, _line("LA", "7,POS"), _line("LOC", "4,0(7),2"), POS_LOW
    ),
    "LOCG": _loaded(3, "", _line("LOCG", "4,DNEG,1"), DNEG),
    "LOCGNL": _loaded(2, "", _line("LOCGNL", "4,DNEG"), DNEG),
    "LOCGL": _loaded(2, "", _line("LOCGL", "4,DNEG"), FILL),
    "LOCFH": _loaded(2, "", _line("LOCFH", "4,NEG,2"), 0x80000001_00000000 | LOW_FILL),
    "LOCFHNP": _loaded(2, "", _line("LOCFHNP", "4,NEG"), FILL),
    "LOCFHNM": _loaded(
        0, "", _line("LOCFHNM", "4,NEG"), 0x80000001_00000000 | LOW_FILL
    ),
    "LOCHI": _loaded(0, "", _line("LOCHI", "4,-2,8"), HIGH_FILL | 0xFFFFFFFE),
    "LOCHIH": _loaded(2, "", _line("LOCHIH", "4,32767"), HIGH_FILL | 0x7FFF),
    "LOCHINL": _loaded(1, "", _line("LOCHINL", "4,5"), FILL),
    "LOCGHI": _loaded(1, "", _line("LOCGHI", "4,-32768,4"), 0xFFFFFFFF_FFFF8000),
    "LOCGHIZ": _loaded(1, "", _line("LOCGHIZ", "4,7"), FILL),
    "LOCGHINH": _loaded(3, "", _line("LOCGHINH", "4,7"), 7),
    "LOCHHI": _loaded(3, "", _line("LOCHHI", "4,-1,1"), 0xFFFFFFFF_00000000 | LOW_FILL),
    "LOCHHINE": _loaded(
        2, "", _line("LOCHHINE", "4,5"), 0x00000005_00000000 | LOW_FILL
    ),
    "LOCHHINO": _loaded(3, "", _line("LOCHHINO", "4,5"), FILL),
}

STORE_ON_CONDITION: Mapping[str, Case] = {
    "STOC": _stored(0, POS_INTO_5, _line("STOC", "5,OUT,8"), 0x7FFF7FFE_FFFFFFFF),
    "STOC not selected": _stored(
        1, POS_INTO_5, _line("STOC", "5,OUT,8"), OUT_UNTOUCHED
    ),
    "STOCH": _stored(2, POS_INTO_5, _line("STOCH", "5,OUT"), 0x7FFF7FFE_FFFFFFFF),
    "STOCL": _stored(2, POS_INTO_5, _line("STOCL", "5,OUT"), OUT_UNTOUCHED),
    "STOCNM": _stored(2, POS_INTO_5, _line("STOCNM", "5,OUT"), 0x7FFF7FFE_FFFFFFFF),
    "STOCG": _stored(1, DNEG_INTO_5, _line("STOCG", "5,OUT,4"), DNEG),
    "STOCGNP": _stored(1, DNEG_INTO_5, _line("STOCGNP", "5,OUT"), DNEG),
    "STOCGNH at CC 3": _stored(3, DNEG_INTO_5, _line("STOCGNH", "5,OUT"), DNEG),
    "STOCGP": _stored(1, DNEG_INTO_5, _line("STOCGP", "5,OUT"), OUT_UNTOUCHED),
    "STOCFH": _stored(0, SRC_INTO_5, _line("STOCFH", "5,OUT,8"), 0x01234567_FFFFFFFF),
    "STOCFHO": _stored(3, SRC_INTO_5, _line("STOCFHO", "5,OUT"), 0x01234567_FFFFFFFF),
    "STOCFHE": _stored(3, SRC_INTO_5, _line("STOCFHE", "5,OUT"), OUT_UNTOUCHED),
}

SELECT: Mapping[str, Case] = {
    "SELR": _selected(0, _line("SELR", "4,5,6,8"), {4: POS_LOW}),
    "SELR third operand": _selected(1, _line("SELR", "4,5,6,8"), {4: NEG_LOW}),
    "SELRNH": _selected(2, _line("SELRNH", "4,5,6"), {4: NEG_LOW}),
    "SELR into the third register": _selected(
        1, _line("SELR", "6,5,6,4"), {5: POS_LOW, 6: POS_LOW}
    ),
    "SELR selected into the second register": _selected(
        0, _line("SELR", "5,5,6,8"), {5: POS_LOW, 6: NEG_LOW}
    ),
    "SELR not selected into the second register": _selected(
        1, _line("SELR", "5,5,6,8"), {5: NEG_LOW, 6: NEG_LOW}
    ),
    "SELGR": _selected_64(2, _line("SELGR", "4,5,6,2"), {4: SRC}),
    "SELGRE": _selected_64(2, _line("SELGRE", "4,5,6"), {4: SRCP}),
    "SELGRO": _selected_64(3, _line("SELGRO", "4,5,6"), {4: SRC}),
    "SELGRNO": _selected_64(3, _line("SELGRNO", "4,5,6"), {4: SRCP}),
    "SELFHR": _selected_64(0, _line("SELFHR", "4,5,6,8"), {4: HIGH_SRC | LOW_FILL}),
    "SELFHRL": _selected_64(0, _line("SELFHRL", "4,5,6"), {4: HIGH_SRCP | LOW_FILL}),
    "SELFHRNE": _selected_64(1, _line("SELFHRNE", "4,5,6"), {4: HIGH_SRC | LOW_FILL}),
}

CC_KEPT = 1
CC_ZERO = 0
CC_ONE_FOUND = 2
CC_NONZERO = 1


def _counted(source: str, count: str, results: Mapping[int, int], cc: int) -> Case:
    return (source + count, results, cc)


def _kept_cc(source: str, count: str, results: Mapping[int, int]) -> Case:
    return (source + SET_CC[CC_KEPT] + count, results, CC_KEPT)


ZERO_INTO_5 = _line("LGHI", "5,0")
ONES_INTO_5 = _line("LGHI", "5,-1")
ONE_INTO_5 = _line("LGHI", "5,1")
BIT_0_INTO_5 = _line("LLIHH", "5,X'8000'")

FIND_LEFTMOST_ONE: Mapping[str, Case] = {
    "FLOGR": _counted(
        SRC_INTO_5, _line("FLOGR", "6,5"), {6: 7, 7: 0x00234567_89ABCDEF}, CC_ONE_FOUND
    ),
    "FLOGR zero": _counted(ZERO_INTO_5, _line("FLOGR", "6,5"), {6: 64, 7: 0}, CC_ZERO),
    "FLOGR bit 0": _counted(
        DNEG_INTO_5, _line("FLOGR", "6,5"), {6: 0, 7: 0x81}, CC_ONE_FOUND
    ),
    "FLOGR bit 63": _counted(
        ONE_INTO_5, _line("FLOGR", "6,5"), {6: 63, 7: 0}, CC_ONE_FOUND
    ),
    "FLOGR from R1+1": _counted(
        _line("LG", "7,SRCP"),
        _line("FLOGR", "6,7"),
        {6: 0, 7: 0x7EDCBA98_76543210},
        CC_ONE_FOUND,
    ),
    "FLOGR from R1": _counted(
        _line("LG", "6,SRC"),
        _line("FLOGR", "6,6"),
        {6: 7, 7: 0x00234567_89ABCDEF},
        CC_ONE_FOUND,
    ),
}

POPULATION_COUNT: Mapping[str, Case] = {
    "POPCNT": _counted(
        SRC_INTO_5, _line("POPCNT", "4,5"), {4: 0x01030305_03050507}, CC_NONZERO
    ),
    "POPCNT total": _counted(SRC_INTO_5, _line("POPCNT", "4,5,8"), {4: 32}, CC_NONZERO),
    "POPCNT all ones": _counted(
        ONES_INTO_5, _line("POPCNT", "4,5"), {4: 0x08080808_08080808}, CC_NONZERO
    ),
    "POPCNT total all ones": _counted(
        ONES_INTO_5, _line("POPCNT", "4,5,8"), {4: 64}, CC_NONZERO
    ),
    "POPCNT zero": _counted(ZERO_INTO_5, _line("POPCNT", "4,5"), {4: 0}, CC_ZERO),
    "POPCNT total zero": _counted(
        ZERO_INTO_5, _line("POPCNT", "4,5,8"), {4: 0}, CC_ZERO
    ),
}

ZERO_COUNTS: Mapping[str, Case] = {
    "CLZG": _kept_cc(SRC_INTO_5, _line("CLZG", "4,5"), {4: 7}),
    "CLZG zero": _kept_cc(ZERO_INTO_5, _line("CLZG", "4,5"), {4: 64}),
    "CLZG bit 0": _kept_cc(BIT_0_INTO_5, _line("CLZG", "4,5"), {4: 0}),
    "CLZG bit 63": _kept_cc(ONE_INTO_5, _line("CLZG", "4,5"), {4: 63}),
    "CTZG": _kept_cc(_line("LG", "5,SRCP"), _line("CTZG", "4,5"), {4: 4}),
    "CTZG zero": _kept_cc(ZERO_INTO_5, _line("CTZG", "4,5"), {4: 64}),
    "CTZG bit 0": _kept_cc(BIT_0_INTO_5, _line("CTZG", "4,5"), {4: 63}),
    "CTZG bit 63": _kept_cc(DNEG_INTO_5, _line("CTZG", "4,5"), {4: 0}),
    "CTZG in place": _kept_cc(_line("LG", "4,SRCP"), _line("CTZG", "4,4"), {4: 4}),
}

MASK_INTO_6: Mapping[str, str] = {
    "zero": _line("LGHI", "6,0"),
    "ones": _line("LGHI", "6,-1"),
    "SRCP": _line("LG", "6,SRCP"),
    "DPOS": _line("LG", "6,DPOS"),
    "DNEG": _line("LG", "6,DNEG"),
}

BITS_UNDER_MASK: Mapping[str, Case] = {
    "BEXTG": _kept_cc(
        SRC_INTO_5 + MASK_INTO_6["DPOS"],
        _line("BEXTG", "4,5,6"),
        {4: 0x02468ACF_13579BB8},
    ),
    "BEXTG mask zero": _kept_cc(
        SRC_INTO_5 + MASK_INTO_6["zero"], _line("BEXTG", "4,5,6"), {4: 0}
    ),
    "BEXTG mask ones": _kept_cc(
        SRC_INTO_5 + MASK_INTO_6["ones"], _line("BEXTG", "4,5,6"), {4: SRC}
    ),
    "BEXTG left-justified": _kept_cc(
        _line("LG", "5,SRCP") + MASK_INTO_6["SRCP"],
        _line("BEXTG", "5,5,6"),
        {5: 0xFFFFFFFF_00000000},
    ),
    "BDEPG": _kept_cc(
        SRC_INTO_5 + MASK_INTO_6["SRCP"],
        _line("BDEPG", "4,5,6"),
        {4: 0x00881880_24501210},
    ),
    "BDEPG mask zero": _kept_cc(
        SRC_INTO_5 + MASK_INTO_6["zero"], _line("BDEPG", "4,5,6"), {4: 0}
    ),
    "BDEPG mask ones": _kept_cc(
        SRC_INTO_5 + MASK_INTO_6["ones"], _line("BDEPG", "4,5,6"), {4: SRC}
    ),
    "BDEPG three mask bits": _kept_cc(
        _line("LG", "5,SRCP") + MASK_INTO_6["DNEG"],
        _line("BDEPG", "6,5,6"),
        {6: DNEG},
    ),
}

CASES: Mapping[str, Case] = {
    **LOAD_ON_CONDITION,
    **STORE_ON_CONDITION,
    **SELECT,
    **FIND_LEFTMOST_ONE,
    **POPULATION_COUNT,
    **ZERO_COUNTS,
    **BITS_UNDER_MASK,
}
