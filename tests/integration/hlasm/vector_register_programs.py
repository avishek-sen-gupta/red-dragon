# pyright: standard
"""Vector register-manipulation programs: each builds vector registers from SRC (bytes X'00' to X'3F') and the constants below, then stores them to OUT with VST, general registers with STG and condition codes with IPM and STC; expected images from the Principles of Operation, SA22-7832-14 chapter 21, page cited per case."""

from collections.abc import Mapping

from tests.integration.hlasm.vector_memory_programs import image, line

type Case = tuple[str, bytes]


def _dc(label: str, *words: str) -> str:
    return f"{label:<8} DC    " + ",".join(f"X'{w}'" for w in words) + "\n"


DATA = (
    _dc("MASKS", "A55A0000", "00000000", "00000000", "00000000")
    + _dc("PERMS", "1F00100F", "203FE105", "111E0807", "C90A1602")
    + _dc("BITS", "0F00161E", "1F84FF7C", "7F173D3C", "010E2D2E")
    + _dc("GVAL", "81828384", "85868788")
    + _dc("GVAL2", "01020304", "05060708")
    + _dc("SIGNH", "007F0080", "FF80FF7F", "00007FFF", "8000FFFF")
    + _dc("SMALLH", "0001FFFE", "0040FFC0", "00100020", "00300040")
    + _dc("WIDEH", "01008000", "7FFFFE00", "01008000", "7FFFFE00")
    + _dc("SIGNF", "00007FFF", "00008000", "FFFF8000", "FFFF7FFF")
    + _dc("SIGNG", "00000000", "7FFFFFFF", "00000000", "80000000")
    + _dc("SIGNG2", "FFFFFFFF", "80000000", "FFFFFFFF", "7FFFFFFF")
    + _dc("LOGH", "00FF0100", "FFFF0080", "00010002", "00030004")
    + _dc("LOGG", "00000000", "FFFFFFFF", "00000001", "00000000")
    + _dc("SEG", "01234567", "89ABCD80", "FEDCBA98", "7654327F")
    + _dc("SELECT", "FF00F00F", "0000FFFF", "AAAA5555", "00000000")
    + _dc("BLENDB", "807FFF00", "8101C040", "80000080", "FFFF0000")
    + _dc("BLENDF", "00000000", "FFFFFFFF", "7FFFFFFF", "80000000")
    + _dc("BLENDG", "80000000", "00000000", "00000000", "00000001")
    + _dc("UNPACK", "807FFF01", "80017FFF", "89ABCDEF", "01234567")
)


def _cc(register: int, at: int) -> str:
    return (
        line("IPM", f"{register}")
        + line("SRL", f"{register},28")
        + line("STC", f"{register},OUT+{at}")
    )


def _pairs() -> str:
    return line("VL", "2,SRC") + line("VL", "3,SRC+16")


