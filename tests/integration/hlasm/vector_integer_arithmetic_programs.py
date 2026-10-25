# pyright: standard
"""Vector integer add, subtract, average, multiply, Galois-field multiply, checksum, sum and divide programs: each builds vector registers from the constants below, then stores the results to OUT with VSTM; expected images from the Principles of Operation, SA22-7832-14 chapter 22, page cited per case. TRAPS end in a vector-processing exception: the VXC each leaves in the FPC, with V1 still holding SRC."""

from collections.abc import Mapping

from tests.integration.hlasm.vector_memory_programs import image, line
from tests.integration.hlasm.vector_register_programs import dc

type Case = tuple[str, bytes]
type Trap = tuple[str, int]


def _sources(*pairs: tuple[int, str]) -> str:
    return "".join(line("VL", f"{v},{label}") for v, label in pairs)


DATA = (
    dc("ADDA", "FF7F8001", "FFFF7FFF", "FFFFFFFF", "7FFFFFFF")
    + dc("ADDB", "01810180", "00018001", "00000001", "80000001")
    + dc("MULA", "FF807F02", "FFFE8000", "FFFFFFF0", "80000001")
    + dc("MULB", "02FF7F80", "7FFF0003", "00000010", "FFFFFFFF")
    + dc("MULC", "FF01807F", "FFFF8000", "7FFFFFFF", "FFFFFFFF")
    + dc("ONES", "FFFFFFFF", "FFFFFFFF", "FFFFFFFF", "FFFFFFFF")
    + dc("ONEZ", "FFFFFFFF", "FFFFFFFF", "FFFFFFFF", "FFFFFFFE")
    + dc("CKSA", "FFFFFFFF", "00000002", "80000000", "80000001")
    + dc("CKSB", "12345678", "00000003", "9ABCDEF0", "00000000")
    + dc("DIVA", "80000000", "FFFFFFF9", "00000007", "7FFFFFFF")
    + dc("DIVB", "FFFFFFFF", "00000002", "FFFFFFFE", "00000000")
    + dc("DIVC", "00000003", "00000002", "FFFFFFFE", "00000005")
    + dc("DIVD", "00000001", "00000002", "00000003", "00000000")
    + dc("DIVE", "00000000", "00000005", "00000000", "00000000")
    + dc("ZERO", "00000000", "00000000", "00000000", "00000000")
    + dc("QMIN", "80000000", "00000000", "00000000", "00000000")
)


