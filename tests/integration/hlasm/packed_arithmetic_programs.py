# pyright: standard
"""Packed-decimal arithmetic programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; data sits at fixed offsets so stored fields can be read back."""

from collections.abc import Mapping

from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import ABEND

type Case = tuple[str, Mapping[int, int], int]
type Span = tuple[int, int]

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
DATA_EXCEPTION = HlasmRun(return_code=0, abend="S0C7", stdout="")
DECIMAL_OVERFLOW = HlasmRun(return_code=0, abend="S0CA", stdout="")
DECIMAL_DIVIDE = HlasmRun(return_code=0, abend="S0CB", stdout="")
SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")

CC_ZERO = 0
CC_LOW = 1
CC_HIGH = 2
CC_OVERFLOW = 3
CC_SET_BY_LTR = 1
CC_SET_BY_ZAP = 2
RESULT = 7

SET_CC = "         LTR   2,2\n"
MASK_OFF = "         LA    1,0\n" "         SPM   1\n"
W_SPAN = (0x480, 0x488)
V_SPAN = (0x48E, 0x490)
V3_SPAN = (0x495, 0x498)

DATA = (
    "         ORG   T+X'400'\n"
    "FILL     DC    10X'A5A5A5A5A5A5A5A5'\n"
    "         ORG   T+X'480'\n"
    "W        DC    PL8'0'\n"
    "VD       DC    XL6'00'\n"
    "V        DC    PL2'0'\n"
    "V3D      DC    XL5'00'\n"
    "V3       DC    PL3'0'\n"
    "ZOV      DC    X'12345C0000000000'\n"
    "ZOV2     DC    X'000000000012345C'\n"
    "OUTF     DC    2X'FFFFFFFFFFFFFFFF'\n"
    "P1       DC    PL3'12345'\n"
    "M1       DC    PL3'-12345'\n"
    "P2       DC    PL2'678'\n"
    "M2       DC    PL2'-678'\n"
    "ALTM     DC    X'678B'\n"
    "ALTF     DC    X'678F'\n"
    "BIGP     DC    PL2'999'\n"
    "BIGM     DC    PL2'-999'\n"
    "ONE      DC    PL1'1'\n"
    "NINE     DC    PL1'9'\n"
    "ZERO     DC    PL1'0'\n"
    "NZERO    DC    X'0D'\n"
    "M5       DC    PL1'-5'\n"
    "MDIV     DC    PL3'-1356'\n"
    "P8991    DC    PL3'8991'\n"
    "P9000    DC    PL3'9000'\n"
    "BADD     DC    X'1A3C'\n"
    "BADS     DC    X'1234'\n"
    "P100     DC    PL3'100'\n"
    "M100     DC    PL3'-100'\n"
    "A31      DC    PL16'4444444444444444444444444444444'\n"
    "N31      DC    PL16'9999999999999999999999999999999'\n"
    "A15      DC    PL8'123456789012345'\n"
    "M15      DC    PL8'-999999999999999'\n"
    "M29      DC    PL16'-77777777777777777777777777777'\n"
    "D15      DC    PL8'-987654321098765'\n"
    "W16      DC    PL16'0'\n"
    "APX      AP    W(1),P2(1)\n"
    "SRPX     SRP   W(1),63,0\n"
    "DPX      DP    W(2),M2(1)\n"
    "MPX      MP    W(2),P2(1)\n"
)


def packed_program(body: str) -> str:
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         LMG   2,11,FILL\n"
        f"{body}{ABEND}{DATA}"
        "         END\n"
    )


def _zap(field: str) -> str:
    return f"         ZAP   W(8),{field}\n"


def _line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<6}{operands}\n"


LOAD_W = _line("LG", "7,W")
LOAD_V = _line("LG", "7,VD")
LOAD_V3 = _line("LG", "7,V3D")
LOAD_W16 = _line("LMG", "6,7,W16")
HIGH_RESULT = 6


def _zap16(field: str) -> str:
    return f"         ZAP   W16(16),{field}\n"


def _wide(high: int, low: int) -> Mapping[int, int]:
    return {HIGH_RESULT: high, RESULT: low}