CASES: Mapping[str, Case] = {
    "VGBM VZERO VONE set bytes by I2 (PoO 21-6)": (
        line("VGBM", "1,X'F001'")
        + line("VONE", "2")
        + line("VL", "3,SRC+16")
        + line("VZERO", "3")
        + line("VSTM", "1,3,OUT"),
        image(
            "FFFFFFFF 00000000 00000000 000000FF",
            "FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF",
            "00000000 00000000 00000000 00000000",
        ),
    ),
    "VGM ranges, wrapping when I2 > I3, I2 and I3 mod element bits (PoO 21-7)": (
        line("VGMB", "1,2,5")
        + line("VGMH", "2,14,1")
        + line("VGMF", "3,8,23")
        + line("VGMG", "4,62,1")
        + line("VGMB", "5,10,13")
        + line("VGMB", "6,7,0")
        + line("VSTM", "1,6,OUT"),
        image(
            "3C3C3C3C 3C3C3C3C 3C3C3C3C 3C3C3C3C",
            "C003C003 C003C003 C003C003 C003C003",
            "00FFFF00 00FFFF00 00FFFF00 00FFFF00",
            "C0000000 00000003 C0000000 00000003",
            "3C3C3C3C 3C3C3C3C 3C3C3C3C 3C3C3C3C",
            "81818181 81818181 81818181 81818181",
        ),
    ),
    "VGEM expands the leftmost bits of V2 per element size (PoO 21-7)": (
        line("VL", "2,MASKS")
        + line("VGEMB", "1,2")
        + line("VGEMH", "3,2")
        + line("VGEMF", "4,2")
        + line("VGEMG", "5,2")
        + line("VGEMQ", "6,2")
        + line("VGEMF", "2,2")
        + line("VSTM", "1,6,OUT"),
        image(
            "FF00FF00 00FF00FF 00FF00FF FF00FF00",
            "FFFFFFFF 00000000 FFFFFFFF 00000000",
            "FFFF0000 FFFF0000 0000FFFF 0000FFFF",
            "FFFFFFFF 00000000 FFFFFFFF 00000000",
            "FFFFFFFF FFFFFFFF 00000000 00000000",
            "FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF",
        ),
    ),
    "VLGV zero-extends the element the address's low 12 bits name (PoO 21-13)": (
        line("VL", "1,SRC")
        + line("LGHI", "2,-1")
        + line("VLGVB", "2,1,5")
        + line("LGHI", "3,-1")
        + line("VLGVH", "3,1,3")
        + line("LGHI", "6,4095")
        + line("VLGVF", "4,1,3(6)")
        + line("VLGVG", "5,1,1")
        + line("STMG", "2,5,OUT"),
        image(
            "00000000 00000005 00000000 00000607",
            "00000000 08090A0B 08090A0B 0C0D0E0F",
        ),
    ),
    "VLVG VLVGP place general registers (PoO 21-16)": (
        line("VL", "1,SRC")
        + line("LG", "2,GVAL")
        + line("VLVGB", "1,2,0")
        + line("VLVGH", "1,2,3")
        + line("VLVGF", "1,2,3")
        + line("VL", "3,SRC+16")
        + line("LGHI", "6,4095")
        + line("VLVGG", "3,2,2(6)")
        + line("LG", "4,GVAL2")
        + line("VLVGP", "4,2,4")
        + line("VLVGP", "5,4,4")
        + line("VST", "1,OUT")
        + line("VSTM", "3,5,OUT+16"),
        image(
            "88010203 04058788 08090A0B 85868788",
            "10111213 14151617 81828384 85868788",
            "81828384 85868788 01020304 05060708",
            "01020304 05060708 01020304 05060708",
        ),
    ),
    "VMRH VMRL interleave halves, V1 equal to V2 or V3 (PoO 21-17)": (
        _pairs()
        + line("VMRHB", "4,2,3")
        + line("VMRLB", "5,2,3")
        + line("VMRHH", "6,2,3")
        + line("VMRHF", "7,2,3")
        + line("VMRHG", "8,2,3")
        + line("VMRLF", "3,2,3")
        + line("VST", "3,OUT+112")
        + line("VL", "3,SRC+16")
        + line("VMRLG", "2,2,3")
        + line("VSTM", "2,8,OUT"),
        image(
            "08090A0B 0C0D0E0F 18191A1B 1C1D1E1F",
            "10111213 14151617 18191A1B 1C1D1E1F",
            "00100111 02120313 04140515 06160717",
            "08180919 0A1A0B1B 0C1C0D1D 0E1E0F1F",
            "00011011 02031213 04051415 06071617",
            "00010203 10111213 04050607 14151617",
            "00010203 04050607 10111213 14151617",
            "08090A0B 18191A1B 0C0D0E0F 1C1D1E1F",
        ),
    ),
    "VPDI picks doublewords by M4 bits 1 and 3 (PoO 21-20)": (
        _pairs()
        + line("VPDI", "4,2,3,0")
        + line("VPDI", "5,2,3,5")
        + line("VPDI", "6,2,3,4")
        + line("VPDI", "7,2,3,1")
        + line("VPDI", "3,2,3,4")
        + line("VSTM", "3,7,OUT"),
        image(
            "08090A0B 0C0D0E0F 10111213 14151617",
            "00010203 04050607 10111213 14151617",
            "08090A0B 0C0D0E0F 18191A1B 1C1D1E1F",
            "08090A0B 0C0D0E0F 10111213 14151617",
            "00010203 04050607 18191A1B 1C1D1E1F",
        ),
    ),
    "VPERM takes bytes of V2 || V3 by V4's low five bits, V1 equal to a source (PoO 21-20)": (
        _pairs()
        + line("VL", "4,PERMS")
        + line("VPERM", "5,2,3,4")
        + line("VL", "6,PERMS")
        + line("VPERM", "6,2,3,6")
        + line("VPERM", "2,2,3,4")
        + line("VST", "5,OUT")
        + line("VST", "6,OUT+16")
        + line("VST", "2,OUT+32"),
        image(
            "1F00100F 001F0105 111E0807 090A1602",
            "1F00100F 001F0105 111E0807 090A1602",
            "1F00100F 001F0105 111E0807 090A1602",
        ),
    ),
    "VBPERM selects bits of V2 || zeros into bits 48-63 (PoO 21-5)": (
        line("VL", "2,SRC")
        + line("VL", "3,BITS")
        + line("VL", "1,SRC+32")
        + line("VBPERM", "1,2,3")
        + line("VBPERM", "3,2,3")
        + line("VST", "1,OUT")
        + line("VST", "3,OUT+16"),
        image(
            "00000000 0000B9A2 00000000 00000000",
            "00000000 0000B9A2 00000000 00000000",
        ),
    ),
    "VPK keeps the right half of each element, V1 equal to V2 (PoO 21-18)": (
        _pairs()
        + line("VPKH", "4,2,3")
        + line("VPKF", "5,2,3")
        + line("VPKG", "6,2,3")
        + line("VPKF", "2,2,3")
        + line("VST", "2,OUT")
        + line("VSTM", "4,6,OUT+16"),
        image(
            "02030607 0A0B0E0F 12131617 1A1B1E1F",
            "01030507 090B0D0F 11131517 191B1D1F",
            "02030607 0A0B0E0F 12131617 1A1B1E1F",
            "04050607 0C0D0E0F 14151617 1C1D1E1F",
        ),
    ),
    "VPKS saturates signed elements and sets CC 0, 1 or 3 only with CS (PoO 21-18, 21-19)": (
        line("VL", "2,SIGNH")
        + line("VL", "3,SMALLH")
        + line("VL", "6,WIDEH")
        + line("VPKSHS", "4,2,3")
        + _cc(9, 192)
        + line("VPKSHS", "5,3,3")
        + _cc(9, 193)
        + line("VPKSHS", "6,6,6")
        + _cc(9, 194)
        + line("LHI", "7,5")
        + line("LTR", "7,7")
        + line("VPKSH", "7,2,3")
        + _cc(9, 195)
        + line("VL", "8,SIGNF")
        + line("VPKSFS", "8,8,8")
        + _cc(9, 196)
        + line("VL", "10,SIGNG")
        + line("VL", "11,SIGNG2")
        + line("VPKSGS", "9,10,11")
        + _cc(9, 197)
        + line("VSTM", "4,9,OUT"),
        image(
            "7F7F8080 007F80FF 01FE40C0 10203040",
            "01FE40C0 10203040 01FE40C0 10203040",
            "7F807F80 7F807F80 7F807F80 7F807F80",
            "7F7F8080 007F80FF 01FE40C0 10203040",
            "7FFF7FFF 80008000 7FFF7FFF 80008000",
            "7FFFFFFF 7FFFFFFF 80000000 80000000",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "01000302 0101EEEE EEEEEEEE EEEEEEEE",
        ),
    ),
    "VPKLS saturates unsigned elements and sets CC with CS (PoO 21-19)": (
        line("VL", "2,LOGH")
        + line("VL", "3,SMALLH")
        + line("VPKLSHS", "4,2,2")
        + _cc(9, 80)
        + line("VPKLSHS", "5,3,3")
        + _cc(9, 81)
        + line("VL", "6,LOGG")
        + line("VPKLSGS", "6,6,6")
        + _cc(9, 82)
        + line("VL", "7,WIDEH")
        + line("VPKLSFS", "7,7,7")
        + _cc(9, 83)
        + line("VL", "8,SIGNG")
        + line("VPKLSGS", "8,8,8")
        + _cc(9, 84)
        + line("VSTM", "4,8,OUT"),
        image(
            "FFFFFF80 01020304 FFFFFF80 01020304",
            "01FF40FF 10203040 01FF40FF 10203040",
            "FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF",
            "FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF",
            "7FFFFFFF 80000000 7FFFFFFF 80000000",
            "01010103 00EEEEEE EEEEEEEE EEEEEEEE",
        ),
    ),
    "VREP VREPI replicate an element or a sign-extended I2 (PoO 21-21)": (
        line("VL", "3,SRC")
        + line("VREPB", "1,3,15")
        + line("VREPH", "2,3,7")
        + line("VREPF", "4,3,0")
        + line("VREPG", "5,3,1")
        + line("VREPF", "3,3,2")
        + line("VREPIB", "6,-2")
        + line("VREPIB", "7,300")
        + line("VREPIH", "8,-3")
        + line("VREPIF", "9,-32768")
        + line("VREPIG", "10,32767")
        + line("VSTM", "1,10,OUT"),
        image(
            "0F0F0F0F 0F0F0F0F 0F0F0F0F 0F0F0F0F",
            "0E0F0E0F 0E0F0E0F 0E0F0E0F 0E0F0E0F",
            "08090A0B 08090A0B 08090A0B 08090A0B",
            "00010203 00010203 00010203 00010203",
            "08090A0B 0C0D0E0F 08090A0B 0C0D0E0F",
            "FEFEFEFE FEFEFEFE FEFEFEFE FEFEFEFE",
            "2C2C2C2C 2C2C2C2C 2C2C2C2C 2C2C2C2C",
            "FFFDFFFD FFFDFFFD FFFDFFFD FFFDFFFD",
            "FFFF8000 FFFF8000 FFFF8000 FFFF8000",
            "00000000 00007FFF 00000000 00007FFF",
        ),
    ),
    "VSEG sign-extends each doubleword's rightmost element (PoO 21-22)": (
        line("VL", "2,SEG")
        + line("VSEGB", "1,2")
        + line("VSEGH", "3,2")
        + line("VSEGF", "2,2")
        + line("VSTM", "1,3,OUT"),
        image(
            "FFFFFFFF FFFFFF80 00000000 0000007F",
            "FFFFFFFF 89ABCD80 00000000 7654327F",
            "FFFFFFFF FFFFCD80 00000000 0000327F",
        ),
    ),
    "VSEL VBLEND choose V2 where V4 is one, V1 equal to V4 or V2 (PoO 21-22, 21-5)": (
        _pairs()
        + line("VL", "4,SELECT")
        + line("VSEL", "1,2,3,4")
        + line("VSEL", "4,2,3,4")
        + line("VL", "5,BLENDB")
        + line("VBLENDB", "6,2,3,5")
        + line("VBLENDH", "7,2,3,5")
        + line("VL", "8,BLENDF")
        + line("VBLENDF", "9,2,3,8")
        + line("VBLENDQ", "10,2,3,8")
        + line("VL", "11,BLENDG")
        + line("VBLENDG", "11,2,3,11")
        + line("VBLENDB", "2,2,3,5")
        + line("VST", "1,OUT")
        + line("VST", "4,OUT+16")
        + line("VSTM", "6,7,OUT+32")
        + line("VSTM", "9,11,OUT+64")
        + line("VST", "2,OUT+112"),
        image(
            "00110213 14150607 18190A0B 1C1D1E1F",
            "00110213 14150607 18190A0B 1C1D1E1F",
            "00110213 04150617 08191A0B 0C0D1E1F",
            "00010203 04050607 08091A1B 0C0D1E1F",
            "10111213 04050607 18191A1B 0C0D0E0F",
            "10111213 14151617 18191A1B 1C1D1E1F",
            "00010203 04050607 18191A1B 1C1D1E1F",
            "00110213 04150617 08191A0B 0C0D1E1F",
        ),
    ),
    "VUPH VUPL sign-extend a half of V2, V1 equal to V2 (PoO 21-27, 21-28)": (
        line("VL", "2,UNPACK")
        + line("VUPHB", "1,2")
        + line("VUPLB", "3,2")
        + line("VUPHH", "4,2")
        + line("VUPLHW", "5,2")
        + line("VUPHF", "6,2")
        + line("VUPLF", "7,2")
        + line("VUPHG", "8,2")
        + line("VUPLG", "9,2")
        + line("VUPHB", "2,2")
        + line("VSTM", "1,9,OUT"),
        image(
            "FF80007F FFFF0001 FF800001 007FFFFF",
            "FF80007F FFFF0001 FF800001 007FFFFF",
            "FF89FFAB FFCDFFEF 00010023 00450067",
            "FFFF807F FFFFFF01 FFFF8001 00007FFF",
            "FFFF89AB FFFFCDEF 00000123 00004567",
            "FFFFFFFF 807FFF01 FFFFFFFF 80017FFF",
            "FFFFFFFF 89ABCDEF 00000000 01234567",
            "FFFFFFFF FFFFFFFF 807FFF01 80017FFF",
            "FFFFFFFF FFFFFFFF 89ABCDEF 01234567",
        ),
    ),
    "VUPLH VUPLL zero-extend a half of V2 (PoO 21-28, 21-29)": (
        line("VL", "2,UNPACK")
        + line("VUPLHB", "1,2")
        + line("VUPLLB", "3,2")
        + line("VUPLHH", "4,2")
        + line("VUPLLH", "5,2")
        + line("VUPLHF", "6,2")
        + line("VUPLLF", "7,2")
        + line("VUPLHG", "8,2")
        + line("VUPLLG", "9,2")
        + line("VSTM", "1,9,OUT"),
        image(
            "0080007F 00FF0001 00800001 007F00FF",
            "807FFF01 80017FFF 89ABCDEF 01234567",
            "008900AB 00CD00EF 00010023 00450067",
            "0000807F 0000FF01 00008001 00007FFF",
            "000089AB 0000CDEF 00000123 00004567",
            "00000000 807FFF01 00000000 80017FFF",
            "00000000 89ABCDEF 00000000 01234567",
            "00000000 00000000 807FFF01 80017FFF",
            "00000000 00000000 89ABCDEF 01234567",
        ),
    ),
}

