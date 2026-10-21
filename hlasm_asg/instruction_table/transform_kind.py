# pyright: standard
"""How an extended mnemonic derives a base-instruction operand."""

from __future__ import annotations

from enum import StrEnum


class TransformKind(StrEnum):
    ADD_TO = "add_to"
    COMPLEMENT = "complement"
    COPY = "copy"
    OR_WITH = "or_with"
    SUBTRACT_FROM = "subtract_from"
    VALUE = "value"
