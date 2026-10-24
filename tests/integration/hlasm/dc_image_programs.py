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
    "00000000"
    "00000008"
    "FFFFFFFF"
    "FFFFFFFE"
    "414243C4"
    "C0080007"
    "C1404040"
    "00000005"
    "C00800AA"
    "01020304"
    "9FFEFFC2"
    "00034142"
    "2020200C"
    "0009EEFF"
)

FIXED_POINT = (
    "         DC    FS2'1',FS4'1.25'\n"
    "         DC    HS1'-3.5',H'-1E2',H'U65535',H'7'\n"
    "         DC    F'1E2',FE1'1.5'\n"
    "         DC    FE1'100',F'U4294967295'\n"
    "         DC    F'1.5E1',F'-2147483648'\n"
)
FIXED_POINT_IMAGE = (
    "00000004"
    "00000014"
    "FFF9FF9C"
    "FFFF0007"
    "00000064"
    "0000000F"
    "000003E8"
    "FFFFFFFF"
    "0000000F"
    "80000000"
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
    "FFF3E8FF"
    "F0A51230"
    "FFEFFEFF"
    "E0C1C077"
    "FFF3E8FF"
    "E0C14066"
    "05C0AAAF"
    "41205555"
)

BIT_LENGTHS_PAST_Z390 = (
    "         DC    3BL.3'101'\n"
    "         DC    BL.3'111',C'X'\n"
    "         DC    XL.12'ABCDE'\n"
    "         DC    ZL.12'5'\n"
    "         DC    BL.4'1',F'1'\n"
)
BIT_LENGTHS_PAST_Z390_IMAGE = "B680E0E7" "CDE00C50" "10000000" "00000001"

CHANNEL_COMMANDS = (
    "         CCW   X'02',X'123456',X'20',80\n"
    "         CCW1  X'03',X'7FFFFFFF',X'40',65535\n"
    "         CCW0  1,0,0,1\n"
)
CHANNEL_COMMANDS_IMAGE = (
    "02123456" "20000050" "0340FFFF" "7FFFFFFF" "01000000" "00000001"
)

PADDING = "         DC    C'A',F'5',C'B',FD'6'\n"
PADDING_IMAGE = "C1000000" "00000005" "C2000000" "00000000" "00000000" "00000006"

HEXADECIMAL_FLOATING_POINT = (
    "         DC    E'46.415',E'-1'\n"
    "         DC    D'0.1'\n"
    "         DC    E'1E-78',EH'-0'\n"
    "         DC    L'-1'\n"
    "         DC    L'1E-70'\n"
    "         DC    EL2'1'\n"
    "         DC    EL.12'1'\n"
    "         DC    EL.13'-1'\n"
    "         DC    EBL.12'1'\n"
    "         DC    LL9'1',XL7'0'\n"
    "         DC    EH'(MAX)',E'0.1'\n"
    "         DC    DH'(MAX)'\n"
    "         DC    LH'(MAX)'\n"
)
HEXADECIMAL_FLOATING_POINT_IMAGE = (
    "422E6A3D"
    "C1100000"
    "40199999"
    "9999999A"
    "001DA48D"
    "80000000"
    "C1100000"
    "00000000"
    "B3000000"
    "00000000"
    "06B0AF48"
    "EC79ACE8"
    "78372D83"
    "5A9DF0C7"
    "41104110"
    "C1103F80"
    "41100000"
    "00000000"
    "33000000"
    "00000000"
    "7FFFFFFF"
    "4019999A"
    "7FFFFFFF"
    "FFFFFFFF"
    "7FFFFFFF"
    "FFFFFFFF"
    "71FFFFFF"
    "FFFFFFFF"
)

BINARY_AND_DECIMAL_FLOATING_POINT = (
    "         DC    EB'1.5',EB'-0'\n"
    "         DC    DB'0.1'\n"
    "         DC    LB'0.1'\n"
    "         DC    EB'(MAX)',EB'(MIN)'\n"
    "         DC    ED'1.5',ED'-0'\n"
    "         DC    DD'1.50'\n"
    "         DC    LD'-0.001'\n"
    "         DC    DD'1E369'\n"
    "         DC    ED'1234567.8',ED'(MAX)'\n"
    "         DC    DD'(MAX)'\n"
    "         DC    LB'(MAX)'\n"
)
BINARY_AND_DECIMAL_FLOATING_POINT_IMAGE = (
    "3FC00000"
    "80000000"
    "3FB99999"
    "9999999A"
    "3FFB9999"
    "99999999"
    "99999999"
    "9999999A"
    "7F7FFFFF"
    "00800000"
    "22400015"
    "A2500000"
    "22300000"
    "000000D0"
    "A2074000"
    "00000000"
    "00000000"
    "00000001"
    "43FC0000"
    "00000001"
    "2654D2E8"
    "77F3FCFF"
    "77FCFF3F"
    "CFF3FCFF"
    "7FFEFFFF"
    "FFFFFFFF"
    "FFFFFFFF"
    "FFFFFFFF"
)