CHECKS: Mapping[str, str] = {
    "VGM element size 4": line("VGM", "1,0,7,4") + line("VST", "1,OUT"),
    "VGEM element size 5": line("VGEM", "1,2,5") + line("VST", "1,OUT"),
    "VLGV element size 4": line("VLGV", "1,2,0,4") + line("STG", "1,OUT"),
    "VLVG element size 4": line("VLVG", "1,2,0,4") + line("VST", "1,OUT"),
    "VMRH element size 4": line("VMRH", "1,2,3,4") + line("VST", "1,OUT"),
    "VPK element size 0": line("VPK", "1,2,3,0") + line("VST", "1,OUT"),
    "VPKS element size 4": line("VPKS", "1,2,3,4,1") + line("VST", "1,OUT"),
    "VPKLS element size 0": line("VPKLS", "1,2,3,0,1") + line("VST", "1,OUT"),
    "VREP element index 16": line("VREP", "1,2,16,0") + line("VST", "1,OUT"),
    "VREPG element index 2": line("VREPG", "1,2,2") + line("VST", "1,OUT"),
    "VREPI element size 4": line("VREPI", "1,0,4") + line("VST", "1,OUT"),
    "VSEG element size 3": line("VSEG", "1,2,3") + line("VST", "1,OUT"),
    "VBLEND element size 5": line("VBLEND", "1,2,3,4,5") + line("VST", "1,OUT"),
    "VUPH element size 4": line("VUPH", "1,2,4") + line("VST", "1,OUT"),
    "VUPLL element size 4": line("VUPLL", "1,2,4") + line("VST", "1,OUT"),
}
