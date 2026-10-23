# pyright: standard
"""Unicode conversion and string search programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; the output area sits at a fixed offset so its storage can be read back."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import ABEND, HIGH_FILL

type Case = tuple[str, Mapping[int, int], int]

CC_EXHAUSTED = 0
CC_FULL = 1
CC_INVALID = 2
CC_FOUND = 1
CC_NOT_FOUND = 2
SLR_EQUAL_CC = 2
SLR_NONZERO_CC = 3
INITIAL_CC = 0
BIT_32 = 0x80000000
OUT_BYTES = 16
UNWRITTEN = 0xFF
DOUBLEWORD = 8

DATA = (
    "         ORG   T+X'400'\n"
    "FILL     DC    10X'A5A5A5A5A5A5A5A5'\n"
    "         ORG   T+X'480'\n"
    "OUT      DC    16X'FF'\n"
    "         ORG   T+X'490'\n"
    "BIT32    DC    X'80000000'\n"
    "U8       DC    X'41C3A9E282ACF09F9880'\n"
    "U16      DC    X'004100E920ACD83DDE00'\n"
    "U32      DC    X'00000041000000E9000020AC0001F600'\n"
    "BADLEAD  DC    X'4180'\n"
    "OVERLONG DC    X'C080'\n"
    "SURR8    DC    X'EDA080'\n"
    "CONT     DC    X'C329'\n"
    "LONG4    DC    X'F0808080'\n"
    "F5LEAD   DC    X'F5808080'\n"
    "F8LEAD   DC    X'F8'\n"
    "LOW16    DC    X'DC00'\n"
    "HIGH16   DC    X'D83D0041'\n"
    "SURR32   DC    X'000000410000D800'\n"
    "LOW32    DC    X'0000DC00'\n"
    "OVER32   DC    X'00110000'\n"
    "ONES32   DC    X'FFFFFFFF'\n"
    "STR      DC    C'ABCDE'\n"
    "HSTR     DC    X'004100420043'\n"
    "HSTR2    DC    X'42000042'\n"
    "BELOW800 DC    X'E09FBF'\n"
    "BELOW1M  DC    X'F08FBFBF'\n"
    "ABOVE10F DC    X'F4908080'\n"
)

DATA_SPAN = (0x480, 0x490)
SECTION = "T"


def unicode_program(body: str) -> str:
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         LMG   2,11,FILL\n"
        f"{body}{ABEND}{DATA}"
        "         END\n"
    )


def _offset(register: int, address: str) -> str:
    return f"         LA    9,{address}\n" f"         SLR   {register},9\n"


def _pairs(target_length: int, source: tuple[str, int]) -> str:
    label, length = source
    return (
        "         LA    2,OUT\n"
        f"         LHI   3,{target_length}\n"
        f"         LA    4,{label}\n"
        f"         LHI   5,{length}\n"
    )


def _out(stored: bytes) -> Mapping[int, int]:
    image = stored + bytes([UNWRITTEN] * (OUT_BYTES - len(stored)))
    return {
        6: int.from_bytes(image[:DOUBLEWORD], "big"),
        7: int.from_bytes(image[DOUBLEWORD:], "big"),
    }


def _converted(
    name: str,
    instruction: str,
    operands: tuple[int, str, int],
    stored_hex: str,
    progress: tuple[int, int],
) -> Mapping[str, Case]:
    target_length, source, source_length = operands
    consumed, cc = progress
    stored = bytes.fromhex(stored_hex)
    setup = _pairs(target_length, (source, source_length)) + instruction
    return {
        name: (
            setup + "         LG    6,OUT\n" "         LG    7,OUT+8\n",
            {
                3: HIGH_FILL | (target_length - len(stored)),
                5: HIGH_FILL | (source_length - consumed),
                **_out(stored),
            },
            cc,
        ),
        f"{name} registers": (
            setup
            + _offset(2, f"OUT+{len(stored)}")
            + _offset(4, f"{source}+{consumed}"),
            {2: HIGH_FILL, 4: HIGH_FILL},
            SLR_EQUAL_CC,
        ),
    }


UTF8_TEXT = "41 C3A9 E282AC F09F9880"
UTF16_TEXT = "0041 00E9 20AC D83DDE00"
UTF32_TEXT = "00000041 000000E9 000020AC 0001F600"

UTF8_TO_UTF16: Mapping[str, Case] = {
    **_converted(
        "CU12 exhausted",
        "         CU12  2,4\n",
        (16, "U8", 10),
        UTF16_TEXT,
        (10, CC_EXHAUSTED),
    ),
    **_converted(
        "CU12 first operand full",
        "         CU12  2,4\n",
        (7, "U8", 10),
        "0041 00E9 20AC",
        (6, CC_FULL),
    ),
    **_converted(
        "CU12 truncated character",
        "         CU12  2,4\n",
        (16, "U8", 9),
        "0041 00E9 20AC",
        (6, CC_EXHAUSTED),
    ),
    **_converted(
        "CU12 invalid lead byte",
        "         CU12  2,4\n",
        (16, "BADLEAD", 2),
        "0041",
        (1, CC_INVALID),
    ),
    **_converted(
        "CU12 invalid beats a full first operand",
        "         CU12  2,4\n",
        (0, "BADLEAD+1", 1),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CU12 F8 lead invalid",
        "         CU12  2,4\n",
        (16, "F8LEAD", 1),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CU12 overlong unchecked",
        "         CU12  2,4\n",
        (16, "OVERLONG", 2),
        "0000",
        (2, CC_EXHAUSTED),
    ),
    **_converted(
        "CU12 overlong checked",
        "         CU12  2,4,1\n",
        (16, "OVERLONG", 2),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CU12 surrogate unchecked",
        "         CU12  2,4\n",
        (16, "SURR8", 3),
        "D800",
        (3, CC_EXHAUSTED),
    ),
    **_converted(
        "CU12 surrogate checked",
        "         CU12  2,4,1\n",
        (16, "SURR8", 3),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CU12 continuation bits unchecked",
        "         CU12  2,4\n",
        (16, "CONT", 2),
        "00E9",
        (2, CC_EXHAUSTED),
    ),
    **_converted(
        "CU12 continuation bits checked",
        "         CU12  2,4,1\n",
        (16, "CONT", 2),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CU12 overlong four-byte unchecked",
        "         CU12  2,4\n",
        (16, "LONG4", 4),
        "DBC0 DC00",
        (4, CC_EXHAUSTED),
    ),
    **_converted(
        "CU12 F5 lead unchecked",
        "         CU12  2,4\n",
        (16, "F5LEAD", 4),
        "D8C0 DC00",
        (4, CC_EXHAUSTED),
    ),
    **_converted(
        "CU12 F5 lead checked beats exhaustion",
        "         CU12  2,4,1\n",
        (16, "F5LEAD", 2),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CU12 both operands end together",
        "         CU12  2,4\n",
        (10, "U8", 10),
        "0041 00E9 20AC D83DDE00",
        (10, CC_EXHAUSTED),
    ),
    **_converted(
        "CU12 three-byte below 800 unchecked",
        "         CU12  2,4\n",
        (16, "BELOW800", 3),
        "07FF",
        (3, CC_EXHAUSTED),
    ),
    **_converted(
        "CU12 three-byte below 800 checked",
        "         CU12  2,4,1\n",
        (16, "BELOW800", 3),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CU12 four-byte below 10000 unchecked",
        "         CU12  2,4\n",
        (16, "BELOW1M", 4),
        "DBFF DFFF",
        (4, CC_EXHAUSTED),
    ),
    **_converted(
        "CU12 four-byte below 10000 checked",
        "         CU12  2,4,1\n",
        (16, "BELOW1M", 4),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CU12 four-byte above 10FFFF unchecked",
        "         CU12  2,4\n",
        (16, "ABOVE10F", 4),
        "D800 DC00",
        (4, CC_EXHAUSTED),
    ),
    **_converted(
        "CU12 four-byte above 10FFFF checked",
        "         CU12  2,4,1\n",
        (16, "ABOVE10F", 4),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CUTFU exhausted",
        "         CUTFU 2,4\n",
        (16, "U8", 10),
        UTF16_TEXT,
        (10, CC_EXHAUSTED),
    ),
    **_converted(
        "CUTFU surrogate checked",
        "         CUTFU 2,4,1\n",
        (16, "SURR8", 3),
        "",
        (0, CC_INVALID),
    ),
}

UTF8_TO_UTF32: Mapping[str, Case] = {
    **_converted(
        "CU14 exhausted",
        "         CU14  2,4\n",
        (16, "U8", 10),
        UTF32_TEXT,
        (10, CC_EXHAUSTED),
    ),
    **_converted(
        "CU14 first operand full",
        "         CU14  2,4\n",
        (15, "U8", 10),
        "00000041 000000E9 000020AC",
        (6, CC_FULL),
    ),
    **_converted(
        "CU14 surrogate unchecked",
        "         CU14  2,4\n",
        (16, "SURR8", 3),
        "0000D800",
        (3, CC_EXHAUSTED),
    ),
    **_converted(
        "CU14 surrogate checked",
        "         CU14  2,4,1\n",
        (16, "SURR8", 3),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CU14 F5 lead unchecked",
        "         CU14  2,4\n",
        (16, "F5LEAD", 4),
        "00140000",
        (4, CC_EXHAUSTED),
    ),
}

UTF16_TO_UTF8: Mapping[str, Case] = {
    **_converted(
        "CU21 exhausted",
        "         CU21  2,4\n",
        (16, "U16", 10),
        UTF8_TEXT,
        (10, CC_EXHAUSTED),
    ),
    **_converted(
        "CU21 first operand full",
        "         CU21  2,4\n",
        (9, "U16", 10),
        "41 C3A9 E282AC",
        (6, CC_FULL),
    ),
    **_converted(
        "CU21 high surrogate at the end",
        "         CU21  2,4\n",
        (16, "U16", 8),
        "41 C3A9 E282AC",
        (6, CC_EXHAUSTED),
    ),
    **_converted(
        "CU21 odd length",
        "         CU21  2,4\n",
        (16, "U16", 3),
        "41",
        (2, CC_EXHAUSTED),
    ),
    **_converted(
        "CU21 isolated low surrogate unchecked",
        "         CU21  2,4\n",
        (16, "LOW16", 2),
        "EDB080",
        (2, CC_EXHAUSTED),
    ),
    **_converted(
        "CU21 isolated low surrogate checked",
        "         CU21  2,4,1\n",
        (16, "LOW16", 2),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CU21 unpaired high surrogate unchecked",
        "         CU21  2,4\n",
        (16, "HIGH16", 4),
        "F09F9181",
        (4, CC_EXHAUSTED),
    ),
    **_converted(
        "CU21 unpaired high surrogate checked",
        "         CU21  2,4,1\n",
        (16, "HIGH16", 4),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CUUTF exhausted",
        "         CUUTF 2,4\n",
        (16, "U16", 10),
        UTF8_TEXT,
        (10, CC_EXHAUSTED),
    ),
    **_converted(
        "CUUTF unpaired high surrogate checked",
        "         CUUTF 2,4,1\n",
        (16, "HIGH16", 4),
        "",
        (0, CC_INVALID),
    ),
}

UTF16_TO_UTF32: Mapping[str, Case] = {
    **_converted(
        "CU24 exhausted",
        "         CU24  2,4\n",
        (16, "U16", 10),
        UTF32_TEXT,
        (10, CC_EXHAUSTED),
    ),
    **_converted(
        "CU24 first operand full",
        "         CU24  2,4\n",
        (14, "U16", 10),
        "00000041 000000E9 000020AC",
        (6, CC_FULL),
    ),
    **_converted(
        "CU24 isolated low surrogate unchecked",
        "         CU24  2,4\n",
        (16, "LOW16", 2),
        "0000DC00",
        (2, CC_EXHAUSTED),
    ),
    **_converted(
        "CU24 isolated low surrogate checked",
        "         CU24  2,4,1\n",
        (16, "LOW16", 2),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CU24 unpaired high surrogate checked",
        "         CU24  2,4,1\n",
        (16, "HIGH16", 4),
        "",
        (0, CC_INVALID),
    ),
}

UTF32_TO_UTF8: Mapping[str, Case] = {
    **_converted(
        "CU41 exhausted",
        "         CU41  2,4\n",
        (16, "U32", 16),
        UTF8_TEXT,
        (16, CC_EXHAUSTED),
    ),
    **_converted(
        "CU41 first operand full",
        "         CU41  2,4\n",
        (9, "U32", 16),
        "41 C3A9 E282AC",
        (12, CC_FULL),
    ),
    **_converted(
        "CU41 truncated character",
        "         CU41  2,4\n",
        (16, "U32", 15),
        "41 C3A9 E282AC",
        (12, CC_EXHAUSTED),
    ),
    **_converted(
        "CU41 high surrogate invalid",
        "         CU41  2,4\n",
        (16, "SURR32", 8),
        "41",
        (4, CC_INVALID),
    ),
    **_converted(
        "CU41 low surrogate invalid",
        "         CU41  2,4\n",
        (16, "LOW32", 4),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CU41 above 10FFFF invalid",
        "         CU41  2,4\n",
        (16, "OVER32", 4),
        "",
        (0, CC_INVALID),
    ),
    "CU41 clears bit 32": (
        _pairs(16, ("U32", 16)) + "         O     4,BIT32\n"
        "         CU41  2,4\n" + _offset(4, "U32+16"),
        {4: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
}

UTF32_TO_UTF16: Mapping[str, Case] = {
    **_converted(
        "CU42 exhausted",
        "         CU42  2,4\n",
        (16, "U32", 16),
        UTF16_TEXT,
        (16, CC_EXHAUSTED),
    ),
    **_converted(
        "CU42 first operand full",
        "         CU42  2,4\n",
        (9, "U32", 16),
        "0041 00E9 20AC",
        (12, CC_FULL),
    ),
    **_converted(
        "CU42 high surrogate invalid",
        "         CU42  2,4\n",
        (16, "SURR32", 8),
        "0041",
        (4, CC_INVALID),
    ),
    **_converted(
        "CU42 low surrogate invalid",
        "         CU42  2,4\n",
        (16, "LOW32", 4),
        "",
        (0, CC_INVALID),
    ),
    **_converted(
        "CU42 all ones invalid",
        "         CU42  2,4\n",
        (16, "ONES32", 4),
        "",
        (0, CC_INVALID),
    ),
}


def _search(character: int, end: str, start: str, instruction: str) -> str:
    return (
        f"         LLILL 0,{character}\n"
        f"         LA    2,{end}\n"
        f"         LA    4,{start}\n"
        f"         {instruction} 2,4\n"
    )


SEARCHES: Mapping[str, Case] = {
    "SRST found": (_search(0xC3, "STR+5", "STR", "SRST "), {}, CC_FOUND),
    "SRST found registers": (
        _search(0xC3, "STR+5", "STR", "SRST ")
        + _offset(2, "STR+2")
        + _offset(4, "STR"),
        {2: HIGH_FILL, 4: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "SRST not found": (_search(0xFF, "STR+5", "STR", "SRST "), {}, CC_NOT_FOUND),
    "SRST not found registers": (
        _search(0xFF, "STR+5", "STR", "SRST ")
        + _offset(2, "STR+5")
        + _offset(4, "STR"),
        {2: HIGH_FILL, 4: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "SRST end excluded": (_search(0xC3, "STR+2", "STR", "SRST "), {}, CC_NOT_FOUND),
    "SRST equal addresses": (
        _search(0xC1, "STR", "STR", "SRST "),
        {},
        CC_NOT_FOUND,
    ),
    "SRST clears bit 32 of R1 only": (
        "         LLILL 0,X'C3'\n"
        "         LA    2,STR+5\n"
        "         LA    4,STR\n"
        "         O     4,BIT32\n"
        "         SRST  2,4\n" + _offset(2, "STR+2") + _offset(4, "STR"),
        {2: HIGH_FILL, 4: HIGH_FILL | BIT_32},
        SLR_NONZERO_CC,
    ),
    "SRSTU found": (_search(0x42, "HSTR+6", "HSTR", "SRSTU"), {}, CC_FOUND),
    "SRSTU found registers": (
        _search(0x42, "HSTR+6", "HSTR", "SRSTU")
        + _offset(2, "HSTR+2")
        + _offset(4, "HSTR"),
        {2: HIGH_FILL, 4: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "SRSTU compares two bytes": (
        _search(0x42, "HSTR2+4", "HSTR2", "SRSTU") + _offset(2, "HSTR2+2"),
        {2: HIGH_FILL},
        SLR_EQUAL_CC,
    ),
    "SRSTU not found": (
        _search(0x44, "HSTR+6", "HSTR", "SRSTU"),
        {},
        CC_NOT_FOUND,
    ),
    "SRSTU end excluded": (
        _search(0x43, "HSTR+4", "HSTR", "SRSTU"),
        {},
        CC_NOT_FOUND,
    ),
    "SRSTU odd end includes the character before it": (
        _search(0x42, "HSTR+3", "HSTR", "SRSTU"),
        {},
        CC_FOUND,
    ),
    "SRSTU odd end stops after it": (
        _search(0x43, "HSTR+3", "HSTR", "SRSTU"),
        {},
        CC_NOT_FOUND,
    ),
    "SRSTU end one past the start examines the first character": (
        _search(0x41, "HSTR+1", "HSTR", "SRSTU"),
        {},
        CC_FOUND,
    ),
    "SRSTU character in bits 48-63": (
        "         LLILL 0,X'FFFF'\n"
        "         LA    2,HSTR+6\n"
        "         LA    4,HSTR\n"
        "         SRSTU 2,4\n",
        {0: 0xFFFF},
        CC_NOT_FOUND,
    ),
}

CASES: Mapping[str, Case] = {
    **UTF8_TO_UTF16,
    **UTF8_TO_UTF32,
    **UTF16_TO_UTF8,
    **UTF16_TO_UTF32,
    **UTF32_TO_UTF8,
    **UTF32_TO_UTF16,
    **SEARCHES,
}

SPECIFICATION_EXCEPTIONS: Mapping[str, Case] = {
    "SRST GR0 bits 32-55": (
        "         LLILF 0,X'100'\n"
        "         LGHI  2,5\n"
        "         LGHI  4,1\n"
        "         SRST  2,4\n",
        {0: 0x100, 2: 5, 4: 1},
        INITIAL_CC,
    ),
    "SRSTU GR0 bits 32-47": (
        "         LLILF 0,X'10042'\n"
        "         LGHI  2,6\n"
        "         LGHI  4,2\n"
        "         SRSTU 2,4\n",
        {0: 0x10042, 2: 6, 4: 2},
        INITIAL_CC,
    ),
}
