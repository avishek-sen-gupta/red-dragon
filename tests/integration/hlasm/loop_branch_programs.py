# pyright: standard
"""Branch on count and branch on index programs: R2 records the path, R3 accumulates a loop; shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import DATA, HIGH_FILL

type LoopCase = tuple[str, Mapping[int, int]]

TAKEN = HIGH_FILL | 1
FELL_THROUGH = HIGH_FILL | 2
PATH_REGISTER = 2
SUM_REGISTER = 3
PRESET_CC = 2
LOOP_SUM = 15
LOW_ONES = 0xFFFFFFFF
ALL_ONES = 0xFFFFFFFF_FFFFFFFF

LIMITS = (
    "         DS    0D\n"
    "DMAXPOS  DC    X'7FFFFFFFFFFFFFFF'\n"
    "MAXPOS   DC    X'7FFFFFFF'\n"
)


def program(code: str) -> str:
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         LMG   2,11,FILL\n"
        "         CLI   NEG,0\n"
        f"{code}"
        "NEXT     LHI   2,2\n"
        "         ABEND 1\n"
        "TGT      LHI   2,1\n"
        "         ABEND 1\n"
        f"{LIMITS}{DATA}"
        "         END\n"
    )


def _line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<5} {operands}\n"


def _loop(setup: str, branch: str) -> str:
    return f"{setup}{_line('LHI', '3,0')}LOOP     LA    3,0(3,4)\n{branch}"


def _loaded(mnemonic: str, values: Mapping[int, int]) -> str:
    return "".join(_line(mnemonic, f"{r},{v}") for r, v in values.items())


COUNT_FROM_5 = _line("LHI", "4,5")
DOUBLE_COUNT_FROM_5 = _line("LGHI", "4,5")
LOOP_ADDRESS_IN_R6 = _line("LA", "6,LOOP")
UP_BY_ONE_TO_5 = _loaded("LHI", {4: 0, 6: 1, 7: 5})
DOUBLE_UP_BY_ONE_TO_5 = _loaded("LGHI", {4: 0, 6: 1, 7: 5})
DOWN_BY_ONE_TO_0 = _loaded("LHI", {4: 5, 6: -1, 7: 0})
DOUBLE_DOWN_BY_ONE_TO_0 = _loaded("LGHI", {4: 5, 6: -1, 7: 0})


def _summed(r4: int) -> Mapping[int, int]:
    return {PATH_REGISTER: FELL_THROUGH, SUM_REGISTER: HIGH_FILL | LOOP_SUM, 4: r4}


COUNT_CASES: Mapping[str, LoopCase] = {
    "BCT": (_loop(COUNT_FROM_5, _line("BCT", "4,LOOP")), _summed(HIGH_FILL)),
    "BCTR": (
        _loop(LOOP_ADDRESS_IN_R6 + COUNT_FROM_5, _line("BCTR", "4,6")),
        _summed(HIGH_FILL),
    ),
    "BCTG": (_loop(DOUBLE_COUNT_FROM_5, _line("BCTG", "4,LOOP")), _summed(0)),
    "BCTGR": (
        _loop(LOOP_ADDRESS_IN_R6 + DOUBLE_COUNT_FROM_5, _line("BCTGR", "4,6")),
        _summed(0),
    ),
    "BRCT": (_loop(COUNT_FROM_5, _line("BRCT", "4,LOOP")), _summed(HIGH_FILL)),
    "JCT": (_loop(COUNT_FROM_5, _line("JCT", "4,LOOP")), _summed(HIGH_FILL)),
    "BRCTG": (_loop(DOUBLE_COUNT_FROM_5, _line("BRCTG", "4,LOOP")), _summed(0)),
    "JCTG": (_loop(DOUBLE_COUNT_FROM_5, _line("JCTG", "4,LOOP")), _summed(0)),
    "BCTR 4,0": (
        _line("LHI", "4,0") + _line("BCTR", "4,0"),
        {PATH_REGISTER: FELL_THROUGH, 4: HIGH_FILL | LOW_ONES},
    ),
    "BCTGR 4,0": (
        _line("LGHI", "4,0") + _line("BCTGR", "4,0"),
        {PATH_REGISTER: FELL_THROUGH, 4: ALL_ONES},
    ),
    "BCT from 0": (
        _line("LHI", "4,0") + _line("BCT", "4,TGT"),
        {PATH_REGISTER: TAKEN, 4: HIGH_FILL | LOW_ONES},
    ),
    "BRCTG from 1": (
        _line("LGHI", "4,1") + _line("BRCTG", "4,TGT"),
        {PATH_REGISTER: FELL_THROUGH, 4: 0},
    ),
    "BCTR 5,5": (_line("LA", "5,TGT") + _line("BCTR", "5,5"), {PATH_REGISTER: TAKEN}),
}

INDEX_CASES: Mapping[str, LoopCase] = {
    "BXLE": (_loop(UP_BY_ONE_TO_5, _line("BXLE", "4,6,LOOP")), _summed(HIGH_FILL | 6)),
    "BRXLE": (
        _loop(UP_BY_ONE_TO_5, _line("BRXLE", "4,6,LOOP")),
        _summed(HIGH_FILL | 6),
    ),
    "JXLE": (_loop(UP_BY_ONE_TO_5, _line("JXLE", "4,6,LOOP")), _summed(HIGH_FILL | 6)),
    "BXLEG": (_loop(DOUBLE_UP_BY_ONE_TO_5, _line("BXLEG", "4,6,LOOP")), _summed(6)),
    "BRXLG": (_loop(DOUBLE_UP_BY_ONE_TO_5, _line("BRXLG", "4,6,LOOP")), _summed(6)),
    "JXLEG": (_loop(DOUBLE_UP_BY_ONE_TO_5, _line("JXLEG", "4,6,LOOP")), _summed(6)),
    "BXH": (_loop(DOWN_BY_ONE_TO_0, _line("BXH", "4,6,LOOP")), _summed(HIGH_FILL)),
    "BRXH": (_loop(DOWN_BY_ONE_TO_0, _line("BRXH", "4,6,LOOP")), _summed(HIGH_FILL)),
    "JXH": (_loop(DOWN_BY_ONE_TO_0, _line("JXH", "4,6,LOOP")), _summed(HIGH_FILL)),
    "BXHG": (_loop(DOUBLE_DOWN_BY_ONE_TO_0, _line("BXHG", "4,6,LOOP")), _summed(0)),
    "BRXHG": (_loop(DOUBLE_DOWN_BY_ONE_TO_0, _line("BRXHG", "4,6,LOOP")), _summed(0)),
    "JXHG": (_loop(DOUBLE_DOWN_BY_ONE_TO_0, _line("JXHG", "4,6,LOOP")), _summed(0)),
}

OVERLAP_CASES: Mapping[str, LoopCase] = {
    "BXH 7,6 compares the original R7": (
        _loaded("LHI", {6: 1, 7: 5}) + _line("BXH", "7,6,TGT"),
        {PATH_REGISTER: TAKEN, 7: HIGH_FILL | 6},
    ),
    "BXHG 7,6 compares the original R7": (
        _loaded("LGHI", {6: 1, 7: 5}) + _line("BXHG", "7,6,TGT"),
        {PATH_REGISTER: TAKEN, 7: 6},
    ),
    "BXLE 5,5": (
        _line("LHI", "5,3") + _line("BXLE", "5,5,TGT"),
        {PATH_REGISTER: FELL_THROUGH, 5: HIGH_FILL | 6},
    ),
    "BRXH 5,5": (
        _line("LHI", "5,3") + _line("BRXH", "5,5,TGT"),
        {PATH_REGISTER: TAKEN, 5: HIGH_FILL | 6},
    ),
    "BXLE 6,6": (
        _loaded("LHI", {6: 3, 7: 5}) + _line("BXLE", "6,6,TGT"),
        {PATH_REGISTER: FELL_THROUGH, 6: HIGH_FILL | 6, 7: HIGH_FILL | 5},
    ),
    "BXH 4,6,0(4) branches to the original R4": (
        _line("LA", "4,TGT") + _loaded("LHI", {6: 1, 7: 0}) + _line("BXH", "4,6,0(4)"),
        {PATH_REGISTER: TAKEN},
    ),
    "BXH compares signed": (
        _loaded("LHI", {4: 0, 6: 1, 7: -1}) + _line("BXH", "4,6,TGT"),
        {PATH_REGISTER: TAKEN, 4: HIGH_FILL | 1},
    ),
    "BXLEG compares signed": (
        _loaded("LGHI", {4: 0, 6: 1, 7: -1}) + _line("BXLEG", "4,6,TGT"),
        {PATH_REGISTER: FELL_THROUGH, 4: 1},
    ),
    "BXH wraps to the most negative": (
        _line("L", "4,MAXPOS") + _loaded("LHI", {6: 1, 7: 0}) + _line("BXH", "4,6,TGT"),
        {PATH_REGISTER: FELL_THROUGH, 4: HIGH_FILL | 0x80000000},
    ),
    "BRXLE wraps to the most negative": (
        _line("L", "4,MAXPOS")
        + _loaded("LHI", {6: 1, 7: 0})
        + _line("BRXLE", "4,6,TGT"),
        {PATH_REGISTER: TAKEN, 4: HIGH_FILL | 0x80000000},
    ),
    "BRXHG wraps to the most negative": (
        _line("LG", "4,DMAXPOS")
        + _loaded("LGHI", {6: 1, 7: 0})
        + _line("BRXHG", "4,6,TGT"),
        {PATH_REGISTER: FELL_THROUGH, 4: 0x80000000_00000000},
    ),
}

CASES: Mapping[str, LoopCase] = {**COUNT_CASES, **INDEX_CASES, **OVERLAP_CASES}
