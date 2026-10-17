"""IS NUMERIC decided from the stored bytes of a zoned or packed decimal item."""

import pytest

from interpreter.cobol.numeric_class import packed_is_numeric, zoned_is_numeric


@pytest.mark.parametrize(
    ("data", "signed", "sign_index", "separate", "numeric"),
    [
        (b"\xf1\xf2\xf3", False, 2, False, True),
        (b"\xf1\xf2\xc3", False, 2, False, False),
        (b"\xf1\xf2\xc1\xc2", False, 3, False, False),
        (b"\xf1\xf2\xc3", True, 2, False, True),
        (b"\xf1\xf2\xd3", True, 2, False, True),
        (b"\xf1\xf2\xf3", True, 2, False, True),
        (b"\xf1\xf2\xe3", True, 2, False, False),
        (b"\xf1\xc2\xc3", True, 2, False, False),
        (b"\xc1\xf2\xf3", True, 0, False, True),
        (b"\x4e\xf2\xf3", True, 0, True, True),
        (b"\xf2\xf3\x60", True, 2, True, True),
        (b"\xf2\xf3\xf4", True, 2, True, False),
        (b"\x40\xf3\x60", True, 2, True, False),
        (b"\x00\x00", False, 1, False, False),
    ],
)
def test_zoned_digits_and_sign(
    data: bytes, signed: bool, sign_index: int, separate: bool, numeric: bool
) -> None:
    assert zoned_is_numeric(list(data), signed, sign_index, separate) is numeric


@pytest.mark.parametrize(
    ("data", "signed", "numeric"),
    [
        (b"\x12\x3f", False, True),
        (b"\x12\x3c", False, False),
        (b"\x12\x3c", True, True),
        (b"\x12\x3d", True, True),
        (b"\x12\x3f", True, True),
        (b"\x12\x3e", True, False),
        (b"\x1a\x3c", True, False),
        (b"\xa2\x3c", True, False),
    ],
)
def test_packed_digit_and_sign_nibbles(
    data: bytes, signed: bool, numeric: bool
) -> None:
    assert packed_is_numeric(list(data), signed) is numeric
