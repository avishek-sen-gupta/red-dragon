# pyright: standard
"""Vector load and store programs: each moves bytes between SRC (bytes X'00' to X'3F') and vector registers, then stores the registers to OUT with VST or VSTE; expected images from the Principles of Operation, SA22-7832-14 chapter 21."""

from collections.abc import Mapping

SECTION = "V"
OUT_AT = 64
OUT_BYTES = 224
OUT_SPAN = (OUT_AT, OUT_AT + OUT_BYTES)
FILL = 0xEE
COMPLETED = "U0001"
SPECIFICATION = "S0C6"

type Case = tuple[str, bytes]

SRC_ROWS = 4
SRC_LINES = "".join(
    f"{'SRC' if row == 0 else '':<8} DC    X'{bytes(range(16 * row, 16 * row + 16)).hex().upper()}'\n"
    for row in range(SRC_ROWS)
)


def line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<8} {operands}\n"


def image(*rows: str) -> bytes:
    image = bytes.fromhex("".join(rows).replace(" ", ""))
    return image + bytes([FILL]) * (OUT_BYTES - len(image))


def program(body: str, data: str) -> str:
    return (
        "T        CSECT\n"
        "         LARL  12,V\n"
        "         USING V,12\n"
        f"{body}"
        "         ABEND 1\n"
        "V        CSECT\n"
        f"{SRC_LINES}"
        f"OUT      DC    {OUT_BYTES}X'{FILL:02X}'\n"
        f"{data}"
        "         END   T\n"
    )


UNCHANGED = image()

