# pyright: standard
"""BFP arithmetic programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; FPRs come back through LGDR, intermediate CCs through IPM, and every program first clears the FPC."""

from collections.abc import Callable, Mapping

from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import ABEND, HIGH_FILL, based_program

type Case = tuple[str, Mapping[int, int], int, str, int]
type Trap = tuple[str, Mapping[int, int], int, int]

COMPLETED = "U0001"
DATA_EXCEPTION = "S0C7"
PRESET_CC = 2
PRESET = "         CLI   NEG,0\n"
INVALID_FLAG = 0x00800000
DIVIDE_FLAG = 0x00400000
INEXACT_FLAG = 0x00080000

DATA = (
    "         DS    0D\n"
    "D1       DC    X'3FF0000000000000'\n"
    "D2       DC    X'4000000000000000'\n"
    "D3       DC    X'40080000',X'00000000'\n"
    "D7       DC    X'401C000000000000'\n"
    "D9       DC    X'4022000000000000'\n"
    "DM1      DC    X'BFF0000000000000'\n"
    "DM2      DC    X'C000000000000000'\n"
    "DM3      DC    X'C008000000000000'\n"
    "D0       DC    X'0000000000000000'\n"
    "DHALF    DC    X'3FE0000000000000'\n"
    "D2P5     DC    X'4004000000000000'\n"
    "DMAX     DC    X'7FEFFFFFFFFFFFFF'\n"
    "DNMIN    DC    X'0010000000000000'\n"
    "DINF     DC    X'7FF0000000000000'\n"
    "DMINF    DC    X'FFF0000000000000'\n"
    "DQNAN    DC    X'7FF8000000000005'\n"
    "DQNAN2   DC    X'7FF800000000000A'\n"
    "DSNAN    DC    X'7FF0000000000009'\n"
    "DM0      DC    X'8000000000000000'\n"
    "DSUB     DC    X'0000000000000001'\n"
    "DMSUB    DC    X'8000000000000001'\n"
    "DMQNAN   DC    X'FFF8000000000005'\n"
    "DMSNAN   DC    X'FFF0000000000009'\n"
    "DTHIRD   DC    X'3FD5555555555555'\n"
    "DUP      DC    X'3FF0000000400000'\n"
    "DDOWN    DC    X'3FEFFFFFFF800000'\n"
    "DP60     DC    X'43B0000000000000'\n"
    "X1       DC    X'3FFF0000000000000000000000001000'\n"
    "X2       DC    X'40000000000000000000000000000000'\n"
    "X3       DC    X'40008000000000000000000000000000'\n"
    "XM2P5    DC    X'C0004000000000000000000000000000'\n"
    "X4       DC    X'40010000000000000000000000000000'\n"
    "S1       DC    X'3F800000'\n"
    "S2       DC    X'40000000'\n"
    "S3       DC    X'40400000'\n"
    "S4       DC    X'40800000'\n"
    "S7       DC    X'40E00000'\n"
    "SM8      DC    X'C1000000'\n"
    "SM2P5    DC    X'C0200000'\n"
    "SM1P5    DC    X'BFC00000'\n"
    "SM0      DC    X'80000000'\n"
    "STHIRD   DC    X'3EAAAAAB'\n"
    "SMAX     DC    X'7F7FFFFF'\n"
    "SQNAN    DC    X'7FC00000'\n"
    "STINY3   DC    X'00000003'\n"
    "STINY2   DC    X'00000002'\n"
    "SBIG     DC    X'7F000000'\n"
    "SNMIN    DC    X'00800000'\n"
    "TS0      DC    X'00000000'\n"
    "TSM1     DC    X'BF800000'\n"
    "TSSUB    DC    X'00000001'\n"
    "TSMSUB   DC    X'80000001'\n"
    "TSINF    DC    X'7F800000'\n"
    "TSMINF   DC    X'FF800000'\n"
    "TSMQNAN  DC    X'FFC00000'\n"
    "TSSNAN   DC    X'7F800001'\n"
    "TSMSNAN  DC    X'FF800001'\n"
    "         DS    0D\n"
    "TX0      DC    X'00000000000000000000000000000000'\n"
    "TXM0     DC    X'80000000000000000000000000000000'\n"
    "TXM1     DC    X'BFFF0000000000000000000000000000'\n"
    "TXSUB    DC    X'00000000000000000000000000000001'\n"
    "TXMSUB   DC    X'80000000000000000000000000000001'\n"
    "TXINF    DC    X'7FFF0000000000000000000000000000'\n"
    "TXMINF   DC    X'FFFF0000000000000000000000000000'\n"
    "TXQNAN   DC    X'7FFF8000000000000000000000000000'\n"
    "TXMQNAN  DC    X'FFFF8000000000000000000000000000'\n"
    "TXSNAN   DC    X'7FFF0000000000000000000000000001'\n"
    "TXMSNAN  DC    X'FFFF0000000000000000000000000001'\n"
)


