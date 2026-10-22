# pyright: standard
"""Execute programs: R8 records the path, R5 a link, R3 a moved doubleword; shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import DATA, HIGH_FILL

type ExecuteCase = tuple[str, HlasmRun, int, Mapping[int, int]]

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
OPERATION = HlasmRun(return_code=0, abend="S0C1", stdout="")
EXECUTE = HlasmRun(return_code=0, abend="S0C3", stdout="")
SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")
USER_5 = HlasmRun(return_code=0, abend="U0005", stdout="")

PRESET_CC = 3
PATH_REGISTER = 8
MOVED_REGISTER = 3
LINK_REGISTER = 5
NEXT_REGISTER = 9
LOW_WORD = 0xFFFFFFFF
BRANCHED = HIGH_FILL | 1
FELL_THROUGH = HIGH_FILL | 2
AMODE_31_LINK = HIGH_FILL | 0x80000000

TARGETS = (
    "MOVE     MVC   0(0,6),0(7)\n"
    "COMPARE  CLI   SRC+4,X'08'\n"
    "SVCI     SVC   0\n"
    "CALL     BAL   0,SUB\n"
    "ADD      AR    0,0\n"
    "JUMP     J     SUB\n"
    "JUMPNOP  JNOP  SUB\n"
    "CALLR    BRAS  5,SUB\n"
    "LOADI    LHI   0,5\n"
    "INNER    EX    0,MOVE\n"
    "COMPAREJ CIJ   3,7,0,SUB\n"
    "INNERRL  EXRL  0,MOVE\n"
    "COMPAREC CLC   0(0,7),SAME\n"
    "EXCLUDE  XC    0(0,6),0(7)\n"
    "XLATE    TR    0(0,6),0(7)\n"
    "SCAN     TRT   0(0,6),FUNCS\n"
    "NUMERICS MVN   0(0,6),0(7)\n"
    "ZONES    MVZ   0(0,6),0(7)\n"
    "INVERSE  MVCIN 0(0,6),7(7)\n"
    "OFFSET   MVO   0(0,6),0(0,7)\n"
    "STORE    MVI   0(6),X'00'\n"
    "TEST     TM    SRC+1,X'00'\n"
    "ANDI     NI    0(6),X'00'\n"
    "ORI      OI    0(6),X'00'\n"
    "XORI     XI    0(6),X'00'\n"
    "ADDI     ASI   OUT,0\n"
    "ADDLI    ALSI  OUT,0\n"
    "ADDGI    AGSI  OUT,0\n"
    "COMPAREY CLIY  SRC+1,X'00'\n"
    "STOREY   MVIY  OUT,X'00'\n"
    "ANDY     NIY   OUT,X'00'\n"
    "ANDC     NC    0(0,6),0(7)\n"
    "ORC      OC    0(0,6),0(7)\n"
    "SCANR    TRTR  3(0,6),FUNCS\n"
    "SPREAD   MVC   1(0,6),0(6)\n"
    "BLOCKS   CLC   LOWHIGH(0),HIGHLOW\n"
    "BRANCH   BC    0,SUB-4\n"
    "SUB      LHI   8,1\n"
    "         ABEND 1\n"
    "BIGSRC   DC    256X'5A'\n"
    "BIGOUT   DC    264X'FF'\n"
    "SAME     DC    X'0123456789000000'\n"
    "CODES    DC    X'0706050403020100'\n"
    "FUNCS    DC    X'00000000C1000000'\n"
    "LOWHIGH  DC    X'00000001FFFF'\n"
    "HIGHLOW  DC    X'000000020000'\n"
)


def program(code: str) -> str:
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         LMG   2,11,FILL\n"
        "         LA    6,OUT\n"
        "         LA    7,SRC\n"
        "         TM    FILL,X'A5'\n"
        f"{code}"
        "NEXT     LHI   8,2\n"
        "         ABEND 1\n"
        f"{TARGETS}{DATA}"
        "         END\n"
    )


def _line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<5} {operands}\n"


def view(machine: HlasmMachine, registers: Mapping[int, int]) -> HlasmMachine:
    gprs = machine.gprs
    relative = {LINK_REGISTER: gprs[LINK_REGISTER] - (gprs[NEXT_REGISTER] & LOW_WORD)}
    return HlasmMachine(
        machine.run,
        machine.cc,
        {r: relative.get(r, gprs[r]) for r in registers},
    )


MOVED = _line("LG", f"{MOVED_REGISTER},OUT")
AT_NEXT = _line("LA", f"{NEXT_REGISTER},NEXT")


def _move(length_code: int) -> str:
    return _line("LHI", f"2,{length_code}") + _line("EX", "2,MOVE") + MOVED


def _executed(field: str, target: str) -> str:
    return _line("LHI", f"2,{field}") + _line("EX", f"2,{target}")


def _on_codes(field: str, target: str) -> str:
    return _line("MVC", "OUT(8),CODES") + _executed(field, target) + MOVED


def _moved(field: str, target: str) -> str:
    return _executed(field, target) + MOVED


CASES: Mapping[str, ExecuteCase] = {
    "MVC length from bits 56-63 only": (
        _move(0x104),
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0x0123456789FFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "MVC length code 0": (
        _move(0),
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0x01FFFFFFFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "MVC length code 4": (
        _move(4),
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0x0123456789FFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "MVC length code 255 moves 256 bytes": (
        _line("LA", "6,BIGOUT")
        + _line("LA", "7,BIGSRC")
        + _line("LHI", "2,255")
        + _line("EX", "2,MOVE")
        + _line("LG", f"{MOVED_REGISTER},BIGOUT+252"),
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0x5A5A5A5AFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "BC mask and index from a register": (
        _line("LHI", "4,4") + _line("LHI", "2,X'F4'") + _line("EX", "2,BRANCH"),
        ABENDED,
        PRESET_CC,
        {PATH_REGISTER: BRANCHED},
    ),
    "BC unchanged": (
        _line("EX", "0,BRANCH"),
        ABENDED,
        PRESET_CC,
        {PATH_REGISTER: FELL_THROUGH},
    ),
    "MVC length code 7": (
        _move(7),
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0x0123456789ABCDEF, PATH_REGISTER: FELL_THROUGH},
    ),
    "R1 0 ignores GR0": (
        _line("LHI", "0,7") + _line("EX", "0,MOVE") + MOVED,
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0x01FFFFFFFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "CLI immediate ORed equal": (
        _line("LHI", "2,X'81'") + _line("EX", "2,COMPARE"),
        ABENDED,
        0,
        {PATH_REGISTER: FELL_THROUGH},
    ),
    "CLI immediate ORed low": (
        _line("LHI", "2,X'F0'") + _line("EX", "2,COMPARE"),
        ABENDED,
        1,
        {PATH_REGISTER: FELL_THROUGH},
    ),
    "CLI immediate unchanged high": (
        _line("EX", "0,COMPARE"),
        ABENDED,
        2,
        {PATH_REGISTER: FELL_THROUGH},
    ),
    "SVC number from a register": (
        _line("LA", "1,5") + _line("LHI", "2,13") + _line("EX", "2,SVCI"),
        USER_5,
        PRESET_CC,
        {},
    ),
    "BAL R1 from a register links after the EX": (
        AT_NEXT + _line("LHI", "4,X'50'") + _line("EX", "4,CALL"),
        ABENDED,
        PRESET_CC,
        {LINK_REGISTER: AMODE_31_LINK, PATH_REGISTER: BRANCHED},
    ),
    "AR R1 and R2 from a register": (
        _line("LHI", "3,5")
        + _line("LHI", "4,7")
        + _line("LHI", "2,X'34'")
        + _line("EX", "2,ADD"),
        ABENDED,
        2,
        {3: HIGH_FILL | 12, 4: HIGH_FILL | 7, PATH_REGISTER: FELL_THROUGH},
    ),
    "LHI R1 from a register": (
        _line("LHI", "2,X'70'") + _line("EX", "2,LOADI"),
        ABENDED,
        PRESET_CC,
        {7: HIGH_FILL | 5, PATH_REGISTER: FELL_THROUGH},
    ),
    "EXRL relative branch": (
        _line("EXRL", "0,JUMP"),
        ABENDED,
        PRESET_CC,
        {PATH_REGISTER: BRANCHED},
    ),
    "EXRL branch mask from a register": (
        _line("LHI", "2,X'F0'") + _line("EXRL", "2,JUMPNOP"),
        ABENDED,
        PRESET_CC,
        {PATH_REGISTER: BRANCHED},
    ),
    "EXRL branch mask unchanged": (
        _line("EXRL", "0,JUMPNOP"),
        ABENDED,
        PRESET_CC,
        {PATH_REGISTER: FELL_THROUGH},
    ),
    "EXRL of CIJ, mask from a register": (
        _line("LHI", "3,7") + _line("LHI", "2,X'08'") + _line("EXRL", "2,COMPAREJ"),
        ABENDED,
        PRESET_CC,
        {PATH_REGISTER: BRANCHED},
    ),
    "EXRL of CIJ, mask unchanged": (
        _line("LHI", "3,7") + _line("EXRL", "0,COMPAREJ"),
        ABENDED,
        PRESET_CC,
        {PATH_REGISTER: FELL_THROUGH},
    ),
    "EXRL BRAS links after the EXRL": (
        AT_NEXT + _line("EXRL", "0,CALLR"),
        ABENDED,
        PRESET_CC,
        {LINK_REGISTER: AMODE_31_LINK, PATH_REGISTER: BRANCHED},
    ),
    "CLC length from a register, equal": (
        _executed("4", "COMPAREC"),
        ABENDED,
        0,
        {PATH_REGISTER: FELL_THROUGH},
    ),
    "CLC length from a register, high": (
        _executed("5", "COMPAREC"),
        ABENDED,
        2,
        {PATH_REGISTER: FELL_THROUGH},
    ),
    "CLC length from a register, low in the first block": (
        _executed("5", "BLOCKS"),
        ABENDED,
        1,
        {PATH_REGISTER: FELL_THROUGH},
    ),
    "XC length from a register": (
        _moved("3", "EXCLUDE"),
        ABENDED,
        1,
        {MOVED_REGISTER: 0xFEDCBA98FFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "TR length from a register": (
        _on_codes("3", "XLATE"),
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0xEFCDAB8903020100, PATH_REGISTER: FELL_THROUGH},
    ),
    "TRT length from a register": (
        _on_codes("3", "SCAN"),
        ABENDED,
        2,
        {2: HIGH_FILL | 0xC1, PATH_REGISTER: FELL_THROUGH},
    ),
    "MVN length from a register": (
        _moved("2", "NUMERICS"),
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0xF1F3F5FFFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "MVZ length from a register": (
        _moved("2", "ZONES"),
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0x0F2F4FFFFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "MVCIN length from a register": (
        _moved("3", "INVERSE"),
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0xEFCDAB89FFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "MVO lengths from a register": (
        _moved("X'31'", "OFFSET"),
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0x0000123FFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "MVI immediate from a register": (
        _moved("X'5A'", "STORE"),
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0x5AFFFFFFFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "TM mask from a register": (
        _executed("X'30'", "TEST"),
        ABENDED,
        1,
        {PATH_REGISTER: FELL_THROUGH},
    ),
    "NI immediate from a register": (
        _moved("X'3C'", "ANDI"),
        ABENDED,
        1,
        {MOVED_REGISTER: 0x3CFFFFFFFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "OI immediate from a register": (
        _line("XC", "OUT(8),OUT") + _moved("X'81'", "ORI"),
        ABENDED,
        1,
        {MOVED_REGISTER: 0x8100000000000000, PATH_REGISTER: FELL_THROUGH},
    ),
    "XI immediate from a register": (
        _moved("X'0F'", "XORI"),
        ABENDED,
        1,
        {MOVED_REGISTER: 0xF0FFFFFFFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "ASI negative immediate from a register": (
        _moved("X'FE'", "ADDI"),
        ABENDED,
        1,
        {MOVED_REGISTER: 0xFFFFFFFDFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "ALSI negative immediate from a register": (
        _moved("X'80'", "ADDLI"),
        ABENDED,
        3,
        {MOVED_REGISTER: 0xFFFFFF7FFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "AGSI negative immediate from a register": (
        _moved("X'80'", "ADDGI"),
        ABENDED,
        1,
        {MOVED_REGISTER: 0xFFFFFFFFFFFFFF7F, PATH_REGISTER: FELL_THROUGH},
    ),
    "CLIY immediate from a register": (
        _executed("X'23'", "COMPAREY"),
        ABENDED,
        0,
        {PATH_REGISTER: FELL_THROUGH},
    ),
    "MVIY immediate from a register": (
        _moved("X'5A'", "STOREY"),
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0x5AFFFFFFFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "NIY immediate from a register": (
        _moved("X'0F'", "ANDY"),
        ABENDED,
        1,
        {MOVED_REGISTER: 0x0FFFFFFFFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "NC length from a register": (
        _moved("1", "ANDC"),
        ABENDED,
        1,
        {MOVED_REGISTER: 0x0123FFFFFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
    ),
    "OC length from a register": (
        _line("XC", "OUT(8),OUT") + _moved("2", "ORC"),
        ABENDED,
        1,
        {MOVED_REGISTER: 0x0123450000000000, PATH_REGISTER: FELL_THROUGH},
    ),
    "TRTR length from a register": (
        _on_codes("3", "SCANR"),
        ABENDED,
        1,
        {2: HIGH_FILL | 0xC1, PATH_REGISTER: FELL_THROUGH},
    ),
    "MVC destructive overlap, length from a register": (
        _on_codes("6", "SPREAD"),
        ABENDED,
        PRESET_CC,
        {MOVED_REGISTER: 0x0707070707070707, PATH_REGISTER: FELL_THROUGH},
    ),
    "EX of EX": (_line("EX", "0,INNER"), EXECUTE, PRESET_CC, {}),
    "EX of EXRL": (_line("EX", "0,INNERRL"), EXECUTE, PRESET_CC, {}),
    "EXRL of EX": (_line("EXRL", "0,INNER"), EXECUTE, PRESET_CC, {}),
    "EX odd target": (_line("EX", "0,MOVE+1"), SPECIFICATION, PRESET_CC, {}),
}

INDEXED_TARGET: ExecuteCase = (
    _line("LHI", "4,0") + _line("EX", "0,MOVE(4)") + MOVED,
    ABENDED,
    PRESET_CC,
    {MOVED_REGISTER: 0x01FFFFFFFFFFFFFF, PATH_REGISTER: FELL_THROUGH},
)

MODIFIED_OPCODE: ExecuteCase = (
    _line("LHI", "2,X'01'") + _line("EX", "2,LOADI"),
    ABENDED,
    PRESET_CC,
    {0: 5, PATH_REGISTER: FELL_THROUGH},
)
