# pyright: standard
"""Decimal conversion programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; each loads what it stored into registers, and the CC is set before the instruction so an unchanged CC shows."""

from collections.abc import Mapping

from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import ABEND
from tests.integration.hlasm.packed_arithmetic_programs import (
    ABENDED,
    DATA_EXCEPTION,
    SPECIFICATION,
    Case,
)

FIXED_POINT_DIVIDE = HlasmRun(return_code=0, abend="S0C9", stdout="")

CC_SET_BY_LTR = 1
CC_PLUS = 0
CC_MINUS = 1
CC_SIGN_INVALID = 3
RESULT = 3
FIRST = 4
FILLED = 0xA5A5A5A5_A5A5A5A5
HIGH_FILL = 0xA5A5A5A5_00000000
OUT_FILL = 0xFFFFFFFF_FFFFFFFF

SET_CC = "         LTR   2,2\n"
DIGITS_10 = "X'31323334353637383930'"
CHARACTERS_10 = "X'0031003200330034003500360037003800390030'"

OUT_SPAN = (0xC00, 0xC78)
SECTION = "T"

DATA = (
    "FILL     DC    10X'A5A5A5A5A5A5A5A5'\n"
    "P7       DC    PL8'1234567'\n"
    "PMAX     DC    PL8'2147483647'\n"
    "PMIN     DC    PL8'-2147483648'\n"
    "POVER    DC    PL8'2147483648'\n"
    "PUNDER   DC    PL8'-2147483649'\n"
    "PBIG     DC    PL8'-999999999999999'\n"
    "NZ8      DC    X'000000000000000D'\n"
    "ALT8     DC    X'000000000012345B'\n"
    "BADD8    DC    X'00000000001A345C'\n"
    "BADS8    DC    X'0000000000123454'\n"
    "GMAX     DC    X'00000000',X'00009223',X'37203685',X'4775807C'\n"
    "GMIN     DC    PL16'-9223372036854775808'\n"
    "GM1      DC    PL16'-1'\n"
    "GOVER    DC    PL16'9223372036854775808'\n"
    "GUNDER   DC    PL16'-9223372036854775809'\n"
    "G31      DC    PL16'-9999999999999999999999999999999'\n"
    "GBADS    DC    XL15'00',X'13'\n"
    "MINF     DC    F'-2147483648'\n"
    "GMINF    DC    X'8000000000000000'\n"
    "Z5       DC    C'12345'\n"
    "Z5M      DC    X'F1F2F3F4D5'\n"
    "Z1       DC    C'7'\n"
    "ZX       DC    X'A1B2C3'\n"
    "SW       DC    X'12345678'\n"
    "Z8       DC    C'12345678'\n"
    "P3       DC    PL3'12345'\n"
    "P3M      DC    PL3'-12345'\n"
    "BADP     DC    X'A1B2'\n"
    "U        DC    XL5'00',PL3'12345'\n"
    "U2       DC    XL4'00',PL3'12345',X'00'\n"
    "AS5      DC    X'3132333435'\n"
    "EB5      DC    C'12345'\n"
    f"AS31     DC    3{DIGITS_10},X'31'\n"
    f"AS32     DC    X'39',3{DIGITS_10},X'31'\n"
    "US5      DC    X'00310032003300340035'\n"
    "UHIGH    DC    X'FF37FF38'\n"
    "US32     DC    X'0039'\n"
    f"         DC    3{CHARACTERS_10}\n"
    "         DC    X'0031'\n"
    "P16      DC    PL16'12345'\n"
    "M16      DC    PL16'-12345'\n"
    "ALTP16   DC    XL13'00',X'12345F'\n"
    "ALTM16   DC    XL13'00',X'12345B'\n"
    "BADS16   DC    XL13'00',X'123457'\n"
    "BADD16   DC    XL13'00',X'1A345C'\n"
    "N31      DC    X'12345678',X'90123456',X'78901234',X'5678901C'\n"
    "         ORG   T+X'C00'\n"
    "OUT      DC    XL8'FFFFFFFFFFFFFFFF'\n"
    "OUT16    DC    2XL8'FFFFFFFFFFFFFFFF'\n"
    "OUT32    DC    4XL8'FFFFFFFFFFFFFFFF'\n"
    "OUT64    DC    8XL8'FFFFFFFFFFFFFFFF'\n"
    "PACKX    PACK  OUT(1),Z5(1)\n"
    "UNPKX    UNPK  OUT(1),P3(1)\n"
    "PKAX     PKA   OUT16,AS5(1)\n"
    "PKUX     PKU   OUT16,US5(2)\n"
    "UNPKAX   UNPKA OUT(1),P16\n"
    "UNPKUX   UNPKU OUT(2),P16\n"
)