CASES: Mapping[str, Case] = {
    "VA VS add and subtract per element with wraparound, ES 0-4, V1 equal to V2 and V3 (PoO 22-4, 22-33)": (
        _sources((2, "ADDA"), (3, "ADDB"))
        + line("VAB", "16,2,3")
        + line("VAH", "17,2,3")
        + line("VAF", "18,2,3")
        + line("VAG", "19,2,3")
        + line("VAQ", "20,2,3")
        + line("VSB", "21,2,3")
        + line("VSH", "22,2,3")
        + line("VSF", "23,2,3")
        + line("VSG", "24,2,3")
        + line("VSQ", "25,2,3")
        + line("VLR", "26,2")
        + line("VAF", "26,26,3")
        + line("VLR", "27,3")
        + line("VSQ", "27,2,27")
        + line("VSTM", "16,27,OUT"),
        image(
            "00008181 FF00FF00 FFFFFF00 FFFFFF00",
            "01008181 00000000 FFFF0000 FFFF0000",
            "01008181 00010000 00000000 00000000",
            "01008182 00010000 00000001 00000000",
            "01008182 00010001 00000001 00000000",
            "FEFE7F81 FFFEFFFE FFFFFFFE FFFFFFFE",
            "FDFE7E81 FFFEFFFE FFFFFFFE FFFFFFFE",
            "FDFE7E81 FFFDFFFE FFFFFFFE FFFFFFFE",
            "FDFE7E81 FFFDFFFE FFFFFFFD FFFFFFFE",
            "FDFE7E81 FFFDFFFE FFFFFFFD FFFFFFFE",
            "01008181 00010000 00000000 00000000",
            "FDFE7E81 FFFDFFFE FFFFFFFD FFFFFFFE",
        ),
    ),
    "VACC VSCBI carry out and borrow indication per element, ES 0-4, V1 equal to V2 and V3 (PoO 22-5, 22-34)": (
        _sources((2, "ADDA"), (3, "ADDB"))
        + line("VACCB", "16,2,3")
        + line("VACCH", "17,2,3")
        + line("VACCF", "18,2,3")
        + line("VACCG", "19,2,3")
        + line("VACCQ", "20,2,3")
        + line("VSCBIB", "21,2,3")
        + line("VSCBIH", "22,2,3")
        + line("VSCBIF", "23,2,3")
        + line("VSCBIG", "24,2,3")
        + line("VSCBIQ", "25,2,3")
        + line("VLR", "26,2")
        + line("VACCH", "26,26,3")
        + line("VLR", "27,2")
        + line("VSCBIG", "27,3,27")
        + line("VSTM", "16,27,OUT"),
        image(
            "01010000 00010001 00000001 00000001",
            "00010000 00010001 00000001 00000001",
            "00000001 00000001 00000001 00000001",
            "00000000 00000001 00000000 00000001",
            "00000000 00000000 00000000 00000001",
            "01000100 01010001 01010101 00010101",
            "00010001 00010000 00010001 00000001",
            "00000001 00000001 00000001 00000000",
            "00000000 00000001 00000000 00000001",
            "00000000 00000000 00000000 00000001",
            "00010000 00010001 00000001 00000001",
            "00000000 00000000 00000000 00000000",
        ),
    ),
    "VAC VACCC VSBI VSBCBI take only bit 127 of V4 as the carry or borrow, V1 equal to V4 (PoO 22-5, 22-6, 22-35)": (
        _sources((2, "ADDA"), (3, "ADDB"), (4, "MULA"), (5, "ONES"), (6, "ONEZ"))
        + line("VACQ", "16,2,3,5")
        + line("VACQ", "17,2,3,6")
        + line("VACCCQ", "18,2,3,5")
        + line("VACCCQ", "19,3,3,5")
        + line("VACCCQ", "20,2,4,6")
        + line("VSBIQ", "21,2,3,5")
        + line("VSBIQ", "22,3,2,6")
        + line("VSBCBIQ", "23,2,3,5")
        + line("VSBCBIQ", "24,3,2,5")
        + line("VSBCBIQ", "25,2,2,6")
        + line("VSBCBIQ", "26,2,2,5")
        + line("VLR", "27,5")
        + line("VACQ", "27,2,3,27")
        + line("VSTM", "16,27,OUT"),
        image(
            "01008182 00010001 00000001 00000001",
            "01008182 00010001 00000001 00000000",
            "00000000 00000000 00000000 00000001",
            "00000000 00000000 00000000 00000000",
            "00000000 00000000 00000000 00000001",
            "FDFE7E81 FFFDFFFE FFFFFFFD FFFFFFFE",
            "0201817E 00020001 00000002 00000001",
            "00000000 00000000 00000000 00000001",
            "00000000 00000000 00000000 00000000",
            "00000000 00000000 00000000 00000000",
            "00000000 00000000 00000000 00000001",
            "01008182 00010001 00000001 00000001",
        ),
    ),
    "VAVG VAVGL round the average up over one extra bit, signed and logical, ES 0-4, V1 equal to V2 and V3 (PoO 22-7)": (
        _sources((2, "MULA"), (3, "MULB"))
        + line("VAVGB", "16,2,3")
        + line("VAVGH", "17,2,3")
        + line("VAVGF", "18,2,3")
        + line("VAVGG", "19,2,3")
        + line("VAVGQ", "20,2,3")
        + line("VAVGLB", "21,2,3")
        + line("VAVGLH", "22,2,3")
        + line("VAVGLF", "23,2,3")
        + line("VAVGLG", "24,2,3")
        + line("VAVGLQ", "25,2,3")
        + line("VLR", "26,2")
        + line("VAVGH", "26,26,3")
        + line("VLR", "27,2")
        + line("VAVGLQ", "27,3,27")
        + line("VSTM", "16,27,OUT"),
        image(
            "01C07FC1 3FFFC002 00000000 C0000000",
            "01407F41 3FFFC002 00000000 C0000000",
            "013FFF41 3FFEC002 00000000 C0000000",
            "013FFF41 BFFEC002 00000000 C0000000",
            "013FFF41 BFFEC002 00000000 C0000000",
            "81C07F41 BFFF4002 80808080 C0808080",
            "81407F41 BFFF4002 80008000 C0008000",
            "813FFF41 BFFEC002 80000000 C0000000",
            "813FFF41 BFFEC002 80000000 C0000000",
            "813FFF41 BFFEC002 00000000 C0000000",
            "01407F41 3FFFC002 00000000 C0000000",
            "813FFF41 BFFEC002 00000000 C0000000",
        ),
    ),
    "VCKSM adds the carry out of each word addition back into bit 31, word 1 only, V1 equal to V3 (PoO 22-7, 22-8)": (
        _sources((2, "CKSA"), (3, "CKSB"), (4, "ONES"))
        + line("VCKSM", "16,2,3")
        + line("VCKSM", "17,4,4")
        + line("VLR", "18,3")
        + line("VCKSM", "18,2,18")
        + line("VSTM", "16,18,OUT"),
        image(
            "00000000 00000007 00000000 00000000",
            "00000000 FFFFFFFF 00000000 00000000",
            "00000000 00000007 00000000 00000000",
        ),
    ),
    "VSUM VSUMG VSUMQ add the sub-elements of each word, doubleword or quadword and V3's rightmost one (PoO 22-36, 22-37)": (
        _sources((2, "MULA"), (3, "MULB"), (4, "ONES"))
        + line("VSUMB", "16,2,3")
        + line("VSUMH", "17,2,3")
        + line("VSUMGH", "18,2,3")
        + line("VSUMGF", "19,2,3")
        + line("VSUMQF", "20,2,3")
        + line("VSUMQG", "21,2,3")
        + line("VSUMQG", "22,4,4")
        + line("VLR", "23,3")
        + line("VSUMQF", "23,2,23")
        + line("VSTM", "16,23,OUT"),
        image(
            "00000280 00000280 000003FD 00000180",
            "0001FE02 00018001 0001FFFF 00018000",
            "00000000 0002FE83 00000000 00037FEF",
            "00000002 7F7DFF05 00000002 7FFFFFF0",
            "00000000 00000000 00000004 7F7EFEF2",
            "00000000 00000001 FF807F04 7FFE8000",
            "00000000 00000002 FFFFFFFF FFFFFFFD",
            "00000000 00000000 00000004 7F7EFEF2",
        ),
    ),
    "VML VMH VMLH low and signed or logical high halves on negative elements, ES B H F, V1 equal to V2 (PoO 22-21, 22-22)": (
        _sources((2, "MULA"), (3, "MULB"))
        + line("VMLB", "16,2,3")
        + line("VMHB", "17,2,3")
        + line("VMLHB", "18,2,3")
        + line("VMLHW", "19,2,3")
        + line("VMHH", "20,2,3")
        + line("VMLHH", "21,2,3")
        + line("VMLF", "22,2,3")
        + line("VMHF", "23,2,3")
        + line("VMLHF", "24,2,3")
        + line("VLR", "25,2")
        + line("VMHB", "25,25,3")
        + line("VSTM", "16,25,OUT"),
        image(
            "FE800100 81020000 00000000 800000FF",
            "FF003FFF FF000000 000000FF 000000FF",
            "017F3F01 7EFD0000 0000000F 7F000000",
            "80807F00 00028000 0000FF00 8000FFFF",
            "FFFE3F41 FFFFFFFE 0000FFFF 0000FFFF",
            "02FD3F41 7FFE0001 0000000F 7FFF0000",
            "063F7F00 7FFB8000 FFFFFF00 7FFFFFFF",
            "FFFE81BD FFFF4001 FFFFFFFF 00000000",
            "02FE013D 7FFE4004 0000000F 80000000",
            "FF003FFF FF000000 000000FF 000000FF",
        ),
    ),
    "VML VMH VMLH low and signed or logical high halves on negative elements, ES G Q, V1 equal to V2 (PoO 22-21, 22-22)": (
        _sources((2, "MULA"), (3, "MULB"))
        + line("VMLG", "16,2,3")
        + line("VMHG", "17,2,3")
        + line("VMLHG", "18,2,3")
        + line("VMLQ", "19,2,3")
        + line("VMHQ", "20,2,3")
        + line("VMLHQ", "21,2,3")
        + line("VLR", "22,2")
        + line("VMHG", "22,22,3")
        + line("VSTM", "16,22,OUT"),
        image(
            "C03DBD0A 7FFB8000 80000020 7FFFFFFF",
            "FFFE81BD 08FF3A01 FFFFFFFF FFFFFEF8",
            "02FE013D 88FE3A04 00000010 FFFFFEF7",
            "43750060 00007EFA 80000020 7FFFFFFF",
            "FFFE81BD 08FF3A01 C33D3C8A C90AB6EE",
            "02FE013D 88FE3A04 C33D3C9B C90AB6ED",
            "FFFE81BD 08FF3A01 FFFFFFFF FFFFFEF8",
        ),
    ),
    "VMAL VMAH VMALH add V4 to the double-wide product, the sum overflowing the element, ES B H F, V1 equal to V4 (PoO 22-19, 22-20)": (
        _sources((2, "MULA"), (3, "MULB"), (4, "MULC"))
        + line("VMALB", "16,2,3,4")
        + line("VMAHB", "17,2,3,4")
        + line("VMALHB", "18,2,3,4")
        + line("VMALHW", "19,2,3,4")
        + line("VMAHH", "20,2,3,4")
        + line("VMALHH", "21,2,3,4")
        + line("VMALF", "22,2,3,4")
        + line("VMAHF", "23,2,3,4")
        + line("VMALHF", "24,2,3,4")
        + line("VLR", "25,4")
        + line("VMALHF", "25,2,3,25")
        + line("VSTM", "16,25,OUT"),
        image(
            "FD81817F 80018000 7FFFFFFF 7FFFFFFE",
            "FF003EFF FF00FF00 00FFFFFE 00FFFFFF",
            "027F3F01 7FFE0000 0000000F 80000001",
            "7F81FF7F 00010000 7FFFFEFF 7FFFFFFE",
            "FFFE3F40 FFFFFFFE 0000FFFF 0000FFFF",
            "02FE3F41 7FFF0002 00000010 80000001",
            "0540FF7F 7FFB0000 7FFFFEFF 7FFFFFFE",
            "FFFE81BD FFFF4001 00000000 00000000",
            "02FE013E 7FFE4005 00000010 80000001",
            "02FE013E 7FFE4005 00000010 80000001",
        ),
    ),
    "VMAL VMAH VMALH add V4 to the double-wide product, the sum overflowing the element, ES G Q, V1 equal to V4 (PoO 22-19, 22-20)": (
        _sources((2, "MULA"), (3, "MULB"), (4, "MULC"))
        + line("VMALG", "16,2,3,4")
        + line("VMAHG", "17,2,3,4")
        + line("VMALHG", "18,2,3,4")
        + line("VMALQ", "19,2,3,4")
        + line("VMAHQ", "20,2,3,4")
        + line("VMALHQ", "21,2,3,4")
        + line("VLR", "22,4")
        + line("VMALHQ", "22,2,3,22")
        + line("VSTM", "16,22,OUT"),
        image(
            "BF3F3D8A 7FFB0000 00000020 7FFFFFFE",
            "FFFE81BD 08FF3A01 FFFFFFFF FFFFFEF9",
            "02FE013D 88FE3A05 00000010 FFFFFEF8",
            "427680DF FFFFFEFB 00000020 7FFFFFFE",
            "FFFE81BD 08FF3A01 C33D3C8A C90AB6EE",
            "02FE013D 88FE3A04 C33D3C9B C90AB6EE",
            "02FE013D 88FE3A04 C33D3C9B C90AB6EE",
        ),
    ),
    "VME VMLE VMO VMLO multiply even or odd elements into double-wide products, ES B H, V1 equal to V3 (PoO 22-23, 22-24)": (
        _sources((2, "MULA"), (3, "MULB"))
        + line("VMEB", "16,2,3")
        + line("VMLEB", "17,2,3")
        + line("VMOB", "18,2,3")
        + line("VMLOB", "19,2,3")
        + line("VMEH", "20,2,3")
        + line("VMLEH", "21,2,3")
        + line("VMOH", "22,2,3")
        + line("VMLOH", "23,2,3")
        + line("VLR", "24,3")
        + line("VMOB", "24,2,24")
        + line("VSTM", "16,24,OUT"),
        image(
            "FFFE3F01 FF810000 00000000 00800000",
            "01FE3F01 7E810000 00000000 7F800000",
            "0080FF00 00020000 0000FF00 0000FFFF",
            "7F800100 FD020000 00000F00 000000FF",
            "FFFE8080 FFFF0002 00000000 00008000",
            "02FD8080 7FFE0002 00000000 7FFF8000",
            "3F417F00 FFFE8000 FFFFFF00 FFFFFFFF",
            "3F417F00 00018000 000FFF00 0000FFFF",
            "0080FF00 00020000 0000FF00 0000FFFF",
        ),
    ),
    "VME VMLE VMO VMLO multiply even or odd elements into double-wide products, ES F G, V1 equal to V3 (PoO 22-23, 22-24)": (
        _sources((2, "MULA"), (3, "MULB"))
        + line("VMEF", "16,2,3")
        + line("VMLEF", "17,2,3")
        + line("VMOF", "18,2,3")
        + line("VMLOF", "19,2,3")
        + line("VMEG", "20,2,3")
        + line("VMLEG", "21,2,3")
        + line("VMOG", "22,2,3")
        + line("VMLOG", "23,2,3")
        + line("VLR", "24,3")
        + line("VMOF", "24,2,24")
        + line("VSTM", "16,24,OUT"),
        image(
            "FFFE81BD 063F7F00 FFFFFFFF FFFFFF00",
            "02FE013D 063F7F00 0000000F FFFFFF00",
            "FFFF4001 7FFB8000 00000000 7FFFFFFF",
            "7FFE4004 7FFB8000 80000000 7FFFFFFF",
            "FFFE81BD 08FF3A01 C03DBD0A 7FFB8000",
            "02FE013D 88FE3A04 C03DBD0A 7FFB8000",
            "FFFFFFFF FFFFFEF8 80000020 7FFFFFFF",
            "00000010 FFFFFEF7 80000020 7FFFFFFF",
            "FFFF4001 7FFB8000 00000000 7FFFFFFF",
        ),
    ),
    "VMAE VMALE VMAO VMALO add the double-wide V4 element to the even or odd product, carry ignored, ES B H, V1 equal to V4 (PoO 22-20, 22-21)": (
        _sources((2, "MULA"), (3, "MULB"), (4, "MULC"))
        + line("VMAEB", "16,2,3,4")
        + line("VMALEB", "17,2,3,4")
        + line("VMAOB", "18,2,3,4")
        + line("VMALOB", "19,2,3,4")
        + line("VMAEH", "20,2,3,4")
        + line("VMALEH", "21,2,3,4")
        + line("VMAOH", "22,2,3,4")
        + line("VMALOH", "23,2,3,4")
        + line("VLR", "24,4")
        + line("VMAEH", "24,2,3,24")
        + line("VSTM", "16,24,OUT"),
        image(
            "FEFFBF80 FF808000 7FFFFFFF 007FFFFF",
            "00FFBF80 7E808000 7FFFFFFF 7F7FFFFF",
            "FF817F7F 00018000 7FFFFEFF FFFFFFFE",
            "7E81817F FD018000 7FFF0EFF FFFF00FE",
            "FF0000FF FFFE8002 7FFFFFFF 00007FFF",
            "01FF00FF 7FFD8002 7FFFFFFF 7FFF7FFF",
            "3E42FF7F FFFE0000 7FFFFEFF FFFFFFFE",
            "3E42FF7F 00010000 800FFEFF 0000FFFE",
            "FF0000FF FFFE8002 7FFFFFFF 00007FFF",
        ),
    ),
    "VMAE VMALE VMAO VMALO add the double-wide V4 element to the even or odd product, carry ignored, ES F G, V1 equal to V4 (PoO 22-20, 22-21)": (
        _sources((2, "MULA"), (3, "MULB"), (4, "MULC"))
        + line("VMAEF", "16,2,3,4")
        + line("VMALEF", "17,2,3,4")
        + line("VMAOF", "18,2,3,4")
        + line("VMALOF", "19,2,3,4")
        + line("VMAEG", "20,2,3,4")
        + line("VMALEG", "21,2,3,4")
        + line("VMAOG", "22,2,3,4")
        + line("VMALOG", "23,2,3,4")
        + line("VLR", "24,4")
        + line("VMAEG", "24,2,3,24")
        + line("VSTM", "16,24,OUT"),
        image(
            "FF00023D 063EFF00 7FFFFFFF FFFFFEFF",
            "01FF81BD 063EFF00 8000000F FFFFFEFF",
            "FF00C081 7FFB0000 80000000 7FFFFFFE",
            "7EFFC084 7FFB0000 00000000 7FFFFFFE",
            "FF00023D 08FEBA02 403DBD0A 7FFB7FFF",
            "01FF81BD 88FDBA05 403DBD0A 7FFB7FFF",
            "FF01807F FFFF7EF9 00000020 7FFFFFFE",
            "FF018090 FFFF7EF8 00000020 7FFFFFFE",
            "FF00023D 08FEBA02 403DBD0A 7FFB7FFF",
        ),
    ),
    "VMSL adds the even and odd doubleword products, each shifted left one bit by its M6 flag, and V4; M6 bits 2-3 ignored; V1 equal to V4 (PoO 22-24)": (
        _sources((2, "ONES"), (3, "MULA"), (4, "MULB"), (5, "MULC"))
        + line("VMSL", "16,2,2,5,3,0")
        + line("VMSLG", "17,2,2,5,8")
        + line("VMSLG", "18,2,2,5,4")
        + line("VMSLG", "19,2,2,5,12")
        + line("VMSLG", "20,3,4,5,3")
        + line("VMSLG", "21,3,4,5,8")
        + line("VMSLG", "22,3,4,5,4")
        + line("VLR", "23,5")
        + line("VMSLG", "23,3,4,23,12")
        + line("VSTM", "16,23,OUT"),
        image(
            "FF01807F FFFF7FFC 80000000 00000001",
            "FF01807F FFFF7FFA 80000000 00000002",
            "FF01807F FFFF7FFA 80000000 00000002",
            "FF01807F FFFF7FF8 80000000 00000003",
            "01FF81CE 88FDB8FC C03DBD2A FFFB7FFE",
            "04FD830C 11FBF301 807B7A35 7FF6FFFE",
            "01FF81DF 88FDB7F4 403DBD4B 7FFB7FFD",
            "04FD831D 11FBF1F9 007B7A55 FFF6FFFD",
        ),
    ),
    "VGFM VGFMA XOR the even and odd carry-less products, and V4, ES 0-3, V1 equal to V2 and V4 (PoO 22-16)": (
        _sources((2, "MULA"), (3, "MULB"), (4, "MULC"))
        + line("VGFMB", "16,2,3")
        + line("VGFMH", "17,2,3")
        + line("VGFMF", "18,2,3")
        + line("VGFMG", "19,2,3")
        + line("VGFMAB", "20,2,3,4")
        + line("VGFMAH", "21,2,3,4")
        + line("VGFMAF", "22,2,3,4")
        + line("VGFMAG", "23,2,3,4")
        + line("VLR", "24,2")
        + line("VGFMH", "24,24,3")
        + line("VLR", "25,4")
        + line("VGFMAG", "25,2,3,25")
        + line("VSTM", "16,25,OUT"),
        image(
            "7E7E1455 7F7F0000 00000F00 7F8000FF",
            "14C05580 2AAB2AAA 000FFF00 7FFF7FFF",
            "2B009595 0597FF00 7FFFFFF0 800000FF",
            "01AA00CE 042BBDF3 C0BEBEED FFFC7FFF",
            "817F942A 80808000 7FFFF0FF 807FFF00",
            "EBC1D5FF D554AAAA 7FF000FF 80008000",
            "D40115EA FA687F00 0000000F 7FFFFF00",
            "FEAB80B1 FBD43DF3 BF414112 00038000",
            "14C05580 2AAB2AAA 000FFF00 7FFF7FFF",
            "FEAB80B1 FBD43DF3 BF414112 00038000",
        ),
    ),
    "VD VDL VR VRL truncate toward zero, the remainder takes the dividend's sign, ES 2-4, V1 equal to V2 and V3 (PoO 22-12, 22-13, 22-27)": (
        _sources((2, "DIVA"), (3, "DIVC"))
        + line("VDF", "16,2,3,0")
        + line("VDLF", "17,2,3,0")
        + line("VRF", "18,2,3,0")
        + line("VRLF", "19,2,3,0")
        + line("VDG", "20,2,3,0")
        + line("VDLG", "21,2,3,0")
        + line("VRG", "22,2,3,0")
        + line("VRLG", "23,2,3,0")
        + line("VDQ", "24,2,3,0")
        + line("VDLQ", "25,2,3,0")
        + line("VRQ", "26,2,3,0")
        + line("VRLQ", "27,2,3,0")
        + line("VLR", "28,3")
        + line("VDF", "28,28,2,0")
        + line("VLR", "29,2")
        + line("VRF", "29,29,3,8")
        + line("VSTM", "16,29,OUT"),
        image(
            "D5555556 FFFFFFFD FFFFFFFD 19999999",
            "2AAAAAAA 7FFFFFFC 00000000 19999999",
            "FFFFFFFE FFFFFFFF 00000001 00000002",
            "00000002 00000001 00000007 00000002",
            "FFFFFFFF D5555556 FFFFFFFF FFFFFFFD",
            "00000000 2AAAAAAA 00000000 00000000",
            "FFFFFFFF 5555554D 00000001 8000000E",
            "00000002 AAAAAAA5 00000007 7FFFFFFF",
            "FFFFFFFF FFFFFFFF FFFFFFFF D5555556",
            "00000000 00000000 00000000 2AAAAAAA",
            "FFFFFFFF 7FFFFFF6 AAAAAAB4 55555551",
            "00000002 7FFFFFFB 5555555A AAAAAAAD",
            "00000000 00000000 00000000 00000000",
            "FFFFFFFE FFFFFFFF 00000001 00000002",
        ),
    ),
    "VD VDL VR VRL with IDC give zero for a zero divisor, and VD for the negative maximum by -1, without an exception; VR of the negative maximum by -1 is no fault even without IDC, remainder 0 (PoO 22-13, 22-27)": (
        _sources((2, "DIVA"), (3, "DIVB"), (4, "ONES"), (5, "QMIN"))
        + line("VDF", "16,2,3,8")
        + line("VDLF", "17,2,3,8")
        + line("VRF", "18,2,3,8")
        + line("VRLF", "19,2,3,8")
        + line("VDG", "20,2,3,8")
        + line("VDLG", "21,2,3,8")
        + line("VRG", "22,2,3,8")
        + line("VRLG", "23,2,3,8")
        + line("VDQ", "24,2,3,8")
        + line("VDLQ", "25,2,3,8")
        + line("VRQ", "26,2,3,8")
        + line("VRLQ", "27,2,3,8")
        + line("VRF", "28,2,4,0")
        + line("VRQ", "29,5,4,0")
        + line("VSTM", "16,29,OUT"),
        image(
            "00000000 FFFFFFFD FFFFFFFD 00000000",
            "00000000 7FFFFFFC 00000000 00000000",
            "00000000 FFFFFFFF 00000001 00000000",
            "80000000 00000001 00000007 00000000",
            "00000000 80000000 FFFFFFFF FFFFFFFD",
            "00000000 00000000 00000000 00000000",
            "FFFFFFFF FFFFFFF9 00000001 7FFFFFFF",
            "80000000 FFFFFFF9 00000007 7FFFFFFF",
            "00000000 00000000 00000000 80000000",
            "00000000 00000000 00000000 00000000",
            "FFFFFFFF 7FFFFFFA 00000007 7FFFFFFF",
            "80000000 FFFFFFF9 00000007 7FFFFFFF",
            "00000000 00000000 00000000 00000000",
            "00000000 00000000 00000000 00000000",
        ),
    ),
}