def _line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<6} {operands}\n"


def lines(*statements: str) -> str:
    return "".join(_line(*statement.split(" ", 1)) for statement in statements)


def set_fpc(value: int) -> str:
    return _line("IILF", f"7,X'{value:08X}'") + _line("SFPC", "7")


def cc_into(register: int) -> str:
    return _line("IPM", f"{register}") + _line("SRL", f"{register},28")


def zeroed_short(*registers: int) -> str:
    return "".join(_line("LZDR", f"{r}") for r in registers)


def extended_from(register: int, label: str) -> str:
    return _line("LD", f"{register},{label}") + _line("LD", f"{register + 2},{label}+8")


def high_word(value: int) -> int:
    return value << 32


def cc_word(cc: int) -> int:
    return HIGH_FILL | cc


def case_of(body: str, registers: Mapping[int, int], cc: int, fpc: int = 0) -> Case:
    return (set_fpc(0) + PRESET + body, registers, cc, COMPLETED, fpc)


LONG_CLASSES = (
    "D0",
    "DM0",
    "D1",
    "DM1",
    "DSUB",
    "DMSUB",
    "DINF",
    "DMINF",
    "DQNAN",
    "DMQNAN",
    "DSNAN",
    "DMSNAN",
)
SHORT_CLASSES = (
    "TS0",
    "SM0",
    "S1",
    "TSM1",
    "TSSUB",
    "TSMSUB",
    "TSINF",
    "TSMINF",
    "SQNAN",
    "TSMQNAN",
    "TSSNAN",
    "TSMSNAN",
)
EXTENDED_CLASSES = (
    "TX0",
    "TXM0",
    "X1",
    "TXM1",
    "TXSUB",
    "TXMSUB",
    "TXINF",
    "TXMINF",
    "TXQNAN",
    "TXMQNAN",
    "TXSNAN",
    "TXMSNAN",
)


def _load_short(label: str) -> str:
    return lines(f"LE 1,{label}")


def _load_long(label: str) -> str:
    return lines(f"LD 1,{label}")


def _load_extended(label: str) -> str:
    return extended_from(1, label)


type ClassTest = tuple[str, Callable[[str], str], tuple[str, ...]]

TCEB: ClassTest = ("TCEB", _load_short, SHORT_CLASSES)
TCDB: ClassTest = ("TCDB", _load_long, LONG_CLASSES)
TCXB: ClassTest = ("TCXB", _load_extended, EXTENDED_CLASSES)


def _classes(test: ClassTest, selected: int, others: int, first: int) -> str:
    mnemonic, load, labels = test
    return "".join(
        load(label)
        + lines(
            f"{mnemonic} 1,X'{(1 << (11 - at)) * selected | (0xFFF ^ (1 << (11 - at))) * others:03X}'",
        )
        + cc_into(2 + at - first)
        for at, label in enumerate(labels)
        if first <= at < first + 6
    )


def _class_case(test: ClassTest, selected: int, others: int, first: int) -> Case:
    return case_of(
        _classes(test, selected, others, first),
        {2 + at: cc_word(selected) for at in range(6)},
        selected,
    )


def program(body: str) -> str:
    return based_program(body, ABEND + DATA)