HEXADECIMAL_FLOATING_POINT_PAST_Z390 = (
    "         DC    E'-0',ES2'1'\n"
    "         DC    EE2'.46415',EH'(MIN)'\n"
    "         DC    EL5'0.1',XL3'0'\n"
    "         DC    DL3'0.1',XL5'0'\n"
    "         DC    LL10'0.1',XL6'0'\n"
    "         DC    LS3'1'\n"
    "         DC    EH'1E80',EH'-1E-79R6'\n"
    "         DC    EH'(DMIN)',EH'0.1R5'\n"
)
HEXADECIMAL_FLOATING_POINT_PAST_Z390_IMAGE = (
    "00000000"
    "43001000"
    "422E6A3D"
    "00100000"
    "40199999"
    "9A000000"
    "40199A00"
    "00000000"
    "40199999"
    "99999999"
    "329A0000"
    "00000000"
    "44000100"
    "00000000"
    "36000000"
    "00000000"
    "7FFFFFFF"
    "8002F6DA"
    "00000001"
    "40199999"
)

BINARY_AND_DECIMAL_FLOATING_POINT_PAST_Z390 = (
    "         DC    EB'3.4028235E38',EB'1E39'\n"
    "         DC    EB'0.1R5',EB'-0.1R7'\n"
    "         DC    EB'(INF)',EB'-(NAN)'\n"
    "         DC    EB'(QNAN)',EB'(SNAN)'\n"
    "         DC    EB'(DMIN)',ED'(DMIN)'\n"
    "         DC    ED'(INF)',ED'(SNAN)'\n"
    "         DC    ED'(MIN)',ED'0.000'\n"
    "         DC    DD'(MIN)'\n"
    "         DC    DD'1E370'\n"
    "         DC    LD'1.5E6200'\n"
    "         DC    DD'1.23456789012345678R9'\n"
)
BINARY_AND_DECIMAL_FLOATING_POINT_PAST_Z390_IMAGE = (
    "7F7FFFFF"
    "7F800000"
    "3DCCCCCC"
    "BDCCCCCD"
    "7F800000"
    "FFC00000"
    "7FE00000"
    "7FA00000"
    "00000001"
    "00000001"
    "78000000"
    "7E000000"
    "00600001"
    "22200000"
    "003C0000"
    "00000001"
    "43FC0000"
    "00000010"
    "78000000"
    "00000000"
    "00000000"
    "00000000"
    "25FD34B9"
    "C1E28E56"
)

FAMILIES: Mapping[str, tuple[str, str]] = {
    "doubleword, character-set and base-displacement types": (TYPES, TYPES_IMAGE),
    "bit lengths packed from each operand's bit offset": (
        BIT_LENGTHS,
        BIT_LENGTHS_IMAGE,
    ),
    "channel command words, format 0 and 1": (
        CHANNEL_COMMANDS,
        CHANNEL_COMMANDS_IMAGE,
    ),
    "fixed point with scale, exponents and the U prefix": (
        FIXED_POINT,
        FIXED_POINT_IMAGE,
    ),
    "hexadecimal floating point, lengths and special values": (
        HEXADECIMAL_FLOATING_POINT,
        HEXADECIMAL_FLOATING_POINT_IMAGE,
    ),
    "binary and decimal floating point and special values": (
        BINARY_AND_DECIMAL_FLOATING_POINT,
        BINARY_AND_DECIMAL_FLOATING_POINT_IMAGE,
    ),
}

PAST_Z390: Mapping[str, tuple[str, str]] = {
    "bit lengths": (BIT_LENGTHS_PAST_Z390, BIT_LENGTHS_PAST_Z390_IMAGE),
    "hexadecimal floating point": (
        HEXADECIMAL_FLOATING_POINT_PAST_Z390,
        HEXADECIMAL_FLOATING_POINT_PAST_Z390_IMAGE,
    ),
    "binary and decimal floating point": (
        BINARY_AND_DECIMAL_FLOATING_POINT_PAST_Z390,
        BINARY_AND_DECIMAL_FLOATING_POINT_PAST_Z390_IMAGE,
    ),
}
