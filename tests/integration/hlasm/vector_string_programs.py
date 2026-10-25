# pyright: standard
"""Vector string programs: each loads vector registers from the constants below (EBCDIC text, halfword and word strings, range limits and controls, substring lengths in byte 7), runs one instruction per result, stores its V1 to OUT+16k with VST and its condition code to OUT+192+k with IPM and STC; expected images from the Principles of Operation, SA22-7832-14 chapter 23, page cited per case."""

from collections.abc import Mapping, Sequence

from tests.integration.hlasm.vector_memory_programs import FILL, image, line
from tests.integration.hlasm.vector_register_programs import cc, dc

type Case = tuple[str, bytes]

RESULT_ROWS = 12
CC_AT = 16 * RESULT_ROWS

DATA = (
    dc("TEXT", "C8C5D3D3", "D600E6D6", "D9D3C440", "C1E340F1")
    + dc("VOWL", "C1C5C9D6", "E4C1C5C9", "D6E4C1C5", "C9D6E4C1")
    + dc("ZTWO", "C1C200C4", "C5C6C7C8", "C9D1D2D3", "D4D5D6D7")
    + dc("MISS", "C4D6C700", "00000000", "00000000", "00000000")
    + dc("DSET", "C4C4C4C4", "C4C4C4C4", "C4C4C4C4", "C4C4C4C4")
    + dc("NOZR", "C1C2C3C4", "C5C6C7C8", "C9D1D2D3", "D4D5D6D7")
    + dc("ZERO", "00000000", "00000000", "00000000", "00000000")
    + dc("PSET", "D7D7D7D7", "D7D7D7D7", "D7D7D7D7", "D7D7D7D7")
    + dc("HALF", "00410042", "00430000", "00440045", "00460047")
    + dc("HSET", "00440043", "00440043", "00440043", "00440043")
    + dc("WRDS", "00000001", "00000002", "00000003", "00000004")
    + dc("WSET", "00000004", "00000004", "00000004", "00000004")
    + dc("NAME", "E2C5C1D9", "C3C840C9", "D540E2E3", "D9C9D5C7")
    + dc("REVS", "C7D5C9D9", "E3E240D5", "C940C8C3", "D9C1C5E2")
    + dc("ZTW3", "C1C200E7", "C5C6C7C8", "C9D1D2D3", "D4D5D6D7")
    + dc("ZTWN", "E7E800D8", "D8D8D8D8", "D8D8D8D8", "D8D8D8D8")
    + dc("SAME", "E2C5C1D9", "C3C840C9", "D540E2E3", "D9C9D5C7")
    + dc("DIFF", "E2C5C1D9", "C3C840D6", "D540E2E3", "D9C9D5C7")
    + dc("LOWR", "C5C2C3C4", "C5C6C7C8", "C9D1D2D3", "D4D5D67F")
    + dc("HIGH", "C5C2C3C4", "C5C6C7C8", "C9D1D2D3", "D4D5D680")
    + dc("HLF2", "00410042", "00430000", "00440045", "00010047")
    + dc("BYTZ", "41420043", "44000045", "46474849", "00000000")
    + dc("HIBT", "41804200", "C1C2C3C4", "C5C6C7C8", "C9D1D2D3")
    + dc("HIBH", "00418000", "00420000", "00430044", "00450046")
    + dc("MIXD", "6060E7F9", "6060C160", "60E96060", "F560607B")
    + dc("RNGL", "C1C9F0F9", "00000000", "00000000", "00000000")
    + dc("RNGC", "A0C0A0C0", "00000000", "00000000", "00000000")
    + dc("ZSTR", "E7E8E900", "C1C2C3C4", "C5C6C7C8", "C9D1D2D3")
    + dc("ALLC", "E0E00000", "00000000", "00000000", "00000000")
    + dc("HMIX", "002D0031", "002D0042", "00000061", "00000000")
    + dc("HRNL", "0041005A", "00300039", "00000000", "00000000")
    + dc("HRNC", "A000C000", "A000C000", "00000000", "00000000")
    + dc("WMIX", "00000005", "00000100", "00000020", "00000015")
    + dc("WRNL", "00000010", "00000020", "00000100", "00000100")
    + dc("WRNC", "A0000000", "C0000000", "80000000", "80000000")
    + dc("HAYS", "E3C8C540", "C3C1E340", "E2C1E340", "D6D540C1")
    + dc("NEED", "E2C1E300", "00000000", "00000000", "00000000")
    + dc("LEN3", "00000000", "00000003", "00000000", "00000000")
    + dc("NEDA", "D6D540C1", "40D4C1E3", "00000000", "00000000")
    + dc("LEN8", "00000000", "00000008", "00000000", "00000000")
    + dc("ABCS", "C1C2C300", "00000000", "00000000", "00000000")
    + dc("LEN0", "00000000", "00000000", "00000000", "00000000")
    + dc("TAIL", "D6D540C1", "00000000", "00000000", "00000000")
    + dc("LEN4", "00000000", "00000004", "00000000", "00000000")
    + dc("ATSB", "C1E30000", "00000000", "00000000", "00000000")
    + dc("LEN2", "00000000", "00000002", "00000000", "00000000")
    + dc("LEN16", "00000000", "00000010", "00000000", "00000000")
    + dc("LENX", "FFFFFFFF", "FFFFFF03", "FFFFFFFF", "FFFFFFFF")
    + dc("HAYZ", "E3C8C500", "C3C1E340", "E2C1E340", "D6D540C1")
    + dc("NEDZ", "D6D500D8", "00000000", "00000000", "00000000")
    + dc("HAYE", "E3C8C540", "C3C1E300", "E2C1E340", "D6D540C1")
    + dc("CATS", "C3C1E300", "00000000", "00000000", "00000000")
    + dc("HAYH", "00410042", "00430044", "00450046", "00470048")
    + dc("NDLH", "00470048", "00490000", "00000000", "00000000")
    + dc("LEN6", "00000000", "00000006", "00000000", "00000000")
    + dc("HAYW", "00000001", "00000002", "00000003", "00000004")
    + dc("NDLW", "00000002", "00000003", "00000000", "00000000")
    + dc("NDW2", "00000004", "00000005", "00000000", "00000000")
)


