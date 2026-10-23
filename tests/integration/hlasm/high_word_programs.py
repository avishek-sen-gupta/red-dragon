# pyright: standard
"""High-word programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; registers start with distinct high and low words."""

from collections.abc import Mapping

from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL

type Case = tuple[str, Mapping[int, int], int, str]

COMPLETED = "U0001"
DATA_EXCEPTION = "S0C7"
CC_ZERO = 0
CC_ONE = 1
CC_TWO = 2
CC_THREE = 3
LOW_FILL = FILL & 0xFFFFFFFF
WORD_BITS = 32
PRESET_CC = CC_TWO
PRESET = "         CLI   NEG,0\n"


def _line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<6} {operands}\n"


def _high(r: int, value: int) -> str:
    return _line("IIHF", f"{r},X'{value:08X}'")


def _low(r: int, value: int) -> str:
    return _line("IILF", f"{r},X'{value:08X}'")


def with_high(value: int) -> int:
    return (value << WORD_BITS) | LOW_FILL


def with_low(value: int) -> int:
    return HIGH_FILL | value


def _ran(body: str, results: Mapping[int, int], cc: int) -> Case:
    return (body, results, cc, COMPLETED)


def _kept(body: str, results: Mapping[int, int]) -> Case:
    return (PRESET + body, results, PRESET_CC, COMPLETED)


def _hh(mnemonic: str, second: int, third: int) -> str:
    return _high(3, second) + _high(4, third) + _line(mnemonic, "2,3,4")


def _hl(mnemonic: str, second: int, third: int) -> str:
    return _high(3, second) + _low(4, third) + _line(mnemonic, "2,3,4")


SIGNED_ARITHMETIC: Mapping[str, Case] = {
    "AHHHR": _ran(_hh("AHHHR", 5, 7), {2: with_high(12), 3: with_high(5)}, CC_TWO),
    "AHHHR zero": _ran(_hh("AHHHR", 5, 0xFFFFFFFB), {2: with_high(0)}, CC_ZERO),
    "AHHHR overflow": _ran(
        _hh("AHHHR", 0x7FFFFFFF, 1), {2: with_high(0x80000000)}, CC_THREE
    ),
    "AHHLR": _ran(
        _hl("AHHLR", 5, 0xFFFFFFF9),
        {2: with_high(0xFFFFFFFE), 4: with_low(0xFFFFFFF9)},
        CC_ONE,
    ),
    "SHHHR": _ran(_hh("SHHHR", 5, 7), {2: with_high(0xFFFFFFFE)}, CC_ONE),
    "SHHHR zero": _ran(_hh("SHHHR", 7, 7), {2: with_high(0)}, CC_ZERO),
    "SHHHR overflow": _ran(
        _hh("SHHHR", 0x80000000, 1), {2: with_high(0x7FFFFFFF)}, CC_THREE
    ),
    "AHHLR overflow": _ran(
        _hl("AHHLR", 0x7FFFFFFF, 1), {2: with_high(0x80000000)}, CC_THREE
    ),
    "SHHLR overflow": _ran(
        _hl("SHHLR", 0x80000000, 1), {2: with_high(0x7FFFFFFF)}, CC_THREE
    ),
    "SHHLR": _ran(_hl("SHHLR", 9, 2), {2: with_high(7)}, CC_TWO),
    "AIH overflow": _ran(
        _high(2, 0x7FFFFFF0) + _line("AIH", "2,16"),
        {2: with_high(0x80000000)},
        CC_THREE,
    ),
    "AIH negative": _ran(
        _high(2, 10) + _line("AIH", "2,-13"), {2: with_high(0xFFFFFFFD)}, CC_ONE
    ),
}

LOGICAL_ARITHMETIC: Mapping[str, Case] = {
    "ALHHHR carry": _ran(_hh("ALHHHR", 0xFFFFFFFF, 1), {2: with_high(0)}, CC_TWO),
    "ALHHHR carry nonzero": _ran(
        _hh("ALHHHR", 0xFFFFFFFF, 2), {2: with_high(1)}, CC_THREE
    ),
    "ALHHLR": _ran(_hl("ALHHLR", 5, 7), {2: with_high(12)}, CC_ONE),
    "ALHHLR zero": _ran(_hl("ALHHLR", 0, 0), {2: with_high(0)}, CC_ZERO),
    "ALHHLR carry": _ran(_hl("ALHHLR", 0xFFFFFFFF, 2), {2: with_high(1)}, CC_THREE),
    "SLHHHR borrow": _ran(_hh("SLHHHR", 5, 7), {2: with_high(0xFFFFFFFE)}, CC_ONE),
    "SLHHHR": _ran(_hh("SLHHHR", 7, 5), {2: with_high(2)}, CC_THREE),
    "SLHHLR zero": _ran(_hl("SLHHLR", 7, 7), {2: with_high(0)}, CC_TWO),
    "SLHHLR borrow": _ran(_hl("SLHHLR", 1, 2), {2: with_high(0xFFFFFFFF)}, CC_ONE),
    "ALSIH carry": _ran(
        _high(2, 0xFFFFFFF0) + _line("ALSIH", "2,16"), {2: with_high(0)}, CC_TWO
    ),
    "ALSIH": _ran(_high(2, 3) + _line("ALSIH", "2,16"), {2: with_high(19)}, CC_ONE),
    "ALSIH negative": _ran(
        _high(2, 1) + _line("ALSIH", "2,-1"), {2: with_high(0)}, CC_TWO
    ),
    "ALSIH negative borrow": _ran(
        _high(2, 0) + _line("ALSIH", "2,-1"), {2: with_high(0xFFFFFFFF)}, CC_ONE
    ),
    "ALSIHN": _kept(_high(2, 1) + _line("ALSIHN", "2,4"), {2: with_high(5)}),
    "ALSIHN negative": _kept(
        _high(2, 0) + _line("ALSIHN", "2,-1"), {2: with_high(0xFFFFFFFF)}
    ),
}


