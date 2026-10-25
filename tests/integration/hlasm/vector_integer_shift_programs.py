# pyright: standard
"""Vector integer shift and rotate programs: each builds vector registers from SRC (bytes X'00' to X'3F') and the constants below, then stores them to OUT with VST or VSTM; expected images from the Principles of Operation, SA22-7832-14 chapter 22, page cited per case."""

from collections.abc import Mapping

from tests.integration.hlasm.vector_memory_programs import image, line
from tests.integration.hlasm.vector_register_programs import dc

type Case = tuple[str, bytes]

DATA = (
    dc("SHFT", "8001FF7F", "1234C00F", "80000001", "7FFFFFFE")
    + dc("CNTS", "00070903", "010F1104", "1F20213F", "4005FF08")
    + dc("MASK", "0F0F00FF", "FFFF0000", "F0F0F0F0", "00000001")
    + dc("BCNT", "0301F200", "040D0607", "0801FA03", "0C050E0F")
    + dc("BYC", "00000000", "000000AF", "FFFFFFFF", "FFFFFFFF")
    + dc("OP2", "01234567", "89ABCDEF", "FEDCBA98", "76543210")
    + dc("OP3", "F0E1D2C3", "B4A59687", "78695A4B", "3C2D1E0A")
)


def _sources(*pairs: tuple[int, str]) -> str:
    return "".join(line("VL", f"{v},{label}") for v, label in pairs)