TRAPPED_V1 = 1


def _trap(mnemonic: str, divisor: str, mask: int) -> str:
    return (
        _sources((TRAPPED_V1, "SRC"), (2, "DIVA"), (3, divisor))
        + line(mnemonic, f"{TRAPPED_V1},2,3,{mask}")
        + line("VST", f"{TRAPPED_V1},OUT")
    )


TRAPS: Mapping[str, Trap] = {
    "VDF zero divisor in word 3 and the negative maximum by -1 in word 0: the lowest index, 0 (PoO 22-2, 22-13)": (
        _trap("VDF", "DIVB", 0),
        0x08,
    ),
    "VDLF zero divisor in word 3 only (PoO 22-12, 22-13)": (
        _trap("VDLF", "DIVD", 0),
        0x38,
    ),
    "VRLG zero divisor in doubleword 1 (PoO 22-27)": (_trap("VRLG", "DIVE", 0), 0x18),
    "VRQ zero divisor, IDC bits 1-3 ignored (PoO 22-27)": (
        _trap("VRQ", "ZERO", 7),
        0x08,
    ),
    "VDQ negative maximum by -1 (PoO 22-13)": (
        _sources((TRAPPED_V1, "SRC"), (2, "QMIN"), (3, "ONES"))
        + line("VDQ", f"{TRAPPED_V1},2,3,0")
        + line("VST", f"{TRAPPED_V1},OUT"),
        0x08,
    ),
}

