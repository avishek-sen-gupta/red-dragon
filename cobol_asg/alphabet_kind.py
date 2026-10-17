"""What an ALPHABET clause names: a character set, or the literal phrase."""

from enum import StrEnum


class AlphabetKind(StrEnum):
    """ALIAS is an implementor-name; LITERALS is the literal phrase."""

    NATIVE = "NATIVE"
    EBCDIC = "EBCDIC"
    ASCII = "ASCII"
    STANDARD_1 = "STANDARD-1"
    STANDARD_2 = "STANDARD-2"
    ALIAS = "ALIAS"
    LITERALS = "LITERALS"
