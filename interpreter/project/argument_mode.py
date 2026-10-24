# pyright: standard
"""How a CALL argument reaches its callee: by reference, by content, by value, or omitted."""

from enum import StrEnum


class ArgumentMode(StrEnum):
    REFERENCE = "REFERENCE"
    CONTENT = "CONTENT"
    VALUE = "VALUE"
    OMITTED = "OMITTED"
