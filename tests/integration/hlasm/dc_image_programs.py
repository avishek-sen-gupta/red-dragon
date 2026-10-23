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

PADDING = "         DC    C'A',F'5',C'B',FD'6'\n"
PADDING_IMAGE = "C100000000000005" "C2000000000000000000000000000006"

FAMILIES: Mapping[str, tuple[str, str]] = {
    "doubleword, character-set and base-displacement types": (TYPES, TYPES_IMAGE),
}