def conversion_program(body: str) -> str:
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         LMG   2,11,FILL\n"
        f"{body}{ABEND}{DATA}"
        "         END\n"
    )


def _line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<6}{operands}\n"


def _executed(fields: str, target: str) -> str:
    return _line("LA", f"1,X'{fields}'") + _line("EX", f"1,{target}")


def _filled(low_word: int) -> Mapping[int, int]:
    return {RESULT: HIGH_FILL | low_word}


def _loaded(*values: int) -> Mapping[int, int]:
    return {FIRST + k: value for k, value in enumerate(values)}


def _converted(mnemonic: str, field: str, results: Mapping[int, int]) -> Case:
    return (SET_CC + _line(mnemonic, f"{RESULT},{field}"), results, CC_SET_BY_LTR)


def _stored(setup: str, mnemonic: str, load: str, results: Mapping[int, int]) -> Case:
    body = setup + SET_CC + _line(mnemonic, f"{RESULT},OUT") + load
    return (body, results, CC_SET_BY_LTR)


def _moved(lines: str, load: str, results: Mapping[int, int]) -> Case:
    return (SET_CC + lines + load, results, CC_SET_BY_LTR)


def _unpacked(lines: str, load: str, results: Mapping[int, int], cc: int) -> Case:
    preset = "" if cc == CC_SET_BY_LTR else SET_CC
    return (preset + lines + load, results, cc)


LOAD_OUT = _line("LG", f"{FIRST},OUT")
LOAD_OUT16 = _line("LMG", f"{FIRST},{FIRST + 1},OUT16")
LOAD_OUT32 = _line("LMG", f"{FIRST},{FIRST + 3},OUT32")
LOAD_OUT64 = _line("LMG", f"{FIRST},{FIRST + 7},OUT64")
DIGITS_31 = (0x12345678_90123456, 0x78901234_5678901C)
ASCII_31 = (
    0x30313233_34353637,
    0x38393031_32333435,
    0x36373839_30313233,
    0x34353637_38393031,
)
UNICODE_31 = (
    0x0030_0031_0032_0033,
    0x0034_0035_0036_0037,
    0x0038_0039_0030_0031,
    0x0032_0033_0034_0035,
    0x0036_0037_0038_0039,
    0x0030_0031_0032_0033,
    0x0034_0035_0036_0037,
    0x0038_0039_0030_0031,
)

TO_BINARY: Mapping[str, Case] = {
    "CVB": _converted("CVB", "P7", _filled(0x0012D687)),
    "CVB largest": _converted("CVB", "PMAX", _filled(0x7FFFFFFF)),
    "CVB most negative": _converted("CVB", "PMIN", _filled(0x80000000)),
    "CVB negative zero": _converted("CVB", "NZ8", _filled(0)),
    "CVBY alternate minus": _converted("CVBY", "ALT8", _filled(0xFFFFCFC7)),
    "CVBG largest": _converted("CVBG", "GMAX", {RESULT: 0x7FFFFFFF_FFFFFFFF}),
    "CVBG most negative": _converted("CVBG", "GMIN", {RESULT: 0x80000000_00000000}),
    "CVBG minus one": _converted("CVBG", "GM1", {RESULT: 0xFFFFFFFF_FFFFFFFF}),
}