ADDS: Mapping[str, Case] = {
    "AP": (
        _zap("P1") + _line("AP", "W(8),P2") + LOAD_W,
        {RESULT: 0x00000000_0013023C},
        CC_HIGH,
    ),
    "AP negative sum": (
        _zap("P2") + _line("AP", "W(8),M1") + LOAD_W,
        {RESULT: 0x00000000_0011667D},
        CC_LOW,
    ),
    "AP zero sum is positive": (
        _zap("M2") + _line("AP", "W(8),P2") + LOAD_W,
        {RESULT: 0x00000000_0000000C},
        CC_ZERO,
    ),
    "AP alternate minus": (
        _zap("P1") + _line("AP", "W(8),ALTM") + LOAD_W,
        {RESULT: 0x00000000_0011667C},
        CC_HIGH,
    ),
    "AP rightmost bytes coincide": (
        _zap("P1") + _line("AP", "W(8),W+5(3)") + LOAD_W,
        {RESULT: 0x00000000_0024690C},
        CC_HIGH,
    ),
    "AP overflow with the mask off": (
        MASK_OFF + _line("MVC", "V(2),BIGP") + _line("AP", "V(2),ONE") + LOAD_V,
        {RESULT: 0x00000000_0000000C},
        CC_OVERFLOW,
    ),
    "SP": (
        _zap("P1") + _line("SP", "W(8),M2") + LOAD_W,
        {RESULT: 0x00000000_0013023C},
        CC_HIGH,
    ),
    "SP negative difference": (
        _zap("P2") + _line("SP", "W(8),P1") + LOAD_W,
        {RESULT: 0x00000000_0011667D},
        CC_LOW,
    ),
    "SP clears a field": (
        _zap("M1") + _line("SP", "W(8),W(8)") + LOAD_W,
        {RESULT: 0x00000000_0000000C},
        CC_ZERO,
    ),
    "AP longer second operand": (
        _line("MVC", "V(2),P2") + _line("AP", "V(2),P100") + LOAD_V,
        {RESULT: 0x778C},
        CC_HIGH,
    ),
    "AP longer second operand overflows with the mask off": (
        MASK_OFF + _line("MVC", "V(2),P2") + _line("AP", "V(2),P1") + LOAD_V,
        {RESULT: 0x023C},
        CC_OVERFLOW,
    ),
    "SP longer second operand": (
        _line("MVC", "V(2),P2") + _line("SP", "V(2),M100") + LOAD_V,
        {RESULT: 0x778C},
        CC_HIGH,
    ),
    "AP 31 digits": (
        _zap16("A31") + _line("AP", "W16(16),A31") + LOAD_W16,
        _wide(0x88888888_88888888, 0x88888888_8888888C),
        CC_HIGH,
    ),
    "AP 31 nines plus one overflows with the mask off": (
        MASK_OFF + _zap16("N31") + _line("AP", "W16(16),ONE") + LOAD_W16,
        _wide(0, 0xC),
        CC_OVERFLOW,
    ),
    "SP overflow to zero keeps the minus sign with the mask off": (
        MASK_OFF + _line("MVC", "V(2),BIGM") + _line("SP", "V(2),ONE") + LOAD_V,
        {RESULT: 0x00000000_0000000D},
        CC_OVERFLOW,
    ),
}