ADD_SUBTRACT: Mapping[str, Case] = {
    "AEBR AEB": case_of(
        zeroed_short(1, 2)
        + lines("LE 1,S1", "LE 2,S2", "AEBR 1,2", "LGDR 2,1", "AEB 1,SM8", "LGDR 3,1"),
        {2: high_word(0x40400000), 3: high_word(0xC0A00000)},
        1,
    ),
    "ADBR ADB": case_of(
        lines("LD 1,D1", "LD 2,D2", "ADBR 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("ADB 1,DM3", "LGDR 3,1"),
        {2: 0x40080000_00000000, 8: cc_word(2), 3: 0},
        0,
    ),
    "AXBR": case_of(
        extended_from(1, "X1")
        + extended_from(4, "X2")
        + lines("AXBR 1,4", "LGDR 2,1", "LGDR 3,3"),
        {2: 0x40008000_00000000, 3: 0x800},
        2,
    ),
    "SEBR SEB": case_of(
        zeroed_short(1, 2)
        + lines("LE 1,S3", "LE 2,S1", "SEBR 1,2", "LGDR 2,1", "SEB 1,S3", "LGDR 3,1"),
        {2: high_word(0x40000000), 3: high_word(0xBF800000)},
        1,
    ),
    "SDBR SDB": case_of(
        lines("LD 1,D1", "LD 2,D3", "SDBR 1,2", "LGDR 2,1")
        + cc_into(8)
        + set_fpc(3)
        + lines("SDB 1,DM2", "LGDR 3,1"),
        {2: 0xC0000000_00000000, 8: cc_word(1), 3: 0x80000000_00000000},
        0,
        3,
    ),
    "SXBR": case_of(
        extended_from(1, "X3")
        + extended_from(4, "X2")
        + lines("SXBR 1,4", "LGDR 2,1", "LGDR 3,3"),
        {2: 0x3FFF0000_00000000, 3: 0},
        2,
    ),
}

MULTIPLY_DIVIDE: Mapping[str, Case] = {
    "MEEBR MEEB": case_of(
        zeroed_short(1, 2)
        + lines(
            "LE 1,S3", "LE 2,S2", "MEEBR 1,2", "LGDR 2,1", "MEEB 1,SM8", "LGDR 3,1"
        ),
        {2: high_word(0x40C00000), 3: high_word(0xC2400000)},
        PRESET_CC,
    ),
    "MDBR MDB": case_of(
        lines("LD 1,D3", "LD 2,DHALF", "MDBR 1,2", "LGDR 2,1", "MDB 1,D2", "LGDR 3,1"),
        {2: 0x3FF80000_00000000, 3: 0x40080000_00000000},
        PRESET_CC,
    ),
    "MXBR": case_of(
        extended_from(1, "X1")
        + extended_from(4, "X2")
        + lines("MXBR 1,4", "LGDR 2,1", "LGDR 3,3"),
        {2: 0x40000000_00000000, 3: 0x1000},
        PRESET_CC,
    ),
    "MDEBR MDEB": case_of(
        zeroed_short(1, 2, 3)
        + lines(
            "LE 1,STHIRD", "LE 2,S3", "MDEBR 1,2", "LGDR 2,1", "LE 3,S2", "MDEB 3,SM8"
        )
        + lines("LGDR 3,3"),
        {2: 0x3FF00000_08000000, 3: 0xC0300000_00000000},
        PRESET_CC,
    ),
    "MXDBR MXDB": case_of(
        lines("LD 1,DTHIRD", "LD 2,D3", "MXDBR 1,2", "LGDR 2,1", "LGDR 3,3")
        + lines("LD 4,D2", "MXDB 4,DM3", "LGDR 4,4", "LGDR 5,6"),
        {
            2: 0x3FFEFFFF_FFFFFFFF,
            3: 0xF8000000_00000000,
            4: 0xC0018000_00000000,
            5: 0,
        },
        PRESET_CC,
    ),
    "MDB underflow nontrap": case_of(
        lines("LD 1,DNMIN", "MDB 1,DTHIRD", "LGDR 2,1"),
        {2: 0x00055555_55555555},
        PRESET_CC,
        0x00180000,
    ),
    "DEBR DEB": case_of(
        zeroed_short(1, 2)
        + lines("LE 1,S1", "LE 2,S2", "DEBR 1,2", "LGDR 2,1", "DEB 1,S3", "LGDR 3,1"),
        {2: high_word(0x3F000000), 3: high_word(0x3E2AAAAB)},
        PRESET_CC,
        INEXACT_FLAG,
    ),
    "DDBR DDB": case_of(
        lines("LD 1,D3", "LD 2,D2", "DDBR 1,2", "LGDR 2,1", "DDB 1,D0", "LGDR 3,1"),
        {2: 0x3FF80000_00000000, 3: 0x7FF00000_00000000},
        PRESET_CC,
        DIVIDE_FLAG,
    ),
    "DXBR": case_of(
        extended_from(1, "X3")
        + extended_from(4, "X2")
        + lines("DXBR 1,4", "LGDR 2,1", "LGDR 3,3"),
        {2: 0x3FFF8000_00000000, 3: 0},
        PRESET_CC,
    ),
}

ROOTS_FUSED: Mapping[str, Case] = {
    "SQEBR SQEB": case_of(
        zeroed_short(1, 2, 3)
        + lines("LE 2,S4", "SQEBR 1,2", "LGDR 2,1", "SQEB 3,S2", "LGDR 3,3"),
        {2: high_word(0x40000000), 3: high_word(0x3FB504F3)},
        PRESET_CC,
        INEXACT_FLAG,
    ),
    "SQDBR SQDB": case_of(
        lines("LD 2,D9", "SQDBR 1,2", "LGDR 2,1", "SQDB 3,DM1", "LGDR 3,3"),
        {2: 0x40080000_00000000, 3: 0x7FF80000_00000000},
        PRESET_CC,
        INVALID_FLAG,
    ),
    "SQXBR": case_of(
        extended_from(4, "X4") + lines("SQXBR 1,4", "LGDR 2,1", "LGDR 3,3"),
        {2: 0x40000000_00000000, 3: 0},
        PRESET_CC,
    ),
    "MAEBR MAEB": case_of(
        zeroed_short(1, 2, 3)
        + lines("LE 1,S1", "LE 3,S2", "LE 2,S3", "MAEBR 1,3,2", "LGDR 2,1")
        + lines("MAEB 1,3,S1", "LGDR 3,1"),
        {2: high_word(0x40E00000), 3: high_word(0x41100000)},
        PRESET_CC,
    ),
    "MADBR MADB": case_of(
        lines("LD 1,DM1", "LD 3,DUP", "LD 2,DDOWN", "MADBR 1,3,2", "LGDR 2,1")
        + lines("LD 4,D1", "LD 5,D2", "MADB 4,5,D3", "LGDR 3,4"),
        {2: 0xBC300000_00000000, 3: 0x401C0000_00000000},
        PRESET_CC,
    ),
    "MSEBR MSEB": case_of(
        zeroed_short(1, 2, 3)
        + lines("LE 1,S1", "LE 3,S2", "LE 2,S3", "MSEBR 1,3,2", "LGDR 2,1")
        + lines("MSEB 1,3,S3", "LGDR 3,1"),
        {2: high_word(0x40A00000), 3: high_word(0x3F800000)},
        PRESET_CC,
    ),
    "MSDBR MSDB": case_of(
        lines("LD 1,D7", "LD 3,D2", "LD 2,D3", "MSDBR 1,3,2", "LGDR 2,1")
        + lines("MSDB 1,3,D2", "LGDR 3,1"),
        {2: 0xBFF00000_00000000, 3: 0x40140000_00000000},
        PRESET_CC,
    ),
    "MADBR NaN order": case_of(
        lines("LD 1,DSNAN", "LD 3,DQNAN", "LD 2,D1", "MADBR 1,3,2", "LGDR 2,1")
        + lines("LD 4,DQNAN", "LD 5,DQNAN2", "LD 6,D1", "MADBR 4,5,6", "LGDR 3,4")
        + lines("LD 8,DSNAN", "LD 9,D0", "LD 10,DINF", "MADBR 8,9,10", "LGDR 4,8"),
        {2: 0x7FF80000_00000009, 3: 0x7FF80000_0000000A, 4: 0x7FF80000_00000000},
        PRESET_CC,
        INVALID_FLAG,
    ),
}

COMPARES: Mapping[str, Case] = {
    "CEBR CEB": case_of(
        zeroed_short(1, 2)
        + lines("LE 1,S1", "LE 2,S2", "CEBR 1,2")
        + cc_into(8)
        + lines("CEB 1,SQNAN"),
        {8: cc_word(1)},
        3,
    ),
    "CDBR CDB": case_of(
        lines("LD 1,D2", "LD 2,D1", "CDBR 1,2") + cc_into(8) + lines("CDB 1,DSNAN"),
        {8: cc_word(2)},
        3,
        INVALID_FLAG,
    ),
    "CXBR": case_of(
        extended_from(1, "X2") + extended_from(4, "X2") + lines("CXBR 1,4"), {}, 0
    ),
    "KEBR KEB": case_of(
        zeroed_short(1)
        + lines("LE 1,S1", "KEBR 1,1")
        + cc_into(8)
        + lines("KEB 1,SQNAN"),
        {8: cc_word(0)},
        3,
        INVALID_FLAG,
    ),
    "KDBR KDB": case_of(
        lines("LD 1,D1", "LD 2,DINF", "KDBR 1,2") + cc_into(8) + lines("KDB 1,DMINF"),
        {8: cc_word(1)},
        2,
    ),
    "CDBR signed order": case_of(
        lines("LD 1,DM2", "LD 2,DM1", "CDBR 1,2")
        + cc_into(8)
        + lines("LD 1,DM0", "LD 2,D0", "CDBR 1,2")
        + cc_into(9)
        + lines("LD 1,DINF", "CDB 1,DINF")
        + cc_into(10)
        + lines("LD 1,DM1", "CDB 1,DMINF"),
        {8: cc_word(1), 9: cc_word(0), 10: cc_word(0)},
        2,
    ),
    "CXBR high": case_of(
        extended_from(1, "X3") + extended_from(4, "X2") + lines("CXBR 1,4"), {}, 2
    ),
    "KXBR": case_of(
        extended_from(1, "X1") + extended_from(4, "X2") + lines("KXBR 1,4"), {}, 1
    ),
}

INTEGRAL: Mapping[str, Case] = {
    "TCEB selects the class bit, zeros to subnormals": _class_case(TCEB, 1, 0, 0),
    "TCEB selects the class bit, infinities to SNaNs": _class_case(TCEB, 1, 0, 6),
    "TCEB misses every other bit, zeros to subnormals": _class_case(TCEB, 0, 1, 0),
    "TCEB misses every other bit, infinities to SNaNs": _class_case(TCEB, 0, 1, 6),
    "TCDB selects the class bit, zeros to subnormals": _class_case(TCDB, 1, 0, 0),
    "TCDB selects the class bit, infinities to SNaNs": _class_case(TCDB, 1, 0, 6),
    "TCDB misses every other bit, zeros to subnormals": _class_case(TCDB, 0, 1, 0),
    "TCDB misses every other bit, infinities to SNaNs": _class_case(TCDB, 0, 1, 6),
    "TCXB selects the class bit, zeros to subnormals": _class_case(TCXB, 1, 0, 0),
    "TCXB selects the class bit, infinities to SNaNs": _class_case(TCXB, 1, 0, 6),
    "TCXB misses every other bit, zeros to subnormals": _class_case(TCXB, 0, 1, 0),
    "TCXB misses every other bit, infinities to SNaNs": _class_case(TCXB, 0, 1, 6),
    "FIEBR FIEBRA": case_of(
        zeroed_short(1, 2, 3)
        + lines("LE 2,SM2P5", "FIEBR 1,0,2", "LGDR 2,1", "FIEBRA 3,1,2,4", "LGDR 3,3"),
        {2: high_word(0xC0000000), 3: high_word(0xC0400000)},
        PRESET_CC,
        INEXACT_FLAG,
    ),
    "FIDBR FIDBRA": case_of(
        lines("LD 2,D2P5", "FIDBR 1,0,2", "LGDR 2,1", "FIDBRA 3,6,2,0", "LGDR 3,3"),
        {2: 0x40000000_00000000, 3: 0x40080000_00000000},
        PRESET_CC,
        INEXACT_FLAG,
    ),
    "FIXBR FIXBRA": case_of(
        extended_from(4, "XM2P5")
        + lines("FIXBR 1,5,4", "LGDR 2,1", "LGDR 3,3")
        + set_fpc(0)
        + lines("FIXBRA 8,7,4,4", "LGDR 4,8", "LGDR 5,10"),
        {2: 0xC0000000_00000000, 3: 0, 4: 0xC0008000_00000000, 5: 0},
        PRESET_CC,
    ),
    "DIEBR": case_of(
        zeroed_short(1, 2, 3)
        + lines("LE 1,S7", "LE 2,S2", "DIEBR 1,3,2,5", "LGDR 2,1", "LGDR 3,3"),
        {2: high_word(0x3F800000), 3: high_word(0x40400000)},
        0,
    ),
    "DIEBR DIDBR in the current mode": case_of(
        zeroed_short(1, 2, 3)
        + set_fpc(1)
        + lines("LE 1,S7", "LE 2,S2", "DIEBR 1,3,2,0", "LGDR 2,1", "LGDR 3,3")
        + lines("LD 4,D7", "LD 5,D2", "DIDBR 4,6,5,0", "LGDR 4,4", "LGDR 5,6"),
        {
            2: high_word(0x3F800000),
            3: high_word(0x40400000),
            4: 0x3FF00000_00000000,
            5: 0x40080000_00000000,
        },
        0,
        1,
    ),
    "DIEBR quotient overflow": case_of(
        zeroed_short(1, 2, 3)
        + lines("LE 1,SBIG", "LE 2,SNMIN", "DIEBR 1,3,2,4", "LGDR 2,1", "LGDR 3,3"),
        {2: 0, 3: high_word(0x5E000000)},
        1,
    ),
    "DIDBR": case_of(
        lines("LD 1,DP60", "LD 2,D3", "DIDBR 1,3,2,4", "LGDR 2,1", "LGDR 3,3"),
        {2: 0x40500000_00000000, 3: 0x43955555_55555555},
        2,
    ),
    "TCEB TCDB TCXB": case_of(
        zeroed_short(1)
        + lines("LE 1,SM0", "TCEB 1,X'400'")
        + cc_into(8)
        + lines("LD 2,DINF", "TCDB 2,X'800'")
        + cc_into(9)
        + extended_from(4, "X1")
        + lines("TCXB 4,X'200'"),
        {8: cc_word(1), 9: cc_word(0)},
        1,
    ),
}

SIGN_FORMS: Mapping[str, Case] = {
    "LTEBR LTDBR LTXBR": case_of(
        zeroed_short(2)
        + lines("LE 2,SM1P5", "LTEBR 1,2")
        + cc_into(8)
        + lines("LD 4,DSNAN", "LTDBR 3,4", "LGDR 2,3")
        + cc_into(9)
        + lines("LZXR 12", "LTXBR 8,12", "LGDR 3,8", "LGDR 4,10"),
        {8: cc_word(1), 2: 0x7FF80000_00000009, 9: cc_word(3), 3: 0, 4: 0},
        0,
        INVALID_FLAG,
    ),
    "LCEBR LCDBR LCXBR": case_of(
        zeroed_short(1, 2)
        + lines("LE 2,S1", "LCEBR 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("LD 4,DSNAN", "LCDBR 3,4", "LGDR 3,3")
        + cc_into(9)
        + extended_from(12, "X2")
        + lines("LCXBR 8,12", "LGDR 4,8", "LGDR 5,10"),
        {
            2: high_word(0xBF800000),
            8: cc_word(1),
            3: 0xFFF00000_00000009,
            9: cc_word(3),
            4: 0xC0000000_00000000,
            5: 0,
        },
        1,
    ),
    "LNEBR LNDBR LNXBR": case_of(
        zeroed_short(1, 2)
        + lines("LE 2,S1", "LNEBR 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("LD 4,D0", "LNDBR 3,4", "LGDR 3,3")
        + cc_into(9)
        + extended_from(12, "X2")
        + lines("LCXBR 12,12", "LNXBR 8,12", "LGDR 4,8"),
        {
            2: high_word(0xBF800000),
            8: cc_word(1),
            3: 0x80000000_00000000,
            9: cc_word(0),
            4: 0xC0000000_00000000,
        },
        1,
    ),
    "LPEBR LPDBR LPXBR": case_of(
        zeroed_short(1, 2)
        + lines("LE 2,SM1P5", "LPEBR 1,2", "LGDR 2,1")
        + cc_into(8)
        + lines("LD 4,DMINF", "LPDBR 3,4", "LGDR 3,3")
        + cc_into(9)
        + lines("LZXR 12", "LCXBR 12,12", "LPXBR 8,12", "LGDR 4,8"),
        {
            2: high_word(0x3FC00000),
            8: cc_word(2),
            3: 0x7FF00000_00000000,
            9: cc_word(2),
            4: 0,
        },
        0,
    ),
}

CASES: Mapping[str, Case] = {
    "FIDBRA inexact control under an enabled mask": case_of(
        set_fpc(0x08000000) + lines("LD 2,D2P5", "FIDBRA 1,4,2,4", "LGDR 2,1"),
        {2: 0x40000000_00000000},
        PRESET_CC,
        0x08000000,
    ),
    **ADD_SUBTRACT,
    **MULTIPLY_DIVIDE,
    **ROOTS_FUSED,
    **COMPARES,
    **INTEGRAL,
    **SIGN_FORMS,
}


def trap_of(body: str, fprs: Mapping[int, int], fpc: int, cc: int = PRESET_CC) -> Trap:
    return (set_fpc(fpc & 0xFF000000) + PRESET + body, fprs, cc, fpc)


TRAPS: Mapping[str, Trap] = {
    "invalid suppresses": trap_of(
        lines("LD 1,D7", "LD 2,DM1", "SQDBR 1,2"), {1: 0x401C0000_00000000}, 0x80008000
    ),
    "division by zero suppresses": trap_of(
        lines("LD 1,D1", "LD 2,D0", "DDBR 1,2"), {1: 0x3FF00000_00000000}, 0x40004000
    ),
    "overflow delivers the scaled result": trap_of(
        lines("LD 1,DMAX", "LD 2,D2", "MDBR 1,2"), {1: 0x1FFFFFFF_FFFFFFFF}, 0x20002000
    ),
    "underflow delivers the scaled result": trap_of(
        lines("LD 1,DNMIN", "LD 2,DHALF", "MDBR 1,2"),
        {1: 0x60000000_00000000},
        0x10001000,
    ),
    "add overflow sets the cc from the scaled result": trap_of(
        zeroed_short(1) + lines("LE 1,SMAX", "AEBR 1,1"),
        {1: high_word(0x1FFFFFFF)},
        0x20002000,
        2,
    ),
    "inexact traps after the store": trap_of(
        lines("LD 1,D1", "LD 2,D3", "DDBR 1,2"), {1: 0x3FD55555_55555555}, 0x08000800
    ),
    "inexact traps with the masked overflow flagged": trap_of(
        lines("LD 1,DMAX", "LD 2,D2", "MDBR 1,2"), {1: 0x7FF00000_00000000}, 0x08200C00
    ),
    "compare and signal traps on a QNaN": trap_of(
        lines("LD 1,D1", "LD 2,DQNAN", "KDBR 1,2"),
        {1: 0x3FF00000_00000000},
        0x80008000,
    ),
    "load and test traps on an SNaN": trap_of(
        lines("LD 1,D7", "LD 2,DSNAN", "LTDBR 1,2"),
        {1: 0x401C0000_00000000},
        0x80008000,
    ),
    "load FP integer traps inexact": trap_of(
        lines("LD 2,D2P5", "FIDBR 1,4,2"), {1: 0x40000000_00000000}, 0x08000800
    ),
    "divide to integer suppresses an invalid operand": trap_of(
        lines("LD 1,DINF", "LD 2,D1", "LD 3,D7", "DIDBR 1,3,2,4"),
        {1: 0x7FF00000_00000000, 3: 0x401C0000_00000000},
        0x80008000,
    ),
    "divide to integer scales a tiny final remainder": trap_of(
        zeroed_short(1, 2, 3) + lines("LE 1,STINY3", "LE 2,STINY2", "DIEBR 1,3,2,4"),
        {1: high_word(0xD5000000), 3: high_word(0x40000000)},
        0x10001000,
        0,
    ),
}


def expected(case: str) -> HlasmMachine:
    registers, cc, abend = CASES[case][1:4]
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)


def expected_trap(case: str) -> tuple[HlasmRun, int, Mapping[int, int], int]:
    fprs, cc, fpc = TRAPS[case][1:]
    return HlasmRun(return_code=0, abend=DATA_EXCEPTION, stdout=""), cc, fprs, fpc