CASES: Mapping[str, Case] = {
    "VESL VESRL VESRA by the address's low bits modulo the width, ES 0-3, counts 0, width-1 and past the width, negative elements, V1 equal to V3 (PoO 22-29, 22-30)": (
        _sources((2, "SHFT"))
        + line("VESLB", "3,2,0")
        + line("VESLH", "4,2,15")
        + line("VESLF", "5,2,33")
        + line("VESLG", "6,2,63")
        + line("VESRLB", "7,2,7")
        + line("VESRLH", "8,2,16")
        + line("VESRLF", "9,2,31")
        + line("VESRLG", "10,2,65")
        + line("VESRAB", "11,2,9")
        + line("VESRAH", "12,2,15")
        + line("VESRAF", "13,2,4")
        + line("VESRAG", "14,2,63")
        + line("VSTM", "3,14,OUT")
        + line("VESRLG", "2,2,4095")
        + line("VST", "2,OUT+192"),
        image(
            "8001FF7F 1234C00F 80000001 7FFFFFFE",
            "80008000 00008000 00008000 80000000",
            "0003FEFE 2469801E 00000002 FFFFFFFC",
            "80000000 00000000 00000000 00000000",
            "01000100 00000100 01000000 00010101",
            "8001FF7F 1234C00F 80000001 7FFFFFFE",
            "00000001 00000000 00000001 00000000",
            "4000FFBF 891A6007 40000000 BFFFFFFF",
            "C000FF3F 091AE007 C0000000 3FFFFFFF",
            "FFFFFFFF 0000FFFF FFFF0000 0000FFFF",
            "F8001FF7 01234C00 F8000000 07FFFFFF",
            "FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF",
            "00000000 00000001 00000000 00000001",
        ),
    ),
    "VERLL by the address (base register included) and VERLLV by each V3 element, counts differing per element and past the width, V1 equal to V3 (PoO 22-27, 22-28)": (
        _sources((2, "SHFT"), (3, "CNTS"))
        + line("LGHI", "9,100")
        + line("VERLLB", "4,2,0")
        + line("VERLLB", "5,2,7")
        + line("VERLLH", "6,2,17")
        + line("VERLLF", "7,2,5(9)")
        + line("VERLLG", "8,2,63")
        + line("VERLLVB", "9,2,3")
        + line("VERLLVH", "10,2,3")
        + line("VERLLVF", "11,2,3")
        + line("VERLLVG", "12,2,3")
        + line("VLR", "13,2")
        + line("VERLLG", "13,13,4094")
        + line("VERLLVG", "3,2,3")
        + line("VSTM", "4,13,OUT")
        + line("VST", "3,OUT+160"),
        image(
            "8001FF7F 1234C00F 80000001 7FFFFFFE",
            "4080FFBF 091A6087 40000080 BFFFFF7F",
            "0003FEFF 2468801F 00010002 FFFEFFFD",
            "03FEFF00 69801E24 00000300 FFFFFCFF",
            "C000FFBF 891A6007 40000000 BFFFFFFF",
            "8080FFFB 241A81F0 40000080 7FFFFFFE",
            "00C0FBFF 091A00FC 80008000 FFEFFEFF",
            "000FFBFC 234C00F1 C0000000 FFFFFE7F",
            "001FF7F1 234C00F8 0000017F FFFFFE80",
            "E0007FDF C48D3003 A0000000 5FFFFFFF",
            "001FF7F1 234C00F8 0000017F FFFFFE80",
        ),
    ),
    "VESLV VESRLV VESRAV by each V3 element modulo the width, ES 0-3, counts differing per element, negative elements, V1 equal to V2 and to V3 (PoO 22-29, 22-30)": (
        _sources((2, "SHFT"), (3, "CNTS"))
        + line("VESLVB", "4,2,3")
        + line("VESLVH", "5,2,3")
        + line("VESLVF", "6,2,3")
        + line("VESLVG", "7,2,3")
        + line("VESRLVB", "8,2,3")
        + line("VESRLVH", "9,2,3")
        + line("VESRLVF", "10,2,3")
        + line("VESRLVG", "11,2,3")
        + line("VESRAVB", "12,2,3")
        + line("VESRAVH", "13,2,3")
        + line("VESRAVF", "14,2,3")
        + line("VESRAVG", "15,2,3")
        + line("VSTM", "4,15,OUT")
        + line("VLR", "16,3")
        + line("VESLVH", "3,2,3")
        + line("VESRAVB", "2,2,16")
        + line("VSTM", "2,3,OUT+192"),
        image(
            "8080FEF8 240080F0 00000080 7FE080FE",
            "0080FBF8 000000F0 80008000 FFE0FE00",
            "000FFBF8 234C00F0 80000000 FFFFFE00",
            "001FF7F1 234C00F0 0000017F FFFFFE00",
            "80007F0F 09006000 01000000 7F0701FE",
            "01001FEF 00000C00 80000000 03FF00FF",
            "10003FEF 01234C00 00000001 007FFFFF",
            "08001FF7 F1234C00 00800000 017FFFFF",
            "8000FF0F 0900E000 FF000000 7FFFFFFE",
            "FF00FFEF 0000FC00 80000000 03FFFFFF",
            "F0003FEF 01234C00 FFFFFFFF 007FFFFF",
            "F8001FF7 F1234C00 FF800000 017FFFFF",
            "8000FF0F 0900E000 FF000000 7FFFFFFE",
            "0080FBF8 000000F0 80008000 FFE0FE00",
        ),
    ),
    "VERIM rotates V2 by I4 modulo the width and inserts under a partial V3 mask, I4 -1 and 300 modulo the width, V1 equal to V2 and to V3, sources unchanged (PoO 22-28, 22-29)": (
        _sources((1, "SRC"), (2, "SHFT"), (3, "MASK"))
        + line("VLR", "4,1")
        + line("VERIMB", "4,2,3,3")
        + line("VLR", "5,1")
        + line("VERIMH", "5,2,3,17")
        + line("VLR", "6,1")
        + line("VERIMF", "6,2,3,-1")
        + line("VLR", "7,1")
        + line("VERIMG", "7,2,3,300")
        + line("VLR", "8,2")
        + line("VERIMH", "8,8,3,4")
        + line("VLR", "9,3")
        + line("VERIMF", "9,2,9,8")
        + line("VSTM", "4,9,OUT")
        + line("VSTM", "2,3,OUT+96"),
        image(
            "040802FB 90A10607 08090A0B 0C0D0E0F",
            "000302FF 24680607 08090A0B 0C0D0E0F",
            "000002BF 891A0607 C8090A0B 0C0D0E0F",
            "0C000200 1FF70607 F8F9EA0B 0C0D0E0F",
            "8008FFFF 2341C00F 00000011 7FFFFFFF",
            "010F0080 34C00000 00000080 00000001",
            "8001FF7F 1234C00F 80000001 7FFFFFFE",
            "0F0F00FF FFFF0000 F0F0F0F0 00000001",
        ),
    ),
    "VSL VSRL VSRA shift each byte by bits 5-7 of the matching V3 byte, counts differing per byte and all equal, neighbour bits in, the sign into the leftmost byte, V1 equal to V2 and to V3 (PoO 22-31, 22-32, 22-33)": (
        _sources((1, "SRC"), (2, "SHFT"), (3, "BCNT"))
        + line("VREPIB", "4,3")
        + line("VSL", "5,2,3")
        + line("VSRL", "6,2,3")
        + line("VSRA", "7,2,3")
        + line("VSL", "8,2,4")
        + line("VSRL", "9,2,4")
        + line("VSRA", "10,2,4")
        + line("VSRA", "11,1,3")
        + line("VSL", "12,1,3")
        + line("VSRA", "2,2,3")
        + line("VSL", "3,1,3")
        + line("VSTM", "5,12,OUT")
        + line("VSTM", "2,3,OUT+128"),
        image(
            "0003FD7F 239803C0 8000000B FFFFFF00",
            "10007F7F F191D380 80000000 17FFFFFF",
            "F0007F7F F191D380 80000000 17FFFFFF",
            "000FFBF8 91A6007C 0000000B FFFFFFF0",
            "10003FEF E2469801 F0000000 2FFFFFFF",
            "F0003FEF E2469801 F0000000 2FFFFFFF",
            "00004003 3020140C 08044241 B060341C",
            "00020803 40A08184 08122858 C0A18380",
            "F0007F7F F191D380 80000000 17FFFFFF",
            "00020803 40A08184 08122858 C0A18380",
        ),
    ),
    "VSLB VSRLB VSRAB shift by the byte count in bits 1-4 of V3 byte 7 only: 5, 15 and 0 bytes, zeros or the sign in, V1 equal to V2 and to V3 (PoO 22-31, 22-32, 22-33)": (
        _sources((1, "SRC"), (2, "SHFT"), (3, "BYC"))
        + line("VREPIB", "4,255")
        + line("VREPIB", "5,X'87'")
        + line("VSLB", "6,2,3")
        + line("VSRLB", "7,2,3")
        + line("VSRAB", "8,2,3")
        + line("VSLB", "9,2,4")
        + line("VSRLB", "10,2,4")
        + line("VSRAB", "11,2,4")
        + line("VSRAB", "12,2,5")
        + line("VSRAB", "13,1,4")
        + line("VSLB", "2,2,3")
        + line("VSRLB", "3,1,3")
        + line("VSTM", "6,13,OUT")
        + line("VSTM", "2,3,OUT+128"),
        image(
            "34C00F80 0000017F FFFFFE00 00000000",
            "00000000 008001FF 7F1234C0 0F800000",
            "FFFFFFFF FF8001FF 7F1234C0 0F800000",
            "FE000000 00000000 00000000 00000000",
            "00000000 00000000 00000000 00000080",
            "FFFFFFFF FFFFFFFF FFFFFFFF FFFFFF80",
            "8001FF7F 1234C00F 80000001 7FFFFFFE",
            "00000000 00000000 00000000 00000000",
            "34C00F80 0000017F FFFFFE00 00000000",
            "00000000 00000102 03040506 0708090A",
        ),
    ),
    "VSLD VSRD VSLDB take 128 bits of V2 || V3 across the 256-bit boundary: the PoO's VSLD example, counts 0, 4, 7, byte indexes 0, 9, 15, I4 256 as its 8-bit image, V1 equal to V2 and to V3 (PoO 22-31, 22-32, 22-33)": (
        _sources((2, "OP2"), (3, "OP3"))
        + line("VSLD", "4,2,3,4")
        + line("VSLD", "5,2,3,0")
        + line("VSLD", "6,2,3,7")
        + line("VSRD", "7,2,3,0")
        + line("VSRD", "8,2,3,7")
        + line("VSRD", "9,2,3,4")
        + line("VSLDB", "10,2,3,0")
        + line("VSLDB", "11,2,3,15")
        + line("VSLDB", "12,2,3,9")
        + line("VSLD", "13,2,3,256")
        + line("VLR", "14,3")
        + line("VSRD", "3,2,3,1")
        + line("VSLDB", "2,2,14,3")
        + line("VSTM", "2,13,OUT"),
        image(
            "6789ABCD EFFEDCBA 98765432 10F0E1D2",
            "7870E961 DA52CB43 BC34AD25 9E168F05",
            "12345678 9ABCDEFF EDCBA987 6543210F",
            "01234567 89ABCDEF FEDCBA98 76543210",
            "91A2B3C4 D5E6F7FF 6E5D4C3B 2A190878",
            "F0E1D2C3 B4A59687 78695A4B 3C2D1E0A",
            "21E1C3A5 87694B2D 0EF0D2B4 96785A3C",
            "0F0E1D2C 3B4A5968 778695A4 B3C2D1E0",
            "01234567 89ABCDEF FEDCBA98 76543210",
            "10F0E1D2 C3B4A596 8778695A 4B3C2D1E",
            "DCBA9876 543210F0 E1D2C3B4 A5968778",
            "01234567 89ABCDEF FEDCBA98 76543210",
        ),
    ),
}