ZERO_AND_ADDS: Mapping[str, Case] = {
    "ZAP": (_zap("M1") + LOAD_W, {RESULT: 0x00000000_0012345D}, CC_LOW),
    "ZAP alternate plus": (_zap("ALTF") + LOAD_W, {RESULT: 0x678C}, CC_HIGH),
    "ZAP alternate minus": (_zap("ALTM") + LOAD_W, {RESULT: 0x678D}, CC_LOW),
    "ZAP negative zero is positive": (_zap("NZERO") + LOAD_W, {RESULT: 0xC}, CC_ZERO),
    "ZAP checks only the second operand": (
        _line("ZAP", "OUTF(8),P1") + _line("LG", "7,OUTF"),
        {RESULT: 0x00000000_0012345C},
        CC_HIGH,
    ),
    "ZAP first operand to the right": (
        _line("ZAP", "ZOV(8),ZOV(3)") + _line("LG", "7,ZOV"),
        {RESULT: 0x00000000_0012345C},
        CC_HIGH,
    ),
    "ZAP first operand to the left": (
        _line("ZAP", "ZOV2(3),ZOV2(8)") + _line("LG", "7,ZOV2"),
        {RESULT: 0x12345C00_0012345C},
        CC_HIGH,
    ),
    "ZAP 31 digits": (
        _zap16("N31") + LOAD_W16,
        _wide(0x99999999_99999999, 0x99999999_9999999C),
        CC_HIGH,
    ),
    "ZAP overflow with the mask off": (
        MASK_OFF + _line("ZAP", "V(2),P1") + LOAD_V,
        {RESULT: 0x345C},
        CC_OVERFLOW,
    ),
}

MULTIPLIES: Mapping[str, Case] = {
    "MP": (
        _zap("P1") + SET_CC + _line("MP", "W(8),M2") + LOAD_W,
        {RESULT: 0x00000000_8369910D},
        CC_SET_BY_LTR,
    ),
    "MP negative zero": (
        _zap("ZERO") + SET_CC + _line("MP", "W(8),M2") + LOAD_W,
        {RESULT: 0xD},
        CC_SET_BY_LTR,
    ),
    "MP 8-byte multiplier": (
        _zap16("A15") + SET_CC + _line("MP", "W16(16),M15") + LOAD_W16,
        _wide(0x01234567_89012344, 0x87654321_0987655D),
        CC_SET_BY_LTR,
    ),
    "MP rightmost bytes coincide": (
        _zap("P1") + SET_CC + _line("MP", "W(8),W+6(2)") + LOAD_W,
        {RESULT: 0x00000000_4259025C},
        CC_SET_BY_LTR,
    ),
}

DIVIDES: Mapping[str, Case] = {
    "DP": (
        _zap("P1") + SET_CC + _line("DP", "W(8),M2") + LOAD_W,
        {RESULT: 0x00000000_018D141C},
        CC_SET_BY_LTR,
    ),
    "DP zero remainder keeps the dividend sign": (
        _zap("MDIV") + SET_CC + _line("DP", "W(8),P2") + LOAD_W,
        {RESULT: 0x00000000_002D000D},
        CC_SET_BY_LTR,
    ),
    "DP zero quotient keeps the algebraic sign": (
        _zap("M5") + SET_CC + _line("DP", "W(8),P2") + LOAD_W,
        {RESULT: 0x00000000_000D005D},
        CC_SET_BY_LTR,
    ),
    "DP 15-digit divisor": (
        _zap16("M29") + SET_CC + _line("DP", "W16(16),D15") + LOAD_W16,
        _wide(0x07874999_9991140C, 0x65131271_2835677D),
        CC_SET_BY_LTR,
    ),
    "DP largest quotient": (
        _line("MVC", "V3(3),P8991") + SET_CC + _line("DP", "V3(3),NINE") + LOAD_V3,
        {RESULT: 0x999C0C},
        CC_SET_BY_LTR,
    ),
}