def _count_loop(mnemonic: str) -> str:
    return (
        _line("LHI", "3,0")
        + "LOOP     AHI   3,1\n"
        + PRESET
        + _line(mnemonic, "4,LOOP")
    )


BRANCH_ON_COUNT: Mapping[str, Case] = {
    "BRCTH": _ran(
        _high(4, 5) + _count_loop("BRCTH"),
        {3: with_low(5), 4: with_high(0)},
        PRESET_CC,
    ),
    "JCTH": _ran(
        _high(4, 3) + _count_loop("JCTH"),
        {3: with_low(3), 4: with_high(0)},
        PRESET_CC,
    ),
    "BRCTH low word ignored": _ran(
        _high(4, 1) + _low(4, 5) + _count_loop("BRCTH"),
        {3: with_low(1), 4: 0x00000000_00000005},
        PRESET_CC,
    ),
    "BRCTH wraps": _kept(
        _high(4, 0)
        + _line("LHI", "5,1")
        + _line("BRCTH", "4,SKIP")
        + _line("LHI", "5,2")
        + "SKIP     LHI   6,3\n",
        {4: with_high(0xFFFFFFFF), 5: with_low(1), 6: with_low(3)},
    ),
}

COMPARES: Mapping[str, Case] = {
    "CHHR low": _ran(
        _high(3, 0xFFFFFFFF) + _high(4, 1) + _line("CHHR", "3,4"),
        {3: with_high(0xFFFFFFFF), 4: with_high(1)},
        CC_ONE,
    ),
    "CLHHR high": _ran(
        _high(3, 0xFFFFFFFF) + _high(4, 1) + _line("CLHHR", "3,4"),
        {3: with_high(0xFFFFFFFF), 4: with_high(1)},
        CC_TWO,
    ),
    "CHLR equal": _ran(
        _high(3, 5) + _low(4, 5) + _line("CHLR", "3,4"),
        {3: with_high(5), 4: with_low(5)},
        CC_ZERO,
    ),
    "CHLR high": _ran(
        _high(3, 1) + _low(4, 0x80000000) + _line("CHLR", "3,4"),
        {3: with_high(1), 4: with_low(0x80000000)},
        CC_TWO,
    ),
    "CLHLR high": _ran(
        _high(3, 0x80000000) + _low(4, 1) + _line("CLHLR", "3,4"),
        {3: with_high(0x80000000), 4: with_low(1)},
        CC_TWO,
    ),
    "CLHLR equal": _ran(
        _high(3, LOW_FILL) + _line("CLHLR", "3,4"),
        {3: with_high(LOW_FILL), 4: FILL},
        CC_ZERO,
    ),
    "CHF equal": _ran(
        _high(3, 0x80000001) + _line("CHF", "3,NEG"),
        {3: with_high(0x80000001)},
        CC_ZERO,
    ),
    "CHF low": _ran(
        _high(3, 0x80000001) + _line("CHF", "3,POS"), {3: with_high(0x80000001)}, CC_ONE
    ),
    "CLHF high": _ran(
        _high(3, 0x80000001) + _line("CLHF", "3,POS"),
        {3: with_high(0x80000001)},
        CC_TWO,
    ),
    "CLHF indexed": _ran(
        _high(3, 0x7FFF7FFE) + _line("LA", "5,4") + _line("CLHF", "3,NEG(5)"),
        {3: with_high(0x7FFF7FFE)},
        CC_ZERO,
    ),
    "CIH equal": _ran(
        _high(3, 0xFFFFFFF0) + _line("CIH", "3,-16"),
        {3: with_high(0xFFFFFFF0)},
        CC_ZERO,
    ),
    "CIH low": _ran(
        _high(3, 0xFFFFFFF0) + _line("CIH", "3,-15"), {3: with_high(0xFFFFFFF0)}, CC_ONE
    ),
    "CLIH high": _ran(
        _high(3, 0xFFFFFFF0) + _line("CLIH", "3,1"), {3: with_high(0xFFFFFFF0)}, CC_TWO
    ),
    "CLIH low": _ran(
        _high(3, 1) + _line("CLIH", "3,X'FFFFFFF0'"), {3: with_high(1)}, CC_ONE
    ),
}

