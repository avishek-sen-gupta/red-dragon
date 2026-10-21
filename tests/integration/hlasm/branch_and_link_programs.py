# pyright: standard
"""Branch and link programs: R2 records the path, R5 the link, R6 the BSM mode bit; shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.load_store_programs import DATA, FILL, HIGH_FILL

type LinkCase = tuple[str, bool]
type ModeCase = tuple[str, bool, int, int]

TAKEN = HIGH_FILL | 1
FELL_THROUGH = HIGH_FILL | 2
PATH_REGISTER = 2
LINK_REGISTER = 5
MODE_REGISTER = 6
NEXT_REGISTER = 7
LOW_WORD = 0xFFFFFFFF
PRESET_CC = 2
AMODE_31_LINK = HIGH_FILL | 0x80000000
MODE_BIT_SET = HIGH_FILL | 0x80000007
LINK_VIEW = (PATH_REGISTER, LINK_REGISTER)
MODE_VIEW = (PATH_REGISTER, MODE_REGISTER)

TARGETS = (
    "SUB      LHI   2,1\n"
    "         ABEND 1\n"
    "MODESUB  TAM\n"
    "         LHI   2,1\n"
    "         ABEND 1\n"
    "         DS    0F\n"
    "ASUB     DC    A(X'80000000'+SUB)\n"
    "A24SUB   DC    A(MODESUB)\n"
    "A31SUB   DC    A(X'80000000'+MODESUB)\n"
    "A64SUB   DC    A(MODESUB+1)\n"
    "ANEXT    DC    A(X'80000000'+NEXT)\n"
)


def path(taken: bool) -> int:
    return TAKEN if taken else FELL_THROUGH


def program(code: str) -> str:
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         LMG   2,11,FILL\n"
        "         LA    7,NEXT\n"
        "         CLI   NEG,0\n"
        f"{code}"
        "NEXT     LHI   2,2\n"
        "         ABEND 1\n"
        f"{TARGETS}{DATA}"
        "         END\n"
    )


def link_view(machine: HlasmMachine) -> HlasmMachine:
    gprs = machine.gprs
    return HlasmMachine(
        machine.run,
        machine.cc,
        {
            PATH_REGISTER: gprs[PATH_REGISTER],
            LINK_REGISTER: gprs[LINK_REGISTER] - (gprs[NEXT_REGISTER] & LOW_WORD),
        },
    )


def _line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<5} {operands}\n"


TARGET_IN_R4 = _line("LA", "4,SUB")
AMODE_31_TARGET_IN_R4 = _line("L", "4,ASUB")

LINK_CASES: Mapping[str, LinkCase] = {
    "BAL": (_line("BAL", "5,SUB"), True),
    "BAL indexed": (_line("LA", "6,4") + _line("BAL", "5,SUB-4(6)"), True),
    "BALR": (TARGET_IN_R4 + _line("BALR", "5,4"), True),
    "BALR 5,0": (_line("BALR", "5,0"), False),
    "BAS": (_line("BAS", "5,SUB"), True),
    "BASR": (TARGET_IN_R4 + _line("BASR", "5,4"), True),
    "BASR 5,0": (_line("BASR", "5,0"), False),
    "BRAS": (_line("BRAS", "5,SUB"), True),
    "JAS": (_line("JAS", "5,SUB"), True),
    "BRASL": (_line("BRASL", "5,SUB"), True),
    "JASL": (_line("JASL", "5,SUB"), True),
    "BASSM": (AMODE_31_TARGET_IN_R4 + _line("BASSM", "5,4"), True),
    "BASSM 5,0": (_line("BASSM", "5,0"), False),
    "BASSM 5,5": (_line("L", "5,ASUB") + _line("BASSM", "5,5"), True),
    "BSM 5,5": (_line("L", "5,ANEXT") + _line("BSM", "5,5"), False),
}

PRESET_R6 = _line("LHI", "6,7")

MODE_CASES: Mapping[str, ModeCase] = {
    "BSM": (
        PRESET_R6 + AMODE_31_TARGET_IN_R4 + _line("BSM", "6,4"),
        True,
        PRESET_CC,
        MODE_BIT_SET,
    ),
    "BSM 0,4": (AMODE_31_TARGET_IN_R4 + _line("BSM", "0,4"), True, PRESET_CC, FILL),
    "BSM 6,0": (PRESET_R6 + _line("BSM", "6,0"), False, PRESET_CC, MODE_BIT_SET),
    "BSM 0,0": (_line("BSM", "0,0"), False, PRESET_CC, FILL),
    "SAM31": (_line("SAM31", ""), False, PRESET_CC, FILL),
    "TAM": (_line("TAM", ""), False, 1, FILL),
    "BASSM into AMODE 31 then TAM": (
        _line("L", "4,A31SUB") + _line("BASSM", "5,4"),
        True,
        1,
        FILL,
    ),
}

AMODE_24_CC = 0
AMODE_64_CC = 3

MODE_SWITCH_CASES: Mapping[str, ModeCase] = {
    "SAM24 then TAM": (
        _line("SAM24", "") + _line("TAM", ""),
        False,
        AMODE_24_CC,
        FILL,
    ),
    "SAM64 then TAM": (
        _line("SAM64", "") + _line("TAM", ""),
        False,
        AMODE_64_CC,
        FILL,
    ),
    "BSM into AMODE 24": (
        _line("L", "4,A24SUB") + _line("BSM", "0,4"),
        True,
        AMODE_24_CC,
        FILL,
    ),
    "BSM into AMODE 64": (
        _line("L", "4,A64SUB") + _line("BSM", "0,4"),
        True,
        AMODE_64_CC,
        FILL,
    ),
    "BASSM into AMODE 24": (
        _line("L", "4,A24SUB") + _line("BASSM", "5,4"),
        True,
        AMODE_24_CC,
        FILL,
    ),
    "BASSM into AMODE 64": (
        _line("L", "4,A64SUB") + _line("BASSM", "5,4"),
        True,
        AMODE_64_CC,
        FILL,
    ),
}

RETURN_CODE = 7
CALLER_RETURNS: Mapping[str, str] = {
    "BSM 0,14": _line("BSM", "0,14"),
    "BASSM 14,14": _line("BASSM", "14,14"),
}


def return_program(code: str) -> str:
    return f"T        CSECT\n{_line('LHI', f'15,{RETURN_CODE}')}{code}         END\n"
