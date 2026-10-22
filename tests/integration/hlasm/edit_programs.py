# pyright: standard
"""Edit programs, shared by the VM tests and the z390 differential tests: each copies a pattern to OUT, sets CC 3, edits and loads OUT into R4 and R5; EDMK cases put GR1 less OUT's address in R6, the CC kept by IPM and SPM."""

from collections.abc import Mapping

from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import ABEND
from tests.integration.hlasm.packed_arithmetic_programs import (
    ABENDED,
    DATA_EXCEPTION,
    Case,
    Span,
)

CC_ZERO = 0
CC_MINUS = 1
CC_PLUS = 2
CC_SET_BY_ALR = 3
FIRST = 4
MARK = 6
FILLED = 0xA5A5A5A5_A5A5A5A5
HIGH_FILL = 0xA5A5A5A5_00000000
OUT_SPAN = (0x480, 0x490)

DATA = (
    "         ORG   T+X'400'\n"
    "FILL     DC    10X'A5A5A5A5A5A5A5A5'\n"
    "         ORG   T+X'480'\n"
    "OUT      DC    2XL8'FFFFFFFFFFFFFFFF'\n"
    "AMT      DC    X'40206B202020',X'6B2021204B20',X'20C3D9'\n"
    "STAR     DC    X'5C20202021204B2020'\n"
    "BLANK    DC    X'4020202021204B2020'\n"
    "MULTI    DC    X'4020212022202120C3D9'\n"
    "SIGNS    DC    X'40202120C3D9'\n"
    "FILLSEL  DC    X'212020'\n"
    "TEXT     DC    X'40C1C2C3'\n"
    "INV      DC    X'4020212020'\n"
    "P5       DC    PL5'1234567'\n"
    "M5       DC    PL5'-1234567'\n"
    "Z4       DC    PL4'0'\n"
    "P1234    DC    PL4'1234'\n"
    "P12      DC    PL4'12'\n"
    "TWO      DC    X'012C345D'\n"
    "TWOZ     DC    X'012C000C'\n"
    "ALTM     DC    X'012B'\n"
    "ALTP     DC    X'012F'\n"
    "BAD      DC    X'012CA5'\n"
    "EDX      ED    OUT(1),P5\n"
)


def edit_program(body: str) -> str:
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


SET_CC = _line("ALR", "2,2")
LOAD_OUT = _line("LMG", f"{FIRST},{FIRST + 1},OUT")
GR1_FILLED = _line("LG", "1,FILL")
MARK_OFFSET = (
    _line("IPM", "13")
    + _line("LGR", f"{MARK},1")
    + _line("LA", "0,OUT")
    + _line("SLR", f"{MARK},0")
    + _line("SPM", "13")
)


def _out(high: int, low: int) -> Mapping[int, int]:
    return {FIRST: high, FIRST + 1: low}


def _copied(pattern: str, length: int) -> str:
    return _line("MVC", f"OUT({length}),{pattern}") + SET_CC


def _edited(
    pattern: tuple[str, int], source: str, out: Mapping[int, int], cc: int
) -> Case:
    label, length = pattern
    body = _copied(label, length) + _line("ED", f"OUT({length}),{source}") + LOAD_OUT
    return (body, out, cc)


def _marked(
    setup: str,
    pattern: tuple[str, int],
    source: str,
    results: tuple[Mapping[int, int], int, int],
) -> Case:
    label, length = pattern
    out, offset, cc = results
    body = (
        setup
        + _copied(label, length)
        + _line("EDMK", f"OUT({length}),{source}")
        + LOAD_OUT
        + MARK_OFFSET
    )
    return (body, {**out, MARK: HIGH_FILL | offset}, cc)


AMOUNT = ("AMT", 15)
STARRED = ("STAR", 9)
BLANKED = ("BLANK", 9)
FIELDS = ("MULTI", 10)
SIGNED = ("SIGNS", 6)

