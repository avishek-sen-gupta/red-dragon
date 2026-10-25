# pyright: standard
"""Vector integer logical, compare, minimum and maximum, complement and count programs: each builds vector registers from SRC (bytes X'00' to X'3F') and the constants below, then stores them to OUT with VST or VSTM and condition codes with IPM and STC; expected images from the Principles of Operation, SA22-7832-14 chapter 22, page cited per case."""

from collections.abc import Mapping

from tests.integration.hlasm.vector_memory_programs import image, line
from tests.integration.hlasm.vector_register_programs import cc, dc

type Case = tuple[str, bytes]

DATA = (
    dc("LOGP", "00FF00FF", "0F0F3C3C", "80017FFF", "5A5AA5A5")
    + dc("LOGR", "0F0F0F0F", "00FF00FF", "7FFF8000", "FFFF0000")
    + dc("LOGC", "33333333", "55555555", "0000FFFF", "12345678")
    + dc("CMPA", "807F01FF", "80007FFF", "80000000", "00000001")
    + dc("CMPB", "7F8001FF", "7FFF8000", "7FFFFFFF", "00000001")
    + dc("ONEY", "00010203", "84058687", "08090A0B", "0C0D0E0F")
    + dc("NEGS", "807F00FF", "80000001", "80000000", "FFFFFFFF")
    + dc("BITS", "000180FF", "0FF00000", "00000000", "00010000")
)


def _sources(*pairs: tuple[int, str]) -> str:
    return "".join(line("VL", f"{v},{label}") for v, label in pairs)


def _set_cc_2() -> str:
    return line("LHI", "9,5") + line("LTR", "9,9")