def _sources(*pairs: tuple[int, str]) -> str:
    return "".join(line("VL", f"{v},{label}") for v, label in pairs)


def _found(mnemonic: str, operands: str, at: int, preset: bool = False) -> str:
    target = operands.split(",")[0]
    return (
        (line("LHI", "9,5") + line("LTR", "9,9") if preset else "")
        + line(mnemonic, operands)
        + cc(9, CC_AT + at)
        + line("VST", f"{target},OUT+{16 * at}")
    )


def _index(byte: int) -> str:
    return f"00000000 000000{byte:02X} 00000000 00000000"


def _expected(results: Sequence[str], codes: str) -> bytes:
    unused = f"{FILL:02X}" * 16 * (RESULT_ROWS - len(results))
    return image(*results, unused, codes)


CASES: Mapping[str, Case] = {
    "VFAE byte: first element equal to any V3 element, IN, RT masks, ZS order with a tie at a zero, no match 16, last element, CS 0 leaves the CC (PoO 23-2, 23-3)": (
        _sources(
            (1, "TEXT"),
            (2, "VOWL"),
            (3, "ZTWO"),
            (4, "MISS"),
            (16, "DSET"),
            (17, "NOZR"),
            (18, "ZERO"),
            (19, "PSET"),
        )
        + _found("VFAEBS", "5,1,2", 0)
        + _found("VFAEZBS", "6,1,2", 1)
        + _found("VFAE", "7,1,2,0,11", 2)
        + _found("VFAE", "8,1,2,0,5", 3)
        + _found("VFAE", "9,1,2,0,15", 4)
        + _found("VFAEZBS", "10,3,4", 5)
        + _found("VFAEZBS", "11,3,16", 6)
        + _found("VFAEBS", "12,17,18", 7)
        + _found("VFAEBS", "13,17,19", 8)
        + _found("VFAEB", "14,1,2", 9, preset=True),
        _expected(
            [
                _index(1),
                _index(1),
                _index(0),
                "00FF0000 FF0000FF 00000000 FF000000",
                "FF00FFFF 00FFFF00 FFFFFFFF 00FFFFFF",
                _index(2),
                _index(2),
                _index(16),
                _index(15),
                _index(1),
            ],
            "01020201 02000003 0102",
        ),
    ),
    "VFAE halfword and word: byte index of the element, RT and IN masks, ZS, an RT mask without the zero search's indications, V1 equal to V2 and to V3 (PoO 23-2, 23-3)": (
        _sources(
            (1, "TEXT"),
            (2, "VOWL"),
            (3, "TEXT"),
            (4, "VOWL"),
            (16, "HALF"),
            (17, "HSET"),
            (18, "WRDS"),
            (19, "WSET"),
        )
        + _found("VFAEHS", "5,16,17", 0)
        + _found("VFAEZHS", "6,16,17", 1)
        + _found("VFAEFS", "7,18,19", 2)
        + _found("VFAE", "8,18,19,2,7", 3)
        + _found("VFAE", "9,16,17,1,12", 4, preset=True)
        + _found("VFAE", "10,1,2,0,7", 5)
        + _found("VFAEZBS", "2,1,2", 6)
        + _found("VFAEBS", "3,3,4", 7),
        _expected(
            [
                _index(4),
                _index(4),
                _index(12),
                "00000000 00000000 00000000 FFFFFFFF",
                "FFFFFFFF 0000FFFF 0000FFFF FFFFFFFF",
                "00FF0000 FF0000FF 00000000 FF000000",
                _index(1),
                _index(1),
            ],
            "01020101 02020201",
        ),
    ),
    "VFEE: first equal element, ZS zero before, after and at the same element as a match, none 16, last element, halfword and word, V1 equal to V2 (PoO 23-3, 23-4)": (
        _sources(
            (1, "NAME"),
            (2, "REVS"),
            (3, "ZTWO"),
            (4, "ZTW3"),
            (16, "DSET"),
            (17, "ZTWN"),
            (18, "NOZR"),
            (19, "PSET"),
            (20, "ZERO"),
            (21, "HALF"),
            (22, "HSET"),
            (23, "WRDS"),
            (24, "WSET"),
        )
        + _found("VFEEBS", "5,1,2", 0)
        + _found("VFEEZBS", "6,3,4", 1)
        + _found("VFEEZBS", "7,3,16", 2)
        + _found("VFEEZBS", "8,3,17", 3)
        + _found("VFEEBS", "9,18,20", 4)
        + _found("VFEEBS", "10,18,19", 5)
        + _found("VFEEZB", "11,3,16", 6, preset=True)
        + _found("VFEEHS", "12,21,22", 7)
        + _found("VFEEZHS", "13,21,22", 8)
        + _found("VFEEFS", "14,23,24", 9)
        + _found("VFEEBS", "1,1,2", 10),
        _expected(
            [
                _index(3),
                _index(0),
                _index(2),
                _index(2),
                _index(16),
                _index(15),
                _index(2),
                _index(8),
                _index(6),
                _index(12),
                _index(3),
            ],
            "01020000 03010201 000101",
        ),
    ),
    "VFENE: first unequal element, CC 1 low and 2 high as unsigned, all equal 16, ZS zero before a mismatch, a zero element unequal to V3 counts as the mismatch, halfword and word, V1 equal to V3 (PoO 23-4, 23-5)": (
        _sources(
            (1, "SAME"),
            (2, "DIFF"),
            (3, "LOWR"),
            (4, "HIGH"),
            (16, "ZTWO"),
            (17, "ZTW3"),
            (18, "NOZR"),
            (19, "HALF"),
            (20, "HLF2"),
            (21, "WRDS"),
            (22, "WSET"),
        )
        + _found("VFENEBS", "5,1,2", 0)
        + _found("VFENEBS", "6,2,1", 1)
        + _found("VFENEBS", "7,3,4", 2)
        + _found("VFENEBS", "8,1,1", 3)
        + _found("VFENEZBS", "9,16,16", 4)
        + _found("VFENEZBS", "10,16,17", 5)
        + _found("VFENEZBS", "11,16,18", 6)
        + _found("VFENEHS", "12,19,20", 7)
        + _found("VFENEZHS", "13,19,20", 8)
        + _found("VFENEFS", "14,21,22", 9)
        + _found("VFENEB", "15,1,2", 10, preset=True)
        + _found("VFENEBS", "2,1,2", 11),
        _expected(
            [
                _index(7),
                _index(7),
                _index(15),
                _index(16),
                _index(2),
                _index(2),
                _index(2),
                _index(12),
                _index(6),
                _index(0),
                _index(7),
                _index(7),
            ],
            "01020103 00000102 00010201",
        ),
    ),
    "VISTR keeps elements before the first zero element and zeroes the rest, a zero byte inside a nonzero halfword or word is kept, an element with only its leftmost bit set is not zero, CC 0 found and 3 none, V1 equal to V2 (PoO 23-5, 23-6)": (
        _sources(
            (1, "TEXT"),
            (2, "NOZR"),
            (3, "BYTZ"),
            (4, "ZERO"),
            (16, "HIBT"),
            (17, "HIBH"),
        )
        + _found("VISTRBS", "5,1", 0)
        + _found("VISTRBS", "6,2", 1)
        + _found("VISTRHS", "7,3", 2)
        + _found("VISTRFS", "8,3", 3)
        + _found("VISTRB", "9,3", 4, preset=True)
        + _found("VISTRBS", "10,4", 5)
        + _found("VISTRBS", "11,16", 6)
        + _found("VISTRHS", "12,17", 7)
        + _found("VISTRBS", "1,1", 8),
        _expected(
            [
                "C8C5D3D3 D6000000 00000000 00000000",
                "C1C2C3C4 C5C6C7C8 C9D1D2D3 D4D5D6D7",
                "41420043 44000045 46474849 00000000",
                "41420043 44000045 46474849 00000000",
                "41420000 00000000 00000000 00000000",
                _index(0),
                "41804200 00000000 00000000 00000000",
                "00418000 00420000 00000000 00000000",
                "C8C5D3D3 D6000000 00000000 00000000",
            ],
            "00030000 02000000 00",
        ),
    ),
    "VSTRC byte: ranges from even-odd limit pairs with E L H controls, IN, RT masks, ZS order, no control bits never true and all three always true, CS 0 leaves the CC (PoO 23-6, 23-7, 23-8)": (
        _sources(
            (1, "MIXD"),
            (2, "RNGL"),
            (3, "RNGC"),
            (4, "ZSTR"),
            (16, "ZTWO"),
            (17, "ZERO"),
            (18, "ALLC"),
        )
        + _found("VSTRCBS", "5,1,2,3", 0)
        + _found("VSTRC", "6,1,2,3,0,9", 1)
        + _found("VSTRC", "7,1,2,3,0,5", 2)
        + _found("VSTRC", "8,1,2,3,0,15", 3)
        + _found("VSTRCZBS", "9,4,2,3", 4)
        + _found("VSTRCZBS", "10,16,2,3", 5)
        + _found("VSTRCBS", "11,1,2,17", 6)
        + _found("VSTRCBS", "12,1,2,18", 7)
        + _found("VSTRC", "13,1,2,18,0,9", 8)
        + _found("VSTRCB", "14,1,2,3", 9, preset=True),
        _expected(
            [
                _index(3),
                _index(0),
                "000000FF 0000FF00 00000000 FF000000",
                "FFFFFF00 FFFF00FF FFFFFFFF 00FFFFFF",
                _index(3),
                _index(0),
                _index(16),
                _index(0),
                _index(16),
                _index(3),
            ],
            "01010101 00020301 0302",
        ),
    ),
    "VSTRC halfword and word: ranges, an equal-only pair, RT masks, ZS, V1 equal to V2, V3 and V4 (PoO 23-6, 23-7, 23-8)": (
        _sources(
            (1, "MIXD"),
            (2, "RNGL"),
            (3, "RNGC"),
            (4, "MIXD"),
            (16, "HMIX"),
            (17, "HRNL"),
            (18, "HRNC"),
            (19, "WMIX"),
            (20, "WRNL"),
            (21, "WRNC"),
            (22, "RNGL"),
            (23, "RNGC"),
        )
        + _found("VSTRCHS", "5,16,17,18", 0)
        + _found("VSTRCZHS", "6,16,17,18", 1)
        + _found("VSTRC", "7,16,17,18,1,4", 2, preset=True)
        + _found("VSTRCFS", "8,19,20,21", 3)
        + _found("VSTRC", "9,19,20,21,2,5", 4)
        + _found("VSTRCBS", "1,1,2,3", 5)
        + _found("VSTRCBS", "22,4,22,3", 6)
        + _found("VSTRCBS", "23,4,2,23", 7),
        _expected(
            [
                _index(2),
                _index(2),
                "0000FFFF 0000FFFF 00000000 00000000",
                _index(4),
                "00000000 FFFFFFFF FFFFFFFF FFFFFFFF",
                _index(3),
                _index(3),
                _index(3),
            ],
            "01020201 01010101",
        ),
    ),
    "VSTRS byte, ZS 0: full match, partial match at the end, last byte, none, length 0, a match ending at byte 15, first of several, whole register, V4 bits other than byte 7 ignored (PoO 23-8, 23-9, 23-10)": (
        _sources(
            (1, "HAYS"),
            (2, "NEED"),
            (3, "LEN3"),
            (4, "NEDA"),
            (16, "LEN8"),
            (17, "ABCS"),
            (18, "MISS"),
            (19, "LEN0"),
            (20, "TAIL"),
            (21, "LEN4"),
            (22, "ATSB"),
            (23, "LEN2"),
            (24, "LEN16"),
            (25, "LENX"),
        )
        + _found("VSTRSB", "5,1,2,3", 0)
        + _found("VSTRSB", "6,1,4,16", 1)
        + _found("VSTRSB", "7,1,17,3", 2)
        + _found("VSTRSB", "8,1,18,3", 3)
        + _found("VSTRSB", "9,1,18,19", 4)
        + _found("VSTRSB", "10,1,20,21", 5)
        + _found("VSTRSB", "11,1,22,23", 6)
        + _found("VSTRSB", "12,1,1,24", 7)
        + _found("VSTRSB", "13,1,2,25", 8),
        _expected(
            [
                _index(8),
                _index(12),
                _index(15),
                _index(16),
                _index(0),
                _index(12),
                _index(5),
                _index(0),
                _index(8),
            ],
            "02030300 02020202 02",
        ),
    ),
    "VSTRS ZS 1: a zero in V2 ends the string and stops partial matches, a zero in V3 shortens the substring, length 0 from a zero first byte, V1 equal to V2, V3 and V4 (PoO 23-8, 23-9, 23-11)": (
        _sources(
            (1, "HAYZ"),
            (2, "NEED"),
            (3, "LEN3"),
            (4, "HAYS"),
            (16, "NEDZ"),
            (17, "LEN4"),
            (18, "NEDA"),
            (19, "LEN8"),
            (20, "HAYE"),
            (21, "ZERO"),
            (22, "CATS"),
            (23, "LEN3"),
        )
        + _found("VSTRSZB", "5,1,2,3", 0)
        + _found("VSTRSZB", "6,4,16,17", 1)
        + _found("VSTRSZB", "7,4,18,19", 2)
        + _found("VSTRSZB", "8,20,18,19", 3)
        + _found("VSTRSB", "9,20,18,19", 4)
        + _found("VSTRSZB", "10,20,21,3", 5)
        + _found("VSTRSZB", "11,20,22,3", 6)
        + _found("VSTRSZB", "4,4,2,3", 7)
        + _found("VSTRSZB", "2,20,2,3", 8)
        + _found("VSTRSZB", "23,22,22,23", 9),
        _expected(
            [
                _index(16),
                _index(12),
                _index(12),
                _index(16),
                _index(12),
                _index(0),
                _index(4),
                _index(8),
                _index(16),
                _index(0),
            ],
            "01020301 03020202 0102",
        ),
    ),
    "VSTRS halfword and word: full and partial matches at element positions, ZS on elements (PoO 23-8, 23-9, 23-10, 23-11)": (
        _sources(
            (1, "HAYH"),
            (2, "NDLH"),
            (3, "LEN6"),
            (4, "LEN4"),
            (16, "HAYW"),
            (17, "NDLW"),
            (18, "NDW2"),
            (19, "LEN8"),
            (20, "LEN2"),
            (21, "LEN16"),
        )
        + _found("VSTRSZH", "5,1,2,3", 0)
        + _found("VSTRSH", "6,1,2,4", 1)
        + _found("VSTRSH", "7,1,2,3", 2)
        + _found("VSTRSF", "8,16,17,19", 3)
        + _found("VSTRSZF", "9,16,18,19", 4)
        + _found("VSTRSF", "10,16,18,19", 5)
        + _found("VSTRSZH", "11,1,1,21", 6)
        + _found("VSTRSF", "12,16,17,4", 7),
        _expected(
            [
                _index(12),
                _index(12),
                _index(12),
                _index(4),
                _index(12),
                _index(12),
                _index(0),
                _index(4),
            ],
            "03020302 03030202",
        ),
    ),
}

