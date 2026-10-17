"""IS NUMERIC decided from the stored bytes of a zoned or packed decimal item."""

from __future__ import annotations

from collections.abc import Sequence

_DIGIT_ZONE = 0xF
_SIGNED_NIBBLES = frozenset({0xC, 0xD, 0xF})
_UNSIGNED_NIBBLES = frozenset({0xF})
_SEPARATE_SIGNS = frozenset({0x4E, 0x60})


def _is_digit(nibble: int) -> bool:
    return nibble <= 9


def _is_digit_byte(byte: int) -> bool:
    return byte >> 4 == _DIGIT_ZONE and _is_digit(byte & 0xF)


def _sign_nibbles(signed: bool) -> frozenset[int]:
    return _SIGNED_NIBBLES if signed else _UNSIGNED_NIBBLES


def _digits_apart_from(data: Sequence[int], sign_index: int) -> bool:
    return all(_is_digit_byte(byte) for i, byte in enumerate(data) if i != sign_index)


def _valid_sign_byte(byte: int, signed: bool, separate: bool) -> bool:
    if separate:
        return byte in _SEPARATE_SIGNS
    return byte >> 4 in _sign_nibbles(signed) and _is_digit(byte & 0xF)


def zoned_is_numeric(
    data: Sequence[int], signed: bool, sign_index: int, separate: bool
) -> bool:
    """Every byte a zoned digit, the sign position carrying a valid sign: C, D
    or F zone over a digit, or a separate '+' / '-'; an unsigned item only the
    F zone (IBM Enterprise COBOL LR, class condition)."""
    return _digits_apart_from(data, sign_index) and _valid_sign_byte(
        data[sign_index], signed, separate
    )


def packed_is_numeric(data: Sequence[int], signed: bool) -> bool:
    """Every digit nibble 0-9 and the sign nibble C, D or F when signed, F when
    not (IBM Enterprise COBOL LR, class condition)."""
    nibbles = [nibble for byte in data for nibble in (byte >> 4, byte & 0xF)]
    return all(_is_digit(nibble) for nibble in nibbles[:-1]) and (
        nibbles[-1] in _sign_nibbles(signed)
    )
