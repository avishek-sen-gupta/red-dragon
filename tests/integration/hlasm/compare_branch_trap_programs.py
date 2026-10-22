# pyright: standard
"""Compare-and-branch, compare-and-trap and load-and-trap programs: R2 records the path, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.branch_on_condition_programs import (
    FELL_THROUGH,
    PATH_REGISTER,
    TAKEN,
)
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL

type Case = tuple[int, str, Mapping[int, int], str]

COMPLETED = "U0001"
DATA_EXCEPTION = "S0C7"

NEG_POS = "         L     3,NEG\n" "         L     4,POS\n"
DNEG_DPOS = "         LG    3,DNEG\n" "         LG    4,DPOS\n"
SEVENS = "         LHI   3,7\n" "         LHI   4,7\n"
DOUBLE_SEVENS = "         LGHI  3,7\n" "         LGHI  4,7\n"
LOW_SEVEN_HIGH_FILL = "         LHI   3,7\n" "         LGHI  4,7\n"


def _line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<7} {operands}\n"


def _set(r: int, value: int) -> str:
    return _line("LGHI" if value < 0 else "LHI", f"{r},{value}")


def taken(cc: int, body: str) -> Case:
    return (cc, body, {PATH_REGISTER: TAKEN}, COMPLETED)


def fell(cc: int, body: str, loaded: Mapping[int, int] = {}) -> Case:
    return (cc, body, {PATH_REGISTER: FELL_THROUGH, **loaded}, COMPLETED)


def trapped(cc: int, body: str, loaded: Mapping[int, int] = {}) -> Case:
    return (cc, body, {PATH_REGISTER: FILL, **loaded}, DATA_EXCEPTION)


COMPARE_AND_BRANCH_RELATIVE: Mapping[str, Case] = {
    "CRJ": taken(1, NEG_POS + _line("CRJ", "3,4,4,TAKEN")),
    "CRJ not selected": fell(1, NEG_POS + _line("CRJ", "3,4,10,TAKEN")),
    "CRJ mask 0": fell(2, SEVENS + _line("CRJ", "3,4,0,TAKEN")),
    "CRJ mask 1": fell(0, NEG_POS + _line("CRJ", "3,4,1,TAKEN")),
    "CRJ mask 15": taken(3, NEG_POS + _line("CRJ", "3,4,15,TAKEN")),
    "CRJ mask 14": taken(0, NEG_POS + _line("CRJ", "3,4,14,TAKEN")),
    "CRJE": taken(2, SEVENS + _line("CRJE", "3,4,TAKEN")),
    "CRJE high word ignored": taken(
        3, LOW_SEVEN_HIGH_FILL + _line("CRJE", "3,4,TAKEN")
    ),
    "CRJH": fell(0, NEG_POS + _line("CRJH", "3,4,TAKEN")),
    "CRJL": taken(0, NEG_POS + _line("CRJL", "3,4,TAKEN")),
    "CRJNE": fell(1, SEVENS + _line("CRJNE", "3,4,TAKEN")),
    "CRJNH": taken(2, NEG_POS + _line("CRJNH", "3,4,TAKEN")),
    "CRJNL": fell(3, NEG_POS + _line("CRJNL", "3,4,TAKEN")),
    "CGRJ": taken(0, DNEG_DPOS + _line("CGRJ", "3,4,4,TAKEN")),
    "CGRJH": fell(1, DNEG_DPOS + _line("CGRJH", "3,4,TAKEN")),
    "CGRJE high word counts": fell(
        2, LOW_SEVEN_HIGH_FILL + _line("CGRJE", "3,4,TAKEN")
    ),
    "CGRJL high word counts": taken(
        2, LOW_SEVEN_HIGH_FILL + _line("CGRJL", "3,4,TAKEN")
    ),
    "CLRJ": taken(0, NEG_POS + _line("CLRJ", "3,4,2,TAKEN")),
    "CLRJL": fell(0, NEG_POS + _line("CLRJL", "3,4,TAKEN")),
    "CLRJNE": fell(1, SEVENS + _line("CLRJNE", "3,4,TAKEN")),
    "CLGRJ": taken(3, DNEG_DPOS + _line("CLGRJ", "3,4,2,TAKEN")),
    "CLGRJE": taken(1, DOUBLE_SEVENS + _line("CLGRJE", "3,4,TAKEN")),
    "CLGRJNH": fell(1, DNEG_DPOS + _line("CLGRJNH", "3,4,TAKEN")),
    "CIJ": taken(1, _set(3, -5) + _line("CIJ", "3,-5,8,TAKEN")),
    "CIJH": taken(0, _set(3, -1) + _line("CIJH", "3,-2,TAKEN")),
    "CIJH at 127": taken(0, _set(3, 128) + _line("CIJH", "3,127,TAKEN")),
    "CIJL at -128": fell(0, _set(3, -128) + _line("CIJL", "3,-128,TAKEN")),
    "CGIJ": taken(2, _set(3, -1) + _line("CGIJ", "3,1,4,TAKEN")),
    "CGIJE high word counts": fell(2, SEVENS + _line("CGIJE", "3,7,TAKEN")),
    "CLIJ": taken(1, _set(3, 200) + _line("CLIJ", "3,200,8,TAKEN")),
    "CLIJH": taken(2, _line("LHI", "3,-1") + _line("CLIJH", "3,255,TAKEN")),
    "CLIJNL at 255": fell(0, _set(3, 254) + _line("CLIJNL", "3,255,TAKEN")),
    "CLGIJ": taken(3, _line("LGHI", "3,255") + _line("CLGIJ", "3,255,8,TAKEN")),
    "CLGIJH high word counts": taken(0, SEVENS + _line("CLGIJH", "3,7,TAKEN")),
}

COMPARE_AND_BRANCH: Mapping[str, Case] = {
    "CRB": taken(1, NEG_POS + _line("CRB", "3,4,4,TAKEN")),
    "CRBH": fell(1, NEG_POS + _line("CRBH", "3,4,TAKEN")),
    "CRB mask 0": fell(0, SEVENS + _line("CRB", "3,4,0,TAKEN")),
    "CRB mask 14": taken(3, NEG_POS + _line("CRB", "3,4,14,TAKEN")),
    "CRBE based": taken(2, SEVENS + _line("LA", "5,TAKEN") + _line("CRBE", "3,4,0(5)")),
    "CGRB": taken(0, DNEG_DPOS + _line("CGRB", "3,4,4,TAKEN")),
    "CGRBNL": fell(0, DNEG_DPOS + _line("CGRBNL", "3,4,TAKEN")),
    "CLRB": taken(2, NEG_POS + _line("CLRB", "3,4,2,TAKEN")),
    "CLRBNH": fell(2, NEG_POS + _line("CLRBNH", "3,4,TAKEN")),
    "CLGRB": taken(1, DNEG_DPOS + _line("CLGRB", "3,4,10,TAKEN")),
    "CLGRBL": fell(1, DNEG_DPOS + _line("CLGRBL", "3,4,TAKEN")),
    "CIB": taken(0, _set(3, -3) + _line("CIB", "3,-3,8,TAKEN")),
    "CIBNE": fell(0, _set(3, -3) + _line("CIBNE", "3,-3,TAKEN")),
    "CGIB": taken(3, _set(3, -100) + _line("CGIB", "3,-99,4,TAKEN")),
    "CGIBH": fell(3, _set(3, -100) + _line("CGIBH", "3,-99,TAKEN")),
    "CLIB": taken(1, _set(3, 255) + _line("CLIB", "3,255,8,TAKEN")),
    "CLIBL": taken(1, _set(3, 1) + _line("CLIBL", "3,255,TAKEN")),
    "CLGIB": taken(2, _line("LGHI", "3,-1") + _line("CLGIB", "3,255,2,TAKEN")),
    "CLGIBNH": fell(2, _line("LGHI", "3,-1") + _line("CLGIBNH", "3,255,TAKEN")),
}

COMPARE_AND_TRAP: Mapping[str, Case] = {
    "CRT": trapped(1, NEG_POS + _line("CRT", "3,4,4")),
    "CRTH": fell(1, NEG_POS + _line("CRTH", "3,4")),
    "CRT mask 0": fell(2, SEVENS + _line("CRT", "3,4,0")),
    "CRT mask 14": trapped(0, NEG_POS + _line("CRT", "3,4,14")),
    "CRTE": trapped(3, SEVENS + _line("CRTE", "3,4")),
    "CGRT": trapped(0, DNEG_DPOS + _line("CGRT", "3,4,4")),
    "CGRTNL": fell(0, DNEG_DPOS + _line("CGRTNL", "3,4")),
    "CLRT": fell(2, NEG_POS + _line("CLRT", "3,4,4")),
    "CLRTH": trapped(2, NEG_POS + _line("CLRTH", "3,4")),
    "CLGRT": trapped(1, DOUBLE_SEVENS + _line("CLGRT", "3,4,8")),
    "CLGRTNH": fell(1, DNEG_DPOS + _line("CLGRTNH", "3,4")),
    "CIT": trapped(0, _line("L", "3,NEG") + _line("CIT", "3,-32768,4")),
    "CITE": trapped(2, _set(3, -7) + _line("CITE", "3,-7")),
    "CITNE": fell(2, _set(3, -7) + _line("CITNE", "3,-7")),
    "CGIT": trapped(3, _set(3, -7) + _line("CGIT", "3,-8,2")),
    "CGITE high word counts": fell(3, SEVENS + _line("CGITE", "3,7")),
    "CLFIT": trapped(1, _line("LHI", "3,-1") + _line("CLFIT", "3,65535,2")),
    "CLFITE": trapped(1, _line("LLILL", "3,65535") + _line("CLFITE", "3,65535")),
    "CLFITL": fell(1, _line("LLILL", "3,65535") + _line("CLFITL", "3,65535")),
    "CLGIT": fell(0, _line("LGHI", "3,9") + _line("CLGIT", "3,9,4")),
    "CLGITH": trapped(0, _line("LGHI", "3,-1") + _line("CLGITH", "3,65535")),
    "CLT": fell(2, _line("L", "3,NEG") + _line("CLT", "3,8,POS")),
    "CLTH": trapped(2, _line("L", "3,NEG") + _line("CLTH", "3,POS")),
    "CLGT": trapped(3, _line("LG", "3,DPOS") + _line("CLGT", "3,8,DPOS")),
    "CLGTNL": fell(3, _line("LG", "3,DPOS") + _line("CLGTNL", "3,DNEG")),
}

ZERO_DOUBLEWORD = _line("LGHI", "5,0") + _line("STG", "5,OUT")
BIT_ZERO_WORD = _line("LLILH", "5,X'8000'") + _line("ST", "5,OUT")

LOAD_AND_TRAP: Mapping[str, Case] = {
    "LAT": fell(1, _line("LAT", "3,POS"), {3: HIGH_FILL | 0x7FFF7FFE}),
    "LAT zero": trapped(1, _line("LAT", "3,ZERO"), {3: HIGH_FILL}),
    "LAT indexed": fell(
        2, _line("LA", "5,4") + _line("LAT", "3,POS-4(5)"), {3: HIGH_FILL | 0x7FFF7FFE}
    ),
    "LGAT": fell(2, _line("LGAT", "3,DNEG"), {3: 0x80000000_00000081}),
    "LGAT zero": trapped(2, ZERO_DOUBLEWORD + _line("LGAT", "3,OUT"), {3: 0}),
    "LLGFAT": fell(0, _line("LLGFAT", "3,NEG"), {3: 0x80000001}),
    "LLGFAT zero": trapped(0, _line("LLGFAT", "3,ZERO"), {3: 0}),
    "LLGTAT": fell(3, _line("LLGTAT", "3,NEG"), {3: 1}),
    "LLGTAT bit 0 only": trapped(3, BIT_ZERO_WORD + _line("LLGTAT", "3,OUT"), {3: 0}),
}

CASES: Mapping[str, Case] = {
    **COMPARE_AND_BRANCH_RELATIVE,
    **COMPARE_AND_BRANCH,
    **COMPARE_AND_TRAP,
    **LOAD_AND_TRAP,
}


def expected(case: str) -> HlasmMachine:
    cc, _, registers, abend = CASES[case]
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)