AMOUNT_EDITED = (0x40404040_F1F26BF3, 0xF4F54BF6_F74040FF)
FIELDS_EDITED = _out(0x4040F1F2_40F3F4F5, 0xC3D9FFFF_FFFFFFFF)

EDITS: Mapping[str, Case] = {
    "ED amount mask drops CR when positive": _edited(
        AMOUNT, "P5", _out(*AMOUNT_EDITED), CC_PLUS
    ),
    "ED amount mask keeps CR when negative": _edited(
        AMOUNT, "M5", _out(0x40404040_F1F26BF3, 0xF4F54BF6_F7C3D9FF), CC_MINUS
    ),
    "ED zero suppression with an asterisk fill": _edited(
        STARRED, "Z4", _out(0x5C5C5C5C_5CF04BF0, 0xF0FFFFFF_FFFFFFFF), CC_ZERO
    ),
    "ED field separator starts a field": _edited(
        FIELDS, "TWO", FIELDS_EDITED, CC_MINUS
    ),
    "ED CC comes from the last field": _edited(
        FIELDS, "TWOZ", _out(0x4040F1F2_404040F0, 0x4040FFFF_FFFFFFFF), CC_ZERO
    ),
    "ED alternate minus keeps the message": _edited(
        SIGNED, "ALTM", _out(0x4040F1F2_C3D9FFFF, 0xFFFFFFFF_FFFFFFFF), CC_MINUS
    ),
    "ED alternate plus fills the message": _edited(
        SIGNED, "ALTP", _out(0x4040F1F2_4040FFFF, 0xFFFFFFFF_FFFFFFFF), CC_PLUS
    ),
    "ED fill byte that is a significance starter": _edited(
        ("FILLSEL", 3), "ALTP", _out(0x21F1F2FF_FFFFFFFF, 0xFFFFFFFF_FFFFFFFF), CC_PLUS
    ),
    "ED without digit selectors fills every message byte": _edited(
        ("TEXT", 4), "TWO", _out(0x40404040_FFFFFFFF, 0xFFFFFFFF_FFFFFFFF), CC_ZERO
    ),
    "EX of ED sets the length": (
        _copied("AMT", 15) + _line("LA", "1,X'0E'") + _line("EX", "1,EDX") + LOAD_OUT,
        _out(*AMOUNT_EDITED),
        CC_PLUS,
    ),
    "EDMK marks the first significant digit": _marked(
        GR1_FILLED,
        BLANKED,
        "P1234",
        (_out(0x40404040_F1F24BF3, 0xF4FFFFFF_FFFFFFFF), 4, CC_PLUS),
    ),
    "EDMK leaves GR1 when a significance starter forces significance": _marked(
        GR1_FILLED + _line("LA", "1,OUT+5"),
        BLANKED,
        "P12",
        (_out(0x40404040_40F04BF1, 0xF2FFFFFF_FFFFFFFF), 5, CC_PLUS),
    ),
    "EDMK marks the rightmost field": _marked(
        GR1_FILLED, FIELDS, "TWO", (FIELDS_EDITED, 5, CC_MINUS)
    ),
}

DATA_EXCEPTIONS: Mapping[str, Case] = {
    "ED invalid digit is suppressed": (
        _copied("INV", 5) + _line("ED", "OUT(5),BAD"),
        {},
        CC_SET_BY_ALR,
    ),
    "EDMK invalid digit leaves GR1": (
        GR1_FILLED + _copied("INV", 5) + _line("EDMK", "OUT(5),BAD"),
        {1: FILLED},
        CC_SET_BY_ALR,
    ),
}

ALL_CASES: Mapping[str, tuple[Case, HlasmRun]] = {
    **{name: (case, ABENDED) for name, case in EDITS.items()},
    **{name: (case, DATA_EXCEPTION) for name, case in DATA_EXCEPTIONS.items()},
}

STORAGE_AFTER_ABEND: Mapping[str, tuple[Span, bytes]] = {
    "ED invalid digit is suppressed": (
        OUT_SPAN,
        bytes.fromhex("4020212020") + bytes([0xFF] * 11),
    ),
}