CASES: Mapping[str, Case] = {
    "VN VNC VNN VNO VNOT VNX VO VOC VX, V1 equal to V2 and to V3 (PoO 22-6, 22-15, 22-25, 22-26)": (
        _sources((2, "LOGP"), (3, "LOGR"))
        + line("VN", "4,2,3")
        + line("VNC", "5,2,3")
        + line("VNN", "6,2,3")
        + line("VNO", "7,2,3")
        + line("VNOT", "8,2")
        + line("VNX", "9,2,3")
        + line("VO", "10,2,3")
        + line("VOC", "11,2,3")
        + line("VX", "12,2,3")
        + line("VN", "2,2,3")
        + line("VOC", "3,2,3")
        + line("VSTM", "4,12,OUT")
        + line("VSTM", "2,3,OUT+144"),
        image(
            "000F000F 000F003C 00010000 5A5A0000",
            "00F000F0 0F003C00 80007FFF 0000A5A5",
            "FFF0FFF0 FFF0FFC3 FFFEFFFF A5A5FFFF",
            "F000F000 F000C300 00000000 00005A5A",
            "FF00FF00 F0F0C3C3 7FFE8000 A5A55A5A",
            "F00FF00F F00FC33C 00010000 5A5A5A5A",
            "0FFF0FFF 0FFF3CFF FFFFFFFF FFFFA5A5",
            "F0FFF0FF FF0FFF3C 80017FFF 5A5AFFFF",
            "0FF00FF0 0FF03CC3 FFFEFFFF A5A5A5A5",
            "000F000F 000F003C 00010000 5A5A0000",
            "F0FFF0FF FF0FFF3C 80017FFF 5A5AFFFF",
        ),
    ),
    "VEVAL selects I5 bit (V2 V3 V4) per bit: AND, MAJOR, none, all, NOR, AND(A,NOR(B,C)), I5 256 and -1 as their low 8 bits, XOR into V4 (PoO 22-13, 22-14)": (
        _sources((2, "LOGP"), (3, "LOGR"), (4, "LOGC"))
        + line("VEVAL", "5,2,3,4,1")
        + line("VEVAL", "6,2,3,4,X'17'")
        + line("VEVAL", "7,2,3,4,0")
        + line("VEVAL", "8,2,3,4,255")
        + line("VEVAL", "9,2,3,4,X'80'")
        + line("VEVAL", "10,2,3,4,X'08'")
        + line("VEVAL", "11,2,3,4,256")
        + line("VEVAL", "12,2,3,4,-1")
        + line("VEVAL", "4,2,3,4,X'69'")
        + line("VSTM", "5,12,OUT")
        + line("VST", "4,OUT+128"),
        image(
            "00030003 00050014 00000000 12100000",
            "033F033F 055F147D 0001FFFF 5A7E0420",
            "00000000 00000000 00000000 00000000",
            "FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF",
            "C000C000 A0008200 00000000 00000802",
            "00C000C0 0A002800 80000000 0000A185",
            "00000000 00000000 00000000 00000000",
            "FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF",
            "3CC33CC3 5AA56996 FFFE0000 B791F3DD",
        ),
    ),
    "VCEQ sets equal elements to ones and, with CS only, CC 0 all, 1 some, 3 none (PoO 22-9)": (
        _sources((2, "CMPA"), (3, "CMPB"), (6, "SRC"), (7, "SRC+16"))
        + line("VCEQBS", "4,2,2")
        + cc(9, 192)
        + line("VCEQHS", "5,2,3")
        + cc(9, 193)
        + line("VCEQFS", "8,6,7")
        + cc(9, 194)
        + _set_cc_2()
        + line("VCEQG", "10,2,3")
        + cc(9, 195)
        + line("VCEQQS", "11,2,2")
        + cc(9, 196)
        + line("VCEQF", "3,2,3")
        + line("VSTM", "4,5,OUT")
        + line("VST", "8,OUT+32")
        + line("VSTM", "10,11,OUT+48")
        + line("VST", "3,OUT+80"),
        image(
            "FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF",
            "0000FFFF 00000000 00000000 FFFFFFFF",
            "00000000 00000000 00000000 00000000",
            "00000000 00000000 00000000 00000000",
            "FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF",
            "00000000 00000000 00000000 FFFFFFFF",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "00010302 00EEEEEE EEEEEEEE EEEEEEEE",
        ),
    ),
    "VCH VCHL compare signed and logical, high-bit elements, CC 0 1 3 with CS (PoO 22-9, 22-10)": (
        _sources((2, "CMPA"), (3, "CMPB"), (6, "SRC"), (7, "SRC+16"))
        + line("VCHBS", "4,2,3")
        + cc(9, 192)
        + line("VCHLBS", "5,2,3")
        + cc(9, 193)
        + line("VCHHS", "8,7,6")
        + cc(9, 194)
        + line("VCHLFS", "10,6,7")
        + cc(9, 195)
        + line("VCHQS", "11,2,3")
        + cc(9, 196)
        + line("VCHLQS", "12,2,3")
        + cc(9, 197)
        + line("VCHGS", "13,2,3")
        + cc(9, 198)
        + line("VCHLG", "3,2,3")
        + _set_cc_2()
        + line("VCHH", "2,2,3")
        + cc(9, 199)
        + line("VSTM", "4,5,OUT")
        + line("VST", "8,OUT+32")
        + line("VSTM", "10,13,OUT+48")
        + line("VST", "3,OUT+112")
        + line("VST", "2,OUT+128"),
        image(
            "00FF0000 00FFFF00 00FFFFFF 00000000",
            "FF000000 FF0000FF FF000000 00000000",
            "FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF",
            "00000000 00000000 00000000 00000000",
            "00000000 00000000 00000000 00000000",
            "FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF",
            "00000000 00000000 00000000 00000000",
            "FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF",
            "0000FFFF 0000FFFF 0000FFFF FFFFFFFF",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "01010003 03000302 EEEEEEEE EEEEEEEE",
        ),
    ),
    "VEC VECL compare byte 7, halfword 3, word 1, doubleword 0, quadword 0 (PoO 22-8)": (
        _sources((2, "SRC"), (3, "ONEY"), (4, "CMPA"), (5, "CMPB"))
        + line("VECB", "2,3")
        + cc(9, 0)
        + line("VECLB", "2,3")
        + cc(9, 1)
        + line("VECH", "2,3")
        + cc(9, 2)
        + line("VECLH", "2,3")
        + cc(9, 3)
        + line("VECF", "2,3")
        + cc(9, 4)
        + line("VECLF", "2,3")
        + cc(9, 5)
        + line("VECG", "2,3")
        + cc(9, 6)
        + line("VECLG", "2,3")
        + cc(9, 7)
        + line("VECQ", "2,3")
        + cc(9, 8)
        + line("VECLQ", "2,3")
        + cc(9, 9)
        + line("VECG", "4,5")
        + cc(9, 10)
        + line("VECLG", "4,5")
        + cc(9, 11)
        + line("VECQ", "4,5")
        + cc(9, 12)
        + line("VECLQ", "4,5")
        + cc(9, 13)
        + line("VECF", "2,2")
        + cc(9, 14),
        image("02010201 02010101 01010102 010200EE"),
    ),
    "VTM sets CC 0 for zero bits or a zero mask, 1 mixed, 3 ones, V1 equal to V2 (PoO 22-37)": (
        _sources((2, "LOGP"))
        + line("VZERO", "5")
        + line("VGBM", "6,X'8000'")
        + line("VGBM", "7,X'4000'")
        + line("VGBM", "8,X'C000'")
        + line("VTM", "2,5")
        + cc(9, 0)
        + line("VTM", "2,6")
        + cc(9, 1)
        + line("VTM", "2,7")
        + cc(9, 2)
        + line("VTM", "2,8")
        + cc(9, 3)
        + line("VTM", "2,2")
        + cc(9, 4),
        image("00000301 03EEEEEE"),
    ),
    "VMN VMNL VMX VMXL signed and logical, ES 0-4, V1 equal to V2 and V3 (PoO 22-18)": (
        _sources((2, "CMPA"), (3, "CMPB"))
        + line("VMXB", "4,2,3")
        + line("VMXLB", "5,2,3")
        + line("VMNH", "6,2,3")
        + line("VMNLH", "7,2,3")
        + line("VMXF", "8,2,3")
        + line("VMNLG", "9,2,3")
        + line("VMXG", "10,2,3")
        + line("VMXQ", "11,2,3")
        + line("VMNLQ", "12,2,3")
        + line("VMXLQ", "13,2,3")
        + line("VMNQ", "14,2,3")
        + line("VMNF", "2,2,3")
        + line("VMXLH", "3,2,3")
        + line("VSTM", "4,14,OUT")
        + line("VSTM", "2,3,OUT+176"),
        image(
            "7F7F01FF 7F007F00 7F000000 00000001",
            "808001FF 80FF80FF 80FFFFFF 00000001",
            "807F01FF 80008000 8000FFFF 00000001",
            "7F8001FF 7FFF7FFF 7FFF0000 00000001",
            "7F8001FF 7FFF8000 7FFFFFFF 00000001",
            "7F8001FF 7FFF8000 7FFFFFFF 00000001",
            "7F8001FF 7FFF8000 7FFFFFFF 00000001",
            "7F8001FF 7FFF8000 7FFFFFFF 00000001",
            "7F8001FF 7FFF8000 7FFFFFFF 00000001",
            "807F01FF 80007FFF 80000000 00000001",
            "807F01FF 80007FFF 80000000 00000001",
            "807F01FF 80007FFF 80000000 00000001",
            "807F01FF 80008000 8000FFFF 00000001",
        ),
    ),
    "VLC VLP complement and absolute value, most negative unchanged, ES 0-4 (PoO 22-17)": (
        _sources((2, "NEGS"))
        + line("VLCB", "3,2")
        + line("VLPB", "4,2")
        + line("VLCH", "5,2")
        + line("VLPH", "6,2")
        + line("VLCF", "7,2")
        + line("VLPF", "8,2")
        + line("VLCG", "9,2")
        + line("VLPG", "10,2")
        + line("VLCQ", "11,2")
        + line("VLPQ", "12,2")
        + line("VLPF", "2,2")
        + line("VSTM", "3,12,OUT")
        + line("VST", "2,OUT+160"),
        image(
            "80810001 800000FF 80000000 01010101",
            "807F0001 80000001 80000000 01010101",
            "7F81FF01 8000FFFF 80000000 00010001",
            "7F8100FF 80000001 80000000 00010001",
            "7F80FF01 7FFFFFFF 80000000 00000001",
            "7F80FF01 7FFFFFFF 80000000 00000001",
            "7F80FF00 7FFFFFFF 7FFFFFFF 00000001",
            "7F80FF00 7FFFFFFF 7FFFFFFF 00000001",
            "7F80FF00 7FFFFFFE 7FFFFFFF 00000001",
            "7F80FF00 7FFFFFFE 7FFFFFFF 00000001",
            "7F80FF01 7FFFFFFF 80000000 00000001",
        ),
    ),
    "VPOPCT counts one bits per element, V1 equal to V2 (PoO 22-26)": (
        _sources((2, "BITS"))
        + line("VPOPCTB", "3,2")
        + line("VPOPCTH", "4,2")
        + line("VPOPCTF", "5,2")
        + line("VPOPCTG", "6,2")
        + line("VPOPCTF", "2,2")
        + line("VSTM", "2,6,OUT"),
        image(
            "0000000A 00000008 00000000 00000001",
            "00010108 04040000 00000000 00010000",
            "00010009 00080000 00000000 00010000",
            "0000000A 00000008 00000000 00000001",
            "00000000 00000012 00000000 00000001",
        ),
    ),
    "VCLZ VCTZ count leading and trailing zeros, the element's bits when zero, ES 0-4 (PoO 22-11, 22-12)": (
        _sources((2, "BITS"))
        + line("VZERO", "13")
        + line("VCLZB", "3,2")
        + line("VCLZH", "4,2")
        + line("VCLZF", "5,2")
        + line("VCLZG", "6,2")
        + line("VCLZQ", "7,2")
        + line("VCTZB", "8,2")
        + line("VCTZH", "9,2")
        + line("VCTZF", "10,2")
        + line("VCTZG", "11,2")
        + line("VCTZQ", "12,2")
        + line("VCLZQ", "14,13")
        + line("VCTZQ", "13,13")
        + line("VCTZH", "2,2")
        + line("VSTM", "2,14,OUT"),
        image(
            "00000000 00040010 00100010 00000010",
            "08070000 04000808 08080808 08070808",
            "000F0000 00040010 00100010 000F0010",
            "0000000F 00000004 00000020 0000000F",
            "00000000 0000000F 00000000 0000002F",
            "00000000 00000000 00000000 0000000F",
            "08000700 00040808 08080808 08000808",
            "00000000 00040010 00100010 00000010",
            "00000000 00000014 00000020 00000010",
            "00000000 00000014 00000000 00000010",
            "00000000 00000000 00000000 00000010",
            "00000000 00000000 00000000 00000080",
            "00000000 00000000 00000000 00000080",
        ),
    ),
}