def _refused(mnemonic: str, operands: str) -> str:
    return line(mnemonic, operands) + line("VST", "1,OUT")


CHECKS: Mapping[str, str] = {
    "VERIM element size 4 (PoO 22-28)": _refused("VERIM", "1,2,3,1,4"),
    "VERLL element size 4 (PoO 22-28)": _refused("VERLL", "1,3,1,4"),
    "VERLLV element size 4 (PoO 22-28)": _refused("VERLLV", "1,2,3,4"),
    "VESL element size 4 (PoO 22-29)": _refused("VESL", "1,3,1,4"),
    "VESLV element size 4 (PoO 22-29)": _refused("VESLV", "1,2,3,4"),
    "VESRA element size 4 (PoO 22-30)": _refused("VESRA", "1,3,1,4"),
    "VESRAV element size 4 (PoO 22-30)": _refused("VESRAV", "1,2,3,4"),
    "VESRL element size 4 (PoO 22-30)": _refused("VESRL", "1,3,1,4"),
    "VESRLV element size 4 (PoO 22-30)": _refused("VESRLV", "1,2,3,4"),
    "VSLD I4 8, bit 4 set (PoO 22-32)": _refused("VSLD", "1,2,3,8"),
    "VSLD I4 -1, image X'FF' (PoO 22-32)": _refused("VSLD", "1,2,3,-1"),
    "VSRD I4 X'80', bit 0 set (PoO 22-33)": _refused("VSRD", "1,2,3,X'80'"),
}