TO_DECIMAL: Mapping[str, Case] = {
    "CVD negative": _stored(
        _line("LHI", f"{RESULT},-1234"), "CVD", LOAD_OUT, _loaded(0x1234D)
    ),
    "CVD positive": _stored(
        _line("LHI", f"{RESULT},1234"), "CVD", LOAD_OUT, _loaded(0x1234C)
    ),
    "CVD zero ignores the high word": _stored(
        _line("LHI", f"{RESULT},0"), "CVD", LOAD_OUT, _loaded(0xC)
    ),
    "CVDY most negative": _stored(
        _line("L", f"{RESULT},MINF"), "CVDY", LOAD_OUT, _loaded(0x00000214_7483648D)
    ),
    "CVDG most negative": (
        _line("LG", f"{RESULT},GMINF")
        + SET_CC
        + _line("CVDG", f"{RESULT},OUT16")
        + LOAD_OUT16,
        _loaded(0x00000000_00009223, 0x37203685_4775808D),
        CC_SET_BY_LTR,
    ),
    "CVDG positive": (
        _line("LGHI", f"{RESULT},5678")
        + SET_CC
        + _line("CVDG", f"{RESULT},OUT16")
        + LOAD_OUT16,
        _loaded(0, 0x5678C),
        CC_SET_BY_LTR,
    ),
    "CVDG uses the high word": (
        _line("LHI", f"{RESULT},0")
        + SET_CC
        + _line("CVDG", f"{RESULT},OUT16")
        + LOAD_OUT16,
        _loaded(0x00000000_00006510, 0x61555820_5997056D),
        CC_SET_BY_LTR,
    ),
}

PACKS: Mapping[str, Case] = {
    "PACK": _moved(_line("PACK", "OUT(8),Z5"), LOAD_OUT, _loaded(0x12345F)),
    "PACK keeps the zone as the sign": _moved(
        _line("PACK", "OUT(8),Z5M"), LOAD_OUT, _loaded(0x12345D)
    ),
    "PACK truncates on the left": _moved(
        _line("PACK", "OUT(2),Z5"), LOAD_OUT, _loaded(0x345FFFFF_FFFFFFFF)
    ),
    "PACK pads with zeros": _moved(
        _line("PACK", "OUT(3),Z1"), LOAD_OUT, _loaded(0x00007FFF_FFFFFFFF)
    ),
    "PACK ignores zones and checks nothing": _moved(
        _line("PACK", "OUT(2),ZX"), LOAD_OUT, _loaded(0x123CFFFF_FFFFFFFF)
    ),
    "PACK one byte swaps its nibbles": _moved(
        _line("PACK", "SW(1),SW(1)"),
        _line("L", f"{FIRST},SW"),
        _loaded(HIGH_FILL | 0x21345678),
    ),
    "PACK in place": _moved(
        _line("PACK", "Z8(8),Z8(8)"), _line("LG", f"{FIRST},Z8"), _loaded(0x12345678F)
    ),
    "PACK overlapping to the left": _moved(
        _line("PACK", "Z8(5),Z8(8)"),
        _line("LG", f"{FIRST},Z8"),
        _loaded(0x012F7F67_8FF6F7F8),
    ),
    "EX of PACK sets both lengths": _moved(
        _executed("74", "PACKX"), LOAD_OUT, _loaded(0x12345F)
    ),
}

UNPACKS: Mapping[str, Case] = {
    "UNPK": _moved(_line("UNPK", "OUT(8),P3"), LOAD_OUT, _loaded(0xF0F0F0F1_F2F3F4C5)),
    "UNPK negative": _moved(
        _line("UNPK", "OUT(8),P3M"), LOAD_OUT, _loaded(0xF0F0F0F1_F2F3F4D5)
    ),
    "UNPK truncates on the left": _moved(
        _line("UNPK", "OUT(3),P3"), LOAD_OUT, _loaded(0xF3F4C5FF_FFFFFFFF)
    ),
    "UNPK even length drops a high digit": _moved(
        _line("UNPK", "OUT(2),P3"), LOAD_OUT, _loaded(0xF4C5FFFF_FFFFFFFF)
    ),
    "UNPK checks nothing": _moved(
        _line("UNPK", "OUT(4),BADP"), LOAD_OUT, _loaded(0xF0FAF12B_FFFFFFFF)
    ),
    "UNPK with the overlap the Principles of Operation allow": _moved(
        _line("UNPK", "U2(8),U2+4(3)"),
        _line("LG", f"{FIRST},U2"),
        _loaded(0xF0F0F0F1_F2F3F4C5),
    ),
    "UNPK overlapping too far": _moved(
        _line("UNPK", "U(8),U+5(3)"),
        _line("LG", f"{FIRST},U"),
        _loaded(0xF0F0F0FF_F3F3F4C5),
    ),
    "EX of UNPK sets both lengths": _moved(
        _executed("72", "UNPKX"), LOAD_OUT, _loaded(0xF0F0F0F1_F2F3F4C5)
    ),
}