CHECKS: Mapping[str, str] = {
    f"{mnemonic} {field}": line(mnemonic, operands) + line("VST", "1,OUT")
    for mnemonic, field, operands in (
        ("VA", "element size 5", "1,2,3,5"),
        ("VACC", "element size 5", "1,2,3,5"),
        ("VS", "element size 5", "1,2,3,5"),
        ("VSCBI", "element size 5", "1,2,3,5"),
        ("VAC", "M5 3 (PoO 22-6)", "1,2,3,4,3"),
        ("VACCC", "M5 0 (PoO 22-6)", "1,2,3,4,0"),
        ("VSBI", "M5 3 (PoO 22-35)", "1,2,3,4,3"),
        ("VSBCBI", "M5 5 (PoO 22-35)", "1,2,3,4,5"),
        ("VAVG", "element size 5", "1,2,3,5"),
        ("VAVGL", "element size 5", "1,2,3,5"),
        ("VD", "element size 1 (PoO 22-13)", "1,2,3,1,0"),
        ("VDL", "element size 5", "1,2,3,5,0"),
        ("VR", "element size 0 (PoO 22-27)", "1,2,3,0,0"),
        ("VRL", "element size 1 (PoO 22-27)", "1,2,3,1,8"),
        ("VML", "element size 5", "1,2,3,5"),
        ("VMH", "element size 5", "1,2,3,5"),
        ("VMLH", "element size 5", "1,2,3,5"),
        ("VMAL", "element size 5", "1,2,3,4,5"),
        ("VMAH", "element size 5", "1,2,3,4,5"),
        ("VMALH", "element size 5", "1,2,3,4,5"),
        ("VME", "element size 4 (PoO 22-23)", "1,2,3,4"),
        ("VMLE", "element size 4 (PoO 22-23)", "1,2,3,4"),
        ("VMO", "element size 4 (PoO 22-24)", "1,2,3,4"),
        ("VMLO", "element size 4 (PoO 22-24)", "1,2,3,4"),
        ("VMAE", "element size 4 (PoO 22-20)", "1,2,3,4,4"),
        ("VMALE", "element size 4 (PoO 22-20)", "1,2,3,4,4"),
        ("VMAO", "element size 4 (PoO 22-21)", "1,2,3,4,4"),
        ("VMALO", "element size 4 (PoO 22-21)", "1,2,3,4,4"),
        ("VMSL", "element size 2 (PoO 22-24)", "1,2,3,4,2,0"),
        ("VMSL", "element size 4 (PoO 22-24)", "1,2,3,4,4,0"),
        ("VGFM", "element size 4 (PoO 22-16)", "1,2,3,4"),
        ("VGFMA", "element size 4 (PoO 22-16)", "1,2,3,4,4"),
        ("VSUM", "element size 2 (PoO 22-36)", "1,2,3,2"),
        ("VSUMG", "element size 0 (PoO 22-36)", "1,2,3,0"),
        ("VSUMG", "element size 3 (PoO 22-36)", "1,2,3,3"),
        ("VSUMQ", "element size 1 (PoO 22-36)", "1,2,3,1"),
        ("VSUMQ", "element size 4 (PoO 22-36)", "1,2,3,4"),
    )
}
