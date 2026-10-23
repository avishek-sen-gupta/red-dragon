# pyright: standard
"""BFP conversion programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; results come back in GRs (FPRs through LGDR), intermediate CCs through IPM, and every program first clears the FPC."""

from collections.abc import Mapping

from tests.integration.hlasm.bfp_arithmetic_programs import (
    DATA,
    DATA_EXCEPTION,
    INEXACT_FLAG,
    INVALID_FLAG,
    PRESET_CC,
    Case,
    case_of,
    cc_into,
    cc_word,
    extended_from,
    lines,
    set_fpc,
)
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import (
    ABEND,
    FILL,
    HIGH_FILL,
    based_program,
)

BOTH_FLAGS = INVALID_FLAG | INEXACT_FLAG

CONVERSION_DATA = (
    "         DS    0D\n"
    "DMPH     DC    X'41DFFFFFFFE00000'\n"
    "DU32     DC    X'41EFFFFFFFE00000'\n"
    "D3P5     DC    X'400C000000000000'\n"
    "XM0      DC    X'80000000000000000000000000000000'\n"
    "XM1      DC    X'BFFF0000000000000000000000000000'\n"
    "XQNAN    DC    X'7FFF8000000000000000000000000000'\n"
    "XMINF    DC    X'FFFF0000000000000000000000000000'\n"
    "S2P63    DC    X'5F000000'\n"
    "SM2P63   DC    X'DF000000'\n"
    "S2P64    DC    X'5F800000'\n"
    "SMHALF   DC    X'BF000000'\n"
)


def program(body: str) -> str:
    return based_program(body, ABEND + DATA + CONVERSION_DATA)


def _low(value: int) -> int:
    return HIGH_FILL | value


def _trapped(body: str, registers: Mapping[int, int], cc: int, fpc: int) -> Case:
    trapping = set_fpc(fpc & 0xFF000000) + body
    return (*case_of(trapping, registers, cc)[:3], DATA_EXCEPTION, fpc)


TO_FIXED: Mapping[str, Case] = {
    "CFEBR CFEBRA": case_of(
        lines("LE 1,SM2P5", "CFEBR 2,0,1") + cc_into(8) + lines("CFEBRA 3,1,1,4"),
        {2: _low(0xFFFFFFFE), 8: cc_word(1), 3: _low(0xFFFFFFFD)},
        1,
        INEXACT_FLAG,
    ),
    "CFDBR CFDBRA": case_of(
        lines("LD 1,DMPH", "CFDBR 2,0,1") + cc_into(8) + lines("CFDBRA 3,5,1,0"),
        {2: _low(0x7FFFFFFF), 8: cc_word(3), 3: _low(0x7FFFFFFF)},
        2,
        BOTH_FLAGS,
    ),
    "CFXBR CFXBRA": case_of(
        extended_from(4, "XM0")
        + lines("CFXBR 2,0,4")
        + cc_into(8)
        + extended_from(4, "XQNAN")
        + lines("CFXBRA 3,0,4,4"),
        {2: _low(0), 8: cc_word(0), 3: _low(0x80000000)},
        3,
        INVALID_FLAG,
    ),
    "CGEBR CGEBRA": case_of(
        lines("LE 1,S2P63", "CGEBR 2,0,1")
        + cc_into(8)
        + lines("LE 1,SM2P63", "CGEBRA 3,0,1,0"),
        {2: 0x7FFFFFFF_FFFFFFFF, 8: cc_word(3), 3: 0x80000000_00000000},
        1,
        BOTH_FLAGS,
    ),
    "CGDBR CGDBRA in the current mode": case_of(
        set_fpc(1)
        + lines("LD 1,D3P5", "CGDBR 2,0,1")
        + cc_into(8)
        + lines("CGDBR 4,4,1", "LD 1,DM1", "CGDBRA 3,6,1,0"),
        {2: 3, 8: cc_word(2), 4: 4, 3: 0xFFFFFFFF_FFFFFFFF},
        1,
        INEXACT_FLAG | 1,
    ),
    "CGXBR CGXBRA": case_of(
        extended_from(4, "X3")
        + lines("CGXBR 2,0,4")
        + cc_into(8)
        + extended_from(4, "XMINF")
        + lines("CGXBRA 3,0,4,0"),
        {2: 3, 8: cc_word(2), 3: 0x80000000_00000000},
        3,
        BOTH_FLAGS,
    ),
    "CLFEBR": case_of(
        lines("LE 1,SMHALF", "CLFEBR 2,5,1,0")
        + cc_into(8)
        + lines("LE 1,S2P63", "CLFEBR 3,0,1,0"),
        {2: _low(0), 8: cc_word(1), 3: _low(0xFFFFFFFF)},
        3,
        BOTH_FLAGS,
    ),
    "CLFDBR": case_of(
        lines("LD 1,DU32", "CLFDBR 2,0,1,0")
        + cc_into(8)
        + lines("LD 1,DM1", "CLFDBR 3,0,1,4"),
        {2: _low(0xFFFFFFFF), 8: cc_word(2), 3: _low(0)},
        3,
        INVALID_FLAG,
    ),
    "CLFXBR": case_of(
        extended_from(4, "X3")
        + lines("CLFXBR 2,0,4,0")
        + cc_into(8)
        + extended_from(4, "XM1")
        + lines("CLFXBR 3,0,4,0"),
        {2: _low(3), 8: cc_word(2), 3: _low(0)},
        3,
        BOTH_FLAGS,
    ),
    "CLGEBR": case_of(
        lines("LE 1,S2P64", "CLGEBR 2,0,1,0")
        + cc_into(8)
        + lines("LE 1,S2P63", "CLGEBR 3,0,1,0"),
        {2: 0xFFFFFFFF_FFFFFFFF, 8: cc_word(3), 3: 0x80000000_00000000},
        2,
        BOTH_FLAGS,
    ),
    "CLGDBR": case_of(
        lines("LD 1,DQNAN", "CLGDBR 2,0,1,0")
        + cc_into(8)
        + lines("LD 1,D7", "CLGDBR 3,0,1,0"),
        {2: 0, 8: cc_word(3), 3: 7},
        2,
        BOTH_FLAGS,
    ),
    "CLGXBR": case_of(
        extended_from(4, "XM0")
        + lines("CLGXBR 2,0,4,0")
        + cc_into(8)
        + extended_from(4, "X3")
        + lines("CLGXBR 3,7,4,0"),
        {2: 0, 8: cc_word(0), 3: 3},
        2,
    ),
    "CLFDBR inexact control under an enabled mask": case_of(
        set_fpc(0x08000000) + lines("LD 1,D3P5", "CLFDBR 2,0,1,4"),
        {2: _low(4)},
        2,
        0x08000000,
    ),
    "CFDBR invalid suppresses": _trapped(
        lines("LD 1,DQNAN", "CFDBR 2,0,1"), {2: FILL}, PRESET_CC, 0x80008000
    ),
    "CGDBR masked invalid takes the inexact trap after the store": _trapped(
        lines("LD 1,DQNAN", "CGDBR 2,0,1"),
        {2: 0x80000000_00000000},
        3,
        0x08800800,
    ),
    "CFDBR inexact traps after the store": _trapped(
        lines("LD 1,D3P5", "CFDBR 2,0,1"), {2: _low(4)}, 2, 0x08000C00
    ),
}

CASES: Mapping[str, Case] = {**TO_FIXED}


def expected(case: str) -> HlasmMachine:
    registers, cc, abend = CASES[case][1:4]
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)