PACKS_TO_16: Mapping[str, Case] = {
    "PKA": _moved(_line("PKA", "OUT16,AS5(5)"), LOAD_OUT16, _loaded(0, 0x12345C)),
    "PKA EBCDIC digits": _moved(
        _line("PKA", "OUT16,EB5(5)"), LOAD_OUT16, _loaded(0, 0x12345C)
    ),
    "PKA 31 digits": _moved(
        _line("PKA", "OUT16,AS31(31)"), LOAD_OUT16, _loaded(*DIGITS_31)
    ),
    "PKA 32 bytes ignores the leftmost": _moved(
        _line("PKA", "OUT16,AS32(32)"), LOAD_OUT16, _loaded(*DIGITS_31)
    ),
    "EX of PKA sets the second length": _moved(
        _executed("04", "PKAX"), LOAD_OUT16, _loaded(0, 0x12345C)
    ),
    "PKU": _moved(_line("PKU", "OUT16,US5(10)"), LOAD_OUT16, _loaded(0, 0x12345C)),
    "PKU ignores the leftmost 12 bits": _moved(
        _line("PKU", "OUT16,UHIGH(4)"), LOAD_OUT16, _loaded(0, 0x78C)
    ),
    "PKU 32 characters ignores the leftmost": _moved(
        _line("PKU", "OUT16,US32(64)"), LOAD_OUT16, _loaded(*DIGITS_31)
    ),
    "EX of PKU sets the second length": _moved(
        _executed("09", "PKUX"), LOAD_OUT16, _loaded(0, 0x12345C)
    ),
}

UNPACKS_FROM_16: Mapping[str, Case] = {
    "UNPKA": _unpacked(
        _line("UNPKA", "OUT(8),P16"), LOAD_OUT, _loaded(0x30303031_32333435), CC_PLUS
    ),
    "UNPKA negative": _unpacked(
        _line("UNPKA", "OUT(8),M16"), LOAD_OUT, _loaded(0x30303031_32333435), CC_MINUS
    ),
    "UNPKA alternate plus": _unpacked(
        _line("UNPKA", "OUT(8),ALTP16"),
        LOAD_OUT,
        _loaded(0x30303031_32333435),
        CC_PLUS,
    ),
    "UNPKA alternate minus": _unpacked(
        _line("UNPKA", "OUT(8),ALTM16"),
        LOAD_OUT,
        _loaded(0x30303031_32333435),
        CC_MINUS,
    ),
    "UNPKA invalid sign sets CC 3": _unpacked(
        _line("UNPKA", "OUT(8),BADS16"),
        LOAD_OUT,
        _loaded(0x30303031_32333435),
        CC_SIGN_INVALID,
    ),
    "UNPKA does not check digits": _unpacked(
        _line("UNPKA", "OUT(8),BADD16"),
        LOAD_OUT,
        _loaded(0x30303031_3A333435),
        CC_PLUS,
    ),
    "UNPKA 32 bytes puts a zero leftmost": _unpacked(
        _line("UNPKA", "OUT32(32),N31"), LOAD_OUT32, _loaded(*ASCII_31), CC_PLUS
    ),
    "EX of UNPKA sets the first length": _unpacked(
        _executed("07", "UNPKAX"), LOAD_OUT, _loaded(0x30303031_32333435), CC_PLUS
    ),
    "UNPKU": _unpacked(
        _line("UNPKU", "OUT(8),P16"), LOAD_OUT, _loaded(0x0032_0033_0034_0035), CC_PLUS
    ),
    "UNPKU negative": _unpacked(
        _line("UNPKU", "OUT(8),M16"),
        LOAD_OUT,
        _loaded(0x0032_0033_0034_0035),
        CC_MINUS,
    ),
    "UNPKU invalid sign sets CC 3": _unpacked(
        _line("UNPKU", "OUT(8),BADS16"),
        LOAD_OUT,
        _loaded(0x0032_0033_0034_0035),
        CC_SIGN_INVALID,
    ),
    "UNPKU 64 bytes puts a zero leftmost": _unpacked(
        _line("UNPKU", "OUT64(64),N31"), LOAD_OUT64, _loaded(*UNICODE_31), CC_PLUS
    ),
    "EX of UNPKU sets the first length": _unpacked(
        _executed("07", "UNPKUX"),
        LOAD_OUT,
        _loaded(0x0032_0033_0034_0035),
        CC_PLUS,
    ),
}