UNDER_MASK: Mapping[str, Case] = {
    "ICMH": _ran(_line("ICMH", "2,B'1010',NEG"), {2: 0x80A500A5_A5A5A5A5}, CC_ONE),
    "ICMH positive": _ran(
        _line("ICMH", "2,B'0011',POS"), {2: 0xA5A57FFF_A5A5A5A5}, CC_TWO
    ),
    "ICMH zero": _ran(_line("ICMH", "2,B'1111',ZERO"), {2: with_high(0)}, CC_ZERO),
    "ICMH mask 0": _ran(PRESET + _line("ICMH", "2,B'0000',NEG"), {2: FILL}, CC_ZERO),
    "STCMH": _kept(
        _line("LG", "2,SRC")
        + _line("STCMH", "2,B'1010',OUT")
        + _line("STCMH", "2,B'0111',OUT+8")
        + _line("STCMH", "2,B'0000',OUT+16")
        + _line("STCMH", "2,B'1111',OUT+24")
        + _line("LMG", "3,6,OUT"),
        {
            3: 0x0145FFFF_FFFFFFFF,
            4: 0x234567FF_FFFFFFFF,
            5: 0xFFFFFFFF_FFFFFFFF,
            6: 0x01234567_FFFFFFFF,
        },
    ),
    "CLMH high": _ran(
        _line("LG", "2,SRC") + _line("CLMH", "2,B'1010',SRC"), {}, CC_TWO
    ),
    "CLMH equal": _ran(
        _line("LG", "2,SRC") + _line("CLMH", "2,B'1100',SRC"), {}, CC_ZERO
    ),
    "CLMH low": _ran(
        _line("LG", "2,SRC") + _line("CLMH", "2,B'0001',SRCP"), {}, CC_ONE
    ),
    "CLMH mask 0": _ran(
        PRESET + _line("LG", "2,SRC") + _line("CLMH", "2,B'0000',SRCP"), {}, CC_ZERO
    ),
}

LOADS_AND_STORES: Mapping[str, Case] = {
    "high loads": _kept(
        _line("LBH", "2,NEG")
        + _line("LHH", "3,NEG")
        + _line("LFH", "4,POS")
        + _line("LLCH", "5,NEG")
        + _line("LLHH", "6,NEG")
        + _line("LA", "7,4")
        + _line("LHH", "8,NEG(7)")
        + _line("LBH", "9,POS+1"),
        {
            2: with_high(0xFFFFFF80),
            3: with_high(0xFFFF8000),
            4: with_high(0x7FFF7FFE),
            5: with_high(0x00000080),
            6: with_high(0x00008000),
            8: with_high(0x00007FFF),
            9: with_high(0xFFFFFFFF),
        },
    ),
    "high stores": _kept(
        _high(2, 0x01234567)
        + _line("STCH", "2,OUT")
        + _line("STHH", "2,OUT+1")
        + _line("STFH", "2,OUT+3")
        + _line("LG", "3,OUT"),
        {2: with_high(0x01234567), 3: 0x67456701_234567FF},
    ),
    "LMH STMH": _kept(
        _line("LMH", "2,4,HIGHS") + _line("STMH", "3,4,OUT") + _line("LG", "5,OUT"),
        {
            2: with_high(0x11111111),
            3: with_high(0x22222222),
            4: with_high(0x33333333),
            5: 0x22222222_33333333,
        },
    ),
    "LMH STMH wrapping": _kept(
        _line("LGHI", "15,7")
        + _line("LGHI", "0,8")
        + _line("LMH", "15,0,WORDS")
        + _line("STMH", "15,0,OUT")
        + _line("LGR", "8,15")
        + _line("LGR", "9,0")
        + _line("LG", "10,OUT"),
        {8: 0x00000001_00000007, 9: 0x00000002_00000008, 10: 0x00000001_00000002},
    ),
    "LFHAT": _kept(_line("LFHAT", "3,NEG"), {3: with_high(0x80000001)}),
    "LFHAT zero": (
        PRESET + _line("LFHAT", "3,ZERO") + _line("LHI", "4,1"),
        {3: with_high(0), 4: FILL},
        PRESET_CC,
        DATA_EXCEPTION,
    ),
}

CASES: Mapping[str, Case] = {
    **SIGNED_ARITHMETIC,
    **LOGICAL_ARITHMETIC,
    **BRANCH_ON_COUNT,
    **COMPARES,
    **UNDER_MASK,
    **LOADS_AND_STORES,
}


def expected(case: str) -> HlasmMachine:
    _, registers, cc, abend = CASES[case]
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)