SHIFTS: Mapping[str, Case] = {
    "SRP left": (
        _zap("P1") + _line("SRP", "W(8),3,0") + LOAD_W,
        {RESULT: 0x00000001_2345000C},
        CC_HIGH,
    ),
    "SRP left 30 fills 31 digits": (
        _zap16("ONE") + _line("SRP", "W16(16),30,0") + LOAD_W16,
        _wide(0x10000000_00000000, 0xC),
        CC_HIGH,
    ),
    "SRP left 31 overflows with the mask off": (
        MASK_OFF + _zap16("A31") + _line("SRP", "W16(16),31,0") + LOAD_W16,
        _wide(0, 0xC),
        CC_OVERFLOW,
    ),
    "SRP right rounds": (
        _zap("P1") + _line("SRP", "W(8),63,5") + LOAD_W,
        {RESULT: 0x1235C},
        CC_HIGH,
    ),
    "SRP right truncates": (
        _zap("P1") + _line("SRP", "W(8),62,0") + LOAD_W,
        {RESULT: 0x123C},
        CC_HIGH,
    ),
    "SRP rounds the magnitude of a negative": (
        _zap("M1") + _line("SRP", "W(8),63,5") + LOAD_W,
        {RESULT: 0x1235D},
        CC_LOW,
    ),
    "SRP right to zero is positive": (
        _zap("M2") + _line("SRP", "W(8),60,9") + LOAD_W,
        {RESULT: 0xC},
        CC_ZERO,
    ),
    "SRP right 32 clears": (
        _zap("P1") + _line("SRP", "W(8),32,5") + LOAD_W,
        {RESULT: 0xC},
        CC_ZERO,
    ),
    "SRP no shift makes the sign preferred": (
        _zap("ZERO") + _line("MVC", "W+6(2),ALTM") + _line("SRP", "W(8),0,0") + LOAD_W,
        {RESULT: 0x678D},
        CC_LOW,
    ),
    "SRP shift from a base register": (
        _zap("P1") + _line("LA", "9,4094") + _line("SRP", "W(8),0(9),5") + LOAD_W,
        {RESULT: 0x123C},
        CC_HIGH,
    ),
    "SRP left overflow to zero keeps the minus sign with the mask off": (
        MASK_OFF + _line("MVC", "V(2),BIGM") + _line("SRP", "V(2),3,0") + LOAD_V,
        {RESULT: 0xD},
        CC_OVERFLOW,
    ),
}

EXECUTED: Mapping[str, Case] = {
    "EX of AP sets both lengths": (
        _zap("P1") + _line("LA", "1,X'71'") + _line("EX", "1,APX") + LOAD_W,
        {RESULT: 0x00000000_0013023C},
        CC_HIGH,
    ),
    "EX of SRP sets the length and the rounding digit": (
        _zap("P1") + _line("LA", "1,X'75'") + _line("EX", "1,SRPX") + LOAD_W,
        {RESULT: 0x1235C},
        CC_HIGH,
    ),
    "EX of DP sets both lengths": (
        _zap("P1") + SET_CC + _line("LA", "1,X'71'") + _line("EX", "1,DPX") + LOAD_W,
        {RESULT: 0x00000000_018D141C},
        CC_SET_BY_LTR,
    ),
}

COMPLETED: Mapping[str, Case] = {
    **ADDS,
    **ZERO_AND_ADDS,
    **MULTIPLIES,
    **DIVIDES,
    **SHIFTS,
    **EXECUTED,
}

DATA_EXCEPTIONS: Mapping[str, Case] = {
    "AP invalid digit": (_zap("P1") + _line("AP", "W(8),BADD"), {}, CC_SET_BY_ZAP),
    "AP invalid first operand": (SET_CC + _line("AP", "OUTF(8),P1"), {}, CC_LOW),
    "AP improper overlap": (
        _zap("P1") + _line("AP", "W(8),W+4(2)"),
        {},
        CC_SET_BY_ZAP,
    ),
    "SP invalid sign": (_zap("P1") + _line("SP", "W(8),BADS"), {}, CC_SET_BY_ZAP),
    "ZAP invalid sign": (SET_CC + _zap("BADS"), {}, CC_LOW),
    "MP too few leading zeros": (
        _line("MVC", "V3(3),P1") + SET_CC + _line("MP", "V3(3),ONE"),
        {},
        CC_SET_BY_LTR,
    ),
    "MP invalid multiplier": (
        _zap("P1") + SET_CC + _line("MP", "W(8),BADD"),
        {},
        CC_SET_BY_LTR,
    ),
    "DP invalid divisor": (
        _zap("P1") + SET_CC + _line("DP", "W(8),BADS"),
        {},
        CC_SET_BY_LTR,
    ),
    "SRP invalid rounding digit": (
        _zap("P1") + _line("SRP", "W(8),0,10"),
        {},
        CC_SET_BY_ZAP,
    ),
    "EX of SRP with an invalid rounding digit": (
        _zap("P1") + _line("LA", "1,X'7A'") + _line("EX", "1,SRPX"),
        {},
        CC_SET_BY_ZAP,
    ),
    "SRP invalid operand without a shift": (
        SET_CC + _line("SRP", "OUTF(8),0,0"),
        {},
        CC_LOW,
    ),
}