CASES: Mapping[str, Case] = {
    "VL VLR VST, VL indexed": (
        line("VL", "1,SRC")
        + line("VLR", "17,1")
        + line("VST", "17,OUT")
        + line("LGHI", "5,32")
        + line("VL", "3,SRC(5),3")
        + line("VST", "3,OUT+16(5),4"),
        image(
            "00010203 04050607 08090A0B 0C0D0E0F",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "20212223 24252627 28292A2B 2C2D2E2F",
        ),
    ),
    "VLM VSTM over 2 and 16 registers (PoO 21-12, 21-24)": (
        line("VLM", "0,15,SRC")
        + line("VSTM", "1,3,OUT")
        + line("VST", "4,OUT+48")
        + line("VST", "15,OUT+64")
        + line("VLM", "30,31,SRC+32")
        + line("VSTM", "30,31,OUT+80"),
        image(
            "10111213 14151617 18191A1B 1C1D1E1F",
            "20212223 24252627 28292A2B 2C2D2E2F",
            "30313233 34353637 38393A3B 3C3D3E3F",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "EEEEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "20212223 24252627 28292A2B 2C2D2E2F",
            "30313233 34353637 38393A3B 3C3D3E3F",
        ),
    ),
    "VLEB VLEH VLEF VLEG VSTEB VSTEH VSTEF VSTEG": (
        line("VL", "1,SRC")
        + line("VLEB", "1,SRC+32,15")
        + line("VLEH", "1,SRC+34,6")
        + line("VLEF", "1,SRC+48,1")
        + line("VST", "1,OUT")
        + line("VL", "2,SRC+16")
        + line("VLEG", "2,SRC+56,0")
        + line("VST", "2,OUT+16")
        + line("VSTEB", "2,OUT+32,9")
        + line("VSTEH", "2,OUT+34,7")
        + line("VSTEF", "2,OUT+36,0")
        + line("VSTEG", "2,OUT+40,1"),
        image(
            "00010203 30313233 08090A0B 22230E20",
            "38393A3B 3C3D3E3F 18191A1B 1C1D1E1F",
            "19EE1E1F 38393A3B 18191A1B 1C1D1E1F",
        ),
    ),
    "VLEIB VLEIH VLEIF VLEIG sign-extend I2": (
        line("VL", "1,SRC")
        + line("VLEIB", "1,-2,0")
        + line("VLEIB", "1,255,1")
        + line("VLEIH", "1,-3,2")
        + line("VLEIF", "1,-4,2")
        + line("VST", "1,OUT")
        + line("VL", "2,SRC+16")
        + line("VLEIG", "2,-5,1")
        + line("VLEIG", "2,32767,0")
        + line("VST", "2,OUT+16"),
        image(
            "FEFF0203 FFFD0607 FFFFFFFC 0C0D0E0F",
            "00000000 00007FFF FFFFFFFF FFFFFFFB",
        ),
    ),
    "VLREP replicates each element size": (
        line("VLREPB", "1,SRC+5")
        + line("VLREPH", "2,SRC+6")
        + line("VLREPF", "3,SRC+8")
        + line("VLREPG", "4,SRC+16")
        + line("VSTM", "1,4,OUT"),
        image(
            "05050505 05050505 05050505 05050505",
            "06070607 06070607 06070607 06070607",
            "08090A0B 08090A0B 08090A0B 08090A0B",
            "10111213 14151617 10111213 14151617",
        ),
    ),
    "VLLEZ zero-extends into the leftmost doubleword": (
        line("VLM", "1,5,SRC")
        + line("VLLEZB", "1,SRC+9")
        + line("VLLEZH", "2,SRC+10")
        + line("VLLEZF", "3,SRC+12")
        + line("VLLEZG", "4,SRC+16")
        + line("VLLEZLF", "5,SRC+36")
        + line("VSTM", "1,5,OUT"),
        image(
            "00000000 00000009 00000000 00000000",
            "00000000 00000A0B 00000000 00000000",
            "00000000 0C0D0E0F 00000000 00000000",
            "10111213 14151617 00000000 00000000",
            "24252627 00000000 00000000 00000000",
        ),
    ),
    "VLL VSTL move min(GR,15)+1 bytes": (
        line("VLM", "1,4,SRC")
        + line("LHI", "3,0")
        + line("VLL", "1,3,SRC+16")
        + line("LHI", "4,15")
        + line("VLL", "2,4,SRC+32")
        + line("LLIHF", "6,1")
        + line("VLL", "3,6,SRC+48")
        + line("VSTM", "1,3,OUT")
        + line("IILF", "5,X'FFFFFFFF'")
        + line("VSTL", "4,3,OUT+48")
        + line("VSTL", "4,5,OUT+64")
        + line("LHI", "7,6")
        + line("VSTL", "4,7,OUT+80"),
        image(
            "10000000 00000000 00000000 00000000",
            "20212223 24252627 28292A2B 2C2D2E2F",
            "30000000 00000000 00000000 00000000",
            "30EEEEEE EEEEEEEE EEEEEEEE EEEEEEEE",
            "30313233 34353637 38393A3B 3C3D3E3F",
            "30313233 343536EE EEEEEEEE EEEEEEEE",
        ),
    ),
    "VGEF VGEG VSCEF VSCEG with V1 equal to V2": (
        line("VL", "1,SRC")
        + line("VLEIF", "1,40,2")
        + line("VGEF", "1,0(1,12),2")
        + line("VST", "1,OUT")
        + line("VL", "3,SRC+16")
        + line("VLEIG", "3,16,1")
        + line("VGEG", "3,4(3,12),1")
        + line("VST", "3,OUT+16")
        + line("VLEIF", "4,104,3")
        + line("VSCEF", "4,0(4,12),3")
        + line("VLEIG", "5,112,0")
        + line("VSCEG", "5,4(5,12),0"),
        image(
            "00010203 04050607 28292A2B 0C0D0E0F",
            "10111213 14151617 14151617 18191A1B",
            "EEEEEEEE EEEEEEEE 00000068 EEEEEEEE",
            "EEEEEEEE 00000000 00000070 EEEEEEEE",
        ),
    ),
    "VLBR VLBRREP reverse each element's bytes": (
        line("VLBRH", "1,SRC")
        + line("VLBRF", "2,SRC")
        + line("VLBRG", "3,SRC")
        + line("VLBRQ", "4,SRC")
        + line("VLBRREPH", "5,SRC+16")
        + line("VLBRREPF", "6,SRC+16")
        + line("VLBRREPG", "7,SRC+16")
        + line("VSTM", "1,7,OUT"),
        image(
            "01000302 05040706 09080B0A 0D0C0F0E",
            "03020100 07060504 0B0A0908 0F0E0D0C",
            "07060504 03020100 0F0E0D0C 0B0A0908",
            "0F0E0D0C 0B0A0908 07060504 03020100",
            "11101110 11101110 11101110 11101110",
            "13121110 13121110 13121110 13121110",
            "17161514 13121110 17161514 13121110",
        ),
    ),
    "VLEBR VLLEBRZ reverse one element": (
        line("VLM", "1,4,SRC")
        + line("VLEBRH", "1,SRC+32,7")
        + line("VLEBRF", "1,SRC+36,0")
        + line("VLEBRG", "2,SRC+40,1")
        + line("VLLEBRZH", "3,SRC+48")
        + line("VLLEBRZF", "4,SRC+48")
        + line("LDRV", "5,SRC+48")
        + line("LERV", "6,SRC+48")
        + line("VSTM", "1,6,OUT"),
        image(
            "27262524 04050607 08090A0B 0C0D2120",
            "10111213 14151617 2F2E2D2C 2B2A2928",
            "00000000 00003130 00000000 00000000",
            "00000000 33323130 00000000 00000000",
            "37363534 33323130 00000000 00000000",
            "33323130 00000000 00000000 00000000",
        ),
    ),
    "VSTBR VSTEBR store each element's bytes reversed": (
        line("VL", "1,SRC")
        + line("VSTBRH", "1,OUT")
        + line("VSTBRF", "1,OUT+16")
        + line("VSTBRG", "1,OUT+32")
        + line("VSTBRQ", "1,OUT+48")
        + line("VSTEBRH", "1,OUT+64,7")
        + line("VSTEBRF", "1,OUT+68,2")
        + line("STDRV", "1,OUT+72"),
        image(
            "01000302 05040706 09080B0A 0D0C0F0E",
            "03020100 07060504 0B0A0908 0F0E0D0C",
            "07060504 03020100 0F0E0D0C 0B0A0908",
            "0F0E0D0C 0B0A0908 07060504 03020100",
            "0F0EEEEE 0B0A0908 07060504 03020100",
        ),
    ),
    "VLER VSTER reverse the element order": (
        line("VLERH", "1,SRC")
        + line("VLERF", "2,SRC")
        + line("VLERG", "3,SRC")
        + line("VSTM", "1,3,OUT")
        + line("VL", "4,SRC+16")
        + line("VSTERH", "4,OUT+48")
        + line("VSTERF", "4,OUT+64")
        + line("VSTERG", "4,OUT+80"),
        image(
            "0E0F0C0D 0A0B0809 06070405 02030001",
            "0C0D0E0F 08090A0B 04050607 00010203",
            "08090A0B 0C0D0E0F 00010203 04050607",
            "1E1F1C1D 1A1B1819 16171415 12131011",
            "1C1D1E1F 18191A1B 14151617 10111213",
            "18191A1B 1C1D1E1F 10111213 14151617",
        ),
    ),
}