CHECKS: Mapping[str, str] = {
    "VFAE element size 3": line("VFAE", "1,2,3,3,1") + line("VST", "1,OUT"),
    "VFEE element size 3": line("VFEE", "1,2,3,3,1") + line("VST", "1,OUT"),
    "VFENE element size 3": line("VFENE", "1,2,3,3,1") + line("VST", "1,OUT"),
    "VISTR element size 3": line("VISTR", "1,2,3,1") + line("VST", "1,OUT"),
    "VSTRC element size 3": line("VSTRC", "1,2,3,4,3,1") + line("VST", "1,OUT"),
    "VSTRS element size 3": line("VSTRS", "1,2,3,4,3") + line("VST", "1,OUT"),
    "VFEE M5 bit 0 (PoO 23-3)": line("VFEE", "1,2,3,0,8") + line("VST", "1,OUT"),
    "VFENE M5 bit 1 (PoO 23-5)": line("VFENE", "1,2,3,0,4") + line("VST", "1,OUT"),
    "VISTR M5 bit 2 (PoO 23-6)": line("VISTR", "1,2,0,2") + line("VST", "1,OUT"),
    "VSTRS M6 bit 3 (PoO 23-9)": line("VSTRS", "1,2,3,4,0,1") + line("VST", "1,OUT"),
    "VSTRS M6 bit 0 (PoO 23-9)": line("VSTRS", "1,2,3,4,0,8") + line("VST", "1,OUT"),
}
