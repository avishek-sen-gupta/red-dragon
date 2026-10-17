"""The kind of literal an ALPHABET clause's literal phrase is written with."""

from enum import StrEnum


class AlphabetLiteralKind(StrEnum):
    """A NUMERIC literal is an ordinal position in the native character set."""

    NONNUMERIC = "NONNUMERIC"
    NUMERIC = "NUMERIC"
    FIGURATIVE = "FIGURATIVE"
