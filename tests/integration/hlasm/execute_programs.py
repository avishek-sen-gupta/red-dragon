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
    "INNERRL  EXRL  0,MOVE\n"
    "BRANCH   BC    0,SUB-4\n"
    "SUB      LHI   8,1\n"
    "         ABEND 1\n"
    "BIGSRC   DC    256X'5A'\n"
    "BIGOUT   DC    264X'FF'\n"
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
    "EXRL BRAS links after the EXRL": (
        AT_NEXT + _line("EXRL", "0,CALLR"),
        ABENDED,
        PRESET_CC,
        {LINK_REGISTER: AMODE_31_LINK, PATH_REGISTER: BRANCHED},
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
