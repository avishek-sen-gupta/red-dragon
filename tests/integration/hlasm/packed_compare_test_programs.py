# pyright: standard
"""Packed-decimal compare and test programs, shared by the VM tests and the z390 differential tests; each leaves only a CC or an abend."""

from collections.abc import Mapping

from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import ABEND
from tests.integration.hlasm.packed_arithmetic_programs import (
    ABENDED,
    CC_HIGH,
    CC_LOW,
    CC_ZERO,
    DATA_EXCEPTION,
)

type Case = tuple[str, int]

CC_SIGN_INVALID = 1
CC_DIGIT_INVALID = 2
CC_BOTH_INVALID = 3
CC_SET_BY_TM = 3

SET_CC = "         TM    ONES,X'FF'\n"

DATA_SPAN = (0x400, 0x470)
SECTION = "T"

DATA = (
    "         ORG   T+X'400'\n"
    "ONES     DC    X'FF'\n"
    "P5       DC    PL3'12345'\n"
    "P5L      DC    PL8'12345'\n"
    "M5       DC    PL3'-12345'\n"
    "M1       DC    PL1'-1'\n"
    "ALTP     DC    X'12345F'\n"
    "ALTM     DC    X'12345B'\n"
    "NZ       DC    X'0D'\n"
    "NZB      DC    X'0B'\n"
    "SIGNS    DC    X'1A1B1E'\n"
    "PZ       DC    PL4'0'\n"
    "AZ       DC    X'000A'\n"
    "N31      DC    PL16'9999999999999999999999999999999'\n"
    "N31B     DC    PL16'9999999999999999999999999999998'\n"
    "M31      DC    PL16'-9999999999999999999999999999999'\n"
    "ONE      DC    PL1'1'\n"
    "BADD     DC    X'1A3C'\n"
    "BADS     DC    X'1234'\n"
    "BADB     DC    X'1A34'\n"
    "BADH     DC    X'00FC'\n"
    "BAD1     DC    X'A9'\n"
    "BADL     DC    X'A0',XL14'00',X'0C'\n"
    "CPX      CP    P5(1),P5L(1)\n"
    "TPX      TP    P5(1)\n"
)


def compare_test_program(body: str) -> str:
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        f"{body}{ABEND}{DATA}"
        "         END\n"
    )


def _line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<6}{operands}\n"


def _executed(fields: str, target: str) -> str:
    return _line("LA", f"1,X'{fields}'") + _line("EX", f"1,{target}")


COMPARES: Mapping[str, Case] = {
    "CP equal values of different lengths": (_line("CP", "P5,P5L"), CC_ZERO),
    "CP the longer operand first": (_line("CP", "P5L,P5"), CC_ZERO),
    "CP negative zero against positive zero": (_line("CP", "NZ,PZ"), CC_ZERO),
    "CP alternate plus sign": (_line("CP", "ALTP,P5"), CC_ZERO),
    "CP alternate minus sign": (_line("CP", "M5,ALTM"), CC_ZERO),
    "CP alternate plus zero against negative zero": (_line("CP", "AZ,NZ"), CC_ZERO),
    "CP alternate minus zero against positive zero": (_line("CP", "NZB,PZ"), CC_ZERO),
    "CP first low": (_line("CP", "M5,P5"), CC_LOW),
    "CP first high": (_line("CP", "P5,M5"), CC_HIGH),
    "CP larger negative magnitude is low": (_line("CP", "M5,M1"), CC_LOW),
    "CP 31 digits high": (_line("CP", "N31,N31B"), CC_HIGH),
    "CP 31 digits negative against one": (_line("CP", "M31,ONE"), CC_LOW),
    "EX of CP sets both lengths": (SET_CC + _executed("27", "CPX"), CC_ZERO),
}

TESTS: Mapping[str, Case] = {
    "TP valid": (_line("TP", "P5"), CC_ZERO),
    "TP valid with sign F": (_line("TP", "ALTP"), CC_ZERO),
    "TP valid with sign A": (_line("TP", "SIGNS(1)"), CC_ZERO),
    "TP valid with sign B": (_line("TP", "SIGNS+1(1)"), CC_ZERO),
    "TP valid with sign E": (_line("TP", "SIGNS+2(1)"), CC_ZERO),
    "TP sign invalid": (_line("TP", "BADS"), CC_SIGN_INVALID),
    "TP digit invalid": (_line("TP", "BADD"), CC_DIGIT_INVALID),
    "TP digit beside the sign invalid": (_line("TP", "BADH"), CC_DIGIT_INVALID),
    "TP digit and sign invalid": (_line("TP", "BADB"), CC_BOTH_INVALID),
    "TP one byte": (_line("TP", "NZ"), CC_ZERO),
    "TP one byte both invalid": (_line("TP", "BAD1"), CC_BOTH_INVALID),
    "TP 16 bytes": (_line("TP", "N31"), CC_ZERO),
    "TP 16 bytes leftmost digit invalid": (_line("TP", "BADL(16)"), CC_DIGIT_INVALID),
    "TP short of the sign": (_line("TP", "P5(1)"), CC_SIGN_INVALID),
    "EX of TP sets the length": (_executed("20", "TPX"), CC_ZERO),
    "EX of TP ignores bits 12-15": (_executed("2F", "TPX"), CC_ZERO),
}

DATA_EXCEPTIONS: Mapping[str, Case] = {
    "CP invalid digit in the first operand": (
        SET_CC + _line("CP", "BADD,P5"),
        CC_SET_BY_TM,
    ),
    "CP invalid sign in the second operand": (
        SET_CC + _line("CP", "P5,BADS"),
        CC_SET_BY_TM,
    ),
    "CP invalid sign in the first operand": (
        SET_CC + _line("CP", "BADS,P5"),
        CC_SET_BY_TM,
    ),
    "CP invalid digit in the second operand": (
        SET_CC + _line("CP", "P5,BADD"),
        CC_SET_BY_TM,
    ),
    "CP invalid operands that are equal": (
        SET_CC + _line("CP", "BADS,BADS"),
        CC_SET_BY_TM,
    ),
    "EX of CP with a length short of the sign": (
        SET_CC + _executed("02", "CPX"),
        CC_SET_BY_TM,
    ),
}

ALL_CASES: Mapping[str, tuple[Case, HlasmRun]] = {
    **{name: (case, ABENDED) for name, case in COMPARES.items()},
    **{name: (case, ABENDED) for name, case in TESTS.items()},
    **{name: (case, DATA_EXCEPTION) for name, case in DATA_EXCEPTIONS.items()},
}