COMPLETED: Mapping[str, Case] = {
    **TO_BINARY,
    **TO_DECIMAL,
    **PACKS,
    **UNPACKS,
    **PACKS_TO_16,
    **UNPACKS_FROM_16,
}

DATA_EXCEPTIONS: Mapping[str, Case] = {
    "CVB invalid digit": _converted("CVB", "BADD8", {RESULT: FILLED}),
    "CVBY invalid sign": _converted("CVBY", "BADS8", {RESULT: FILLED}),
    "CVBG invalid sign": _converted("CVBG", "GBADS", {RESULT: FILLED}),
}

FIXED_POINT_DIVIDES: Mapping[str, Case] = {
    "CVB too large stores the low word": _converted(
        "CVB", "POVER", _filled(0x80000000)
    ),
    "CVB too negative stores the low word": _converted(
        "CVB", "PUNDER", _filled(0x7FFFFFFF)
    ),
    "CVBY 15 digits stores the low word": _converted(
        "CVBY", "PBIG", _filled(0x5B398001)
    ),
    "CVBG too large is suppressed": _converted("CVBG", "GOVER", {RESULT: FILLED}),
    "CVBG too negative is suppressed": _converted("CVBG", "GUNDER", {RESULT: FILLED}),
    "CVBG 31 digits is suppressed": _converted("CVBG", "G31", {RESULT: FILLED}),
}

SPECIFICATIONS: Mapping[str, Case] = {
    "PKA second operand over 32 bytes": (
        SET_CC + _executed("20", "PKAX"),
        {},
        CC_SET_BY_LTR,
    ),
    "PKU second operand over 64 bytes": (
        SET_CC + _executed("40", "PKUX"),
        {},
        CC_SET_BY_LTR,
    ),
    "PKU odd second-operand length": (
        SET_CC + _line("PKU", "OUT16,US5(9)"),
        {},
        CC_SET_BY_LTR,
    ),
    "UNPKA first operand over 32 bytes": (
        SET_CC + _executed("20", "UNPKAX"),
        {},
        CC_SET_BY_LTR,
    ),
    "UNPKU first operand over 64 bytes": (
        SET_CC + _executed("40", "UNPKUX"),
        {},
        CC_SET_BY_LTR,
    ),
    "UNPKU odd first-operand length": (
        SET_CC + _line("UNPKU", "OUT(7),P16"),
        {},
        CC_SET_BY_LTR,
    ),
}

ALL_CASES: Mapping[str, tuple[Case, HlasmRun]] = {
    **{name: (case, ABENDED) for name, case in COMPLETED.items()},
    **{name: (case, DATA_EXCEPTION) for name, case in DATA_EXCEPTIONS.items()},
    **{name: (case, FIXED_POINT_DIVIDE) for name, case in FIXED_POINT_DIVIDES.items()},
    **{name: (case, SPECIFICATION) for name, case in SPECIFICATIONS.items()},
}