OVERFLOWS: Mapping[str, Case] = {
    "AP overflow": (
        _line("MVC", "V(2),BIGP") + _line("AP", "V(2),ONE"),
        {},
        CC_OVERFLOW,
    ),
    "SP overflow": (
        _line("MVC", "V(2),BIGM") + _line("SP", "V(2),ONE"),
        {},
        CC_OVERFLOW,
    ),
    "ZAP overflow": (_line("ZAP", "V(2),P1"), {}, CC_OVERFLOW),
    "SRP overflow": (
        _line("MVC", "V(2),BIGP") + _line("SRP", "V(2),1,0"),
        {},
        CC_OVERFLOW,
    ),
}

DIVIDE_EXCEPTIONS: Mapping[str, Case] = {
    "DP zero divisor": (
        _zap("P1") + SET_CC + _line("DP", "W(8),ZERO"),
        {},
        CC_SET_BY_LTR,
    ),
    "DP negative zero divisor": (
        _zap("P1") + SET_CC + _line("DP", "W(8),NZERO"),
        {},
        CC_SET_BY_LTR,
    ),
    "DP zero by zero": (
        _zap("ZERO") + SET_CC + _line("DP", "W(8),ZERO"),
        {},
        CC_SET_BY_LTR,
    ),
    "DP quotient too large": (
        _line("MVC", "V3(3),P9000") + SET_CC + _line("DP", "V3(3),NINE"),
        {},
        CC_SET_BY_LTR,
    ),
}


def _executed(lengths: str, target: str) -> str:
    return (
        _zap("P1")
        + SET_CC
        + _line("LA", f"1,X'{lengths}'")
        + _line("EX", f"1,{target}")
    )


SPECIFICATION_EXCEPTIONS: Mapping[str, Case] = {
    "MP equal lengths": (_executed("11", "MPX"), {}, CC_SET_BY_LTR),
    "MP multiplier over 8 bytes": (_executed("F8", "MPX"), {}, CC_SET_BY_LTR),
    "DP equal lengths": (_executed("11", "DPX"), {}, CC_SET_BY_LTR),
    "DP divisor over 8 bytes": (_executed("F8", "DPX"), {}, CC_SET_BY_LTR),
}

ALL_CASES: Mapping[str, tuple[Case, HlasmRun]] = {
    **{name: (case, ABENDED) for name, case in COMPLETED.items()},
    **{name: (case, DATA_EXCEPTION) for name, case in DATA_EXCEPTIONS.items()},
    **{name: (case, DECIMAL_OVERFLOW) for name, case in OVERFLOWS.items()},
    **{name: (case, DECIMAL_DIVIDE) for name, case in DIVIDE_EXCEPTIONS.items()},
    **{name: (case, SPECIFICATION) for name, case in SPECIFICATION_EXCEPTIONS.items()},
}

STORAGE_AFTER_ABEND: Mapping[str, tuple[Span, bytes]] = {
    "AP overflow": (V_SPAN, bytes.fromhex("000C")),
    "SP overflow": (V_SPAN, bytes.fromhex("000D")),
    "ZAP overflow": (V_SPAN, bytes.fromhex("345C")),
    "SRP overflow": (V_SPAN, bytes.fromhex("990C")),
    "AP invalid digit": (W_SPAN, bytes.fromhex("000000000012345C")),
    "MP too few leading zeros": (V3_SPAN, bytes.fromhex("12345C")),
    "DP zero divisor": (W_SPAN, bytes.fromhex("000000000012345C")),
    "DP quotient too large": (V3_SPAN, bytes.fromhex("09000C")),
    "EX of SRP with an invalid rounding digit": (
        W_SPAN,
        bytes.fromhex("000000000012345C"),
    ),
    **{
        name: (W_SPAN, bytes.fromhex("000000000012345C"))
        for name in SPECIFICATION_EXCEPTIONS
    },
}