CHECKS: Mapping[str, str] = {
    "VCEQ element size 5": line("VCEQ", "1,2,3,5,1") + line("VST", "1,OUT"),
    "VCH element size 5": line("VCH", "1,2,3,5,1") + line("VST", "1,OUT"),
    "VCHL element size 5": line("VCHL", "1,2,3,5,0") + line("VST", "1,OUT"),
    "VEC element size 5": line("VEC", "1,2,5") + line("VST", "1,OUT"),
    "VECL element size 5": line("VECL", "1,2,5") + line("VST", "1,OUT"),
    "VMN element size 5": line("VMN", "1,2,3,5") + line("VST", "1,OUT"),
    "VMNL element size 5": line("VMNL", "1,2,3,5") + line("VST", "1,OUT"),
    "VMX element size 5": line("VMX", "1,2,3,5") + line("VST", "1,OUT"),
    "VMXL element size 5": line("VMXL", "1,2,3,5") + line("VST", "1,OUT"),
    "VLC element size 5": line("VLC", "1,2,5") + line("VST", "1,OUT"),
    "VLP element size 5": line("VLP", "1,2,5") + line("VST", "1,OUT"),
    "VPOPCT element size 4 (PoO 22-26)": line("VPOPCT", "1,2,4") + line("VST", "1,OUT"),
    "VCLZ element size 5": line("VCLZ", "1,2,5") + line("VST", "1,OUT"),
    "VCTZ element size 5": line("VCTZ", "1,2,5") + line("VST", "1,OUT"),
}
