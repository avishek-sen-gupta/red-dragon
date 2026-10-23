# pyright: standard
"""DC image programs shared by the VM tests and the z390 differential tests: the constants sit at DATA, a doubleword after the section start, and LMG loads them into R2 upward before an ABEND."""

from collections.abc import Mapping

FIRST_REGISTER = 2
DOUBLEWORD_HEX_DIGITS = 16


def image_program(constants: str, doublewords: int) -> str:
    last = FIRST_REGISTER + doublewords - 1
    return (
        "T        CSECT\n"
        "         USING T,12\n"
        "         J     CODE\n"
        "         DS    0D\n"
        f"DATA     DS    0D\n{constants}"
        "         DS    0D\n"
        "CODE     LARL  12,T\n"
        f"         LMG   {FIRST_REGISTER},{last},DATA\n"
        "         ABEND 1\n"
        "         END\n"
    )


def registers(image: str) -> Mapping[int, int]:
    words = [
        image[i : i + DOUBLEWORD_HEX_DIGITS]
        for i in range(0, len(image), DOUBLEWORD_HEX_DIGITS)
    ]
    return {FIRST_REGISTER + i: int(word, 16) for i, word in enumerate(words)}


TYPES = (
    "         DC    AD(DATA-T)\n"
    "         DC    FD'-2'\n"
    "         DC    CA'ABC',CE'D',S(DATA),H'7'\n"
    "         DC    CL4'A',F'5'\n"
    "         DC    SY(DATA),X'AA',XL4'01020304'\n"
    "         DC    SY(-2(9)),C'B',AL2(3)\n"
    "         DC    CAL5'AB',X'C',Y(9),X'EEFF'\n"
)
TYPES_IMAGE = (
    "0000000000000008"
    "FFFFFFFFFFFFFFFE"
    "414243C4C0080007"
    "C140404000000005"
    "C00800AA01020304"
    "9FFEFFC200034142"
    "2020200C0009EEFF"
)

FIXED_POINT = (
    "         DC    FS2'1',FS4'1.25'\n"
    "         DC    HS1'-3.5',H'-1E2',H'U65535',H'7'\n"
    "         DC    F'1E2',FE1'1.5'\n"
    "         DC    FE1'100',F'U4294967295'\n"
    "         DC    F'1.5E1',F'-2147483648'\n"
)
FIXED_POINT_IMAGE = (
    "0000000400000014"
    "FFF9FF9CFFFF0007"
    "000000640000000F"
    "000003E8FFFFFFFF"
    "0000000F80000000"
)

BIT_LENGTHS = (
    "         DC    FL.12'-1,1000'\n"
    "         DC    FL.12'-1'\n"
    "         DC    BL.4'1010',BL.4'0101'\n"
    "         DC    AL.4(1),AL.4(2)\n"
    "         DC    HL.4'3'\n"
    "         DC    3FL.12'-2'\n"
    "         DC    CL.12'AB'\n"
    "         DC    X'77'\n"
    "         DC    FL.12'-1,1000,-2'\n"
    "         DC    CL.12'A'\n"
    "         DC    X'66'\n"
    "         DC    PL.12'5'\n"
    "         DC    BL.12'101010101010',BL.4'1111'\n"
    "         DC    CAL.12'A'\n"
    "         DC    X'5555'\n"
)
BIT_LENGTHS_IMAGE = (
    "FFF3E8FFF0A51230" "FFEFFEFFE0C1C077" "FFF3E8FFE0C14066" "05C0AAAF41205555"
)

BIT_LENGTHS_PAST_Z390 = (
    "         DC    3BL.3'101'\n"
    "         DC    BL.3'111',C'X'\n"
    "         DC    XL.12'ABCDE'\n"
    "         DC    ZL.12'5'\n"
    "         DC    BL.4'1',F'1'\n"
)
BIT_LENGTHS_PAST_Z390_IMAGE = "B680E0E7CDE00C50" "1000000000000001"

PADDING = "         DC    C'A',F'5',C'B',FD'6'\n"
PADDING_IMAGE = "C100000000000005" "C2000000000000000000000000000006"

FAMILIES: Mapping[str, tuple[str, str]] = {
    "doubleword, character-set and base-displacement types": (TYPES, TYPES_IMAGE),
    "bit lengths packed from each operand's bit offset": (
        BIT_LENGTHS,
        BIT_LENGTHS_IMAGE,
    ),
    "fixed point with scale, exponents and the U prefix": (
        FIXED_POINT,
        FIXED_POINT_IMAGE,
    ),
}