CHECKS: Mapping[str, str] = {
    "VSTEF element index 4": line("VL", "1,SRC") + line("VSTEF", "1,OUT,4"),
    "VSCEG element index 2": line("VSCEG", "1,0(1,12),2"),
    "VLREP element size 4": line("VLREP", "1,SRC,4") + line("VST", "1,OUT"),
    "VLLEZ element size 4": line("VLLEZ", "1,SRC,4") + line("VST", "1,OUT"),
    "VLBRREP element size 0": line("VLBRREP", "1,SRC,0") + line("VST", "1,OUT"),
    "VSTBR element size 0": line("VSTBR", "1,OUT,0"),
    "VSTER element size 4": line("VSTER", "1,OUT,4"),
    "VLBB boundary code 7": line("VLBB", "1,SRC,7") + line("VST", "1,OUT"),
    "VSTM 17 registers (PoO 21-24)": line("VSTM", "0,16,OUT"),
    "VLM 17 registers (PoO 21-12)": line("VLM", "0,16,SRC") + line("VST", "0,OUT"),
    "VLM V3 below V1 (PoO 21-12)": line("VLM", "30,1,SRC") + line("VST", "30,OUT"),
    "VSTM V3 below V1 (PoO 21-24)": line("VL", "31,SRC") + line("VSTM", "31,0,OUT"),
}

BLOCK_BUFFER = "BUF      DS    XL8208\n"
BLOCK_BYTES = (64, 128, 256, 512, 1024, 2048, 4096)
SHORT_OF_HALF_BLOCK = 3


def _block_load(target: int, offset: int, source: str, code: int) -> str:
    return (
        line("LA", f"7,{offset}(6)")
        + line("MVC", f"0(16,7),{source}")
        + line("VLBB", f"{target},0(7),{code}")
    )


def _crossing(code: int) -> str:
    return _block_load(code + 1, BLOCK_BYTES[code] - code - 2, "SRC+16", code)


def _within(code: int) -> str:
    offset = BLOCK_BYTES[code] // 2 - SHORT_OF_HALF_BLOCK
    return _block_load(code + 7, offset, "SRC", code)


VLBB_BODY = (
    line("LA", "6,BUF")
    + line("AHI", "6,4095")
    + line("NILL", "6,X'F000'")
    + _block_load(0, 0, "SRC+32", 0)
    + "".join(_crossing(code) for code in range(len(BLOCK_BYTES)))
    + "".join(_within(code) for code in range(1, len(BLOCK_BYTES)))
    + line("VSTM", "0,13,OUT")
)
VLBB_LOADED = (16, *(code + 2 for code in range(len(BLOCK_BYTES))), *(16,) * 6)
VLBB_EXPECTED = (
    bytes(range(0x20, 0x30)),
    *(bytes(range(0x10, 0x12 + code)) for code in range(len(BLOCK_BYTES))),
    *(bytes(range(0x10)),) * 6,
)
