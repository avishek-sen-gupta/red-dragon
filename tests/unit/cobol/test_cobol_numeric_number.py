"""cobol_numeric.number — the exact COBOL value boundary (red-dragon-4q25.1)."""

from __future__ import annotations

import pytest

from cobol_numeric.number import (
    add,
    as_whole_int,
    digits_for_encode,
    divide,
    from_digits,
    from_float,
    from_literal,
    is_cobol_number,
    multiply,
    round_half_up,
    scale_by,
    subtract,
    to_float,
    to_number,
    to_plain_str,
    truncate_to,
)
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_digits_places_the_implied_decimal_point():
    assert from_digits(12345, 2) == from_literal("123.45")
    assert to_plain_str(from_digits(12345, 2)) == "123.45"
    assert to_plain_str(from_digits(-5, 3)) == "-0.005"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_digits_keeps_trailing_zeros_of_the_scale():
    assert to_plain_str(from_digits(80, 2)) == "0.80"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_scale_by_shifts_without_rounding_beyond_28_digits():
    big = from_literal("123456789012345678901234567890.5")
    assert to_plain_str(scale_by(big, 2)) == "12345678901234567890123456789050"
    assert to_plain_str(scale_by(123, -3)) == "0.123"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_literal_accepts_cobol_fixed_point_literals():
    assert to_plain_str(from_literal("+0.007")) == "0.007"
    assert to_plain_str(from_literal("-12")) == "-12"
    assert to_plain_str(from_literal(".5")) == "0.5"


@pytest.mark.parametrize("text", ["", ".", "1.2.3", "1E5", "NaN", "ABC", "+-1", " "])
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_literal_rejects_non_literals(text):
    with pytest.raises(ValueError):
        from_literal(text)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_float_uses_the_shortest_round_trip_repr():
    assert to_plain_str(from_float(76.59999999999994)) == "76.59999999999994"
    assert to_plain_str(from_float(1e-05)) == "0.00001"
    with pytest.raises(ValueError):
        from_float(float("inf"))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_to_number_normalises_migration_inputs():
    assert to_number(7) == 7
    assert to_number(0.5) == from_literal("0.5")
    assert to_number(" 12.50 ") == from_literal("12.50")
    with pytest.raises(ValueError):
        to_number("SPACES")
    with pytest.raises(TypeError):
        to_number(True)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_is_cobol_number():
    assert is_cobol_number(3)
    assert is_cobol_number(from_literal("1.5"))
    assert not is_cobol_number(True)
    assert not is_cobol_number(1.5)
    assert not is_cobol_number("1")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_to_float():
    assert to_float(from_literal("0.25")) == 0.25


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_truncate_to_truncates_toward_zero():
    assert to_plain_str(truncate_to(from_literal("1.239"), 2)) == "1.23"
    assert to_plain_str(truncate_to(from_literal("-1.239"), 2)) == "-1.23"
    assert to_plain_str(truncate_to(from_literal("0.129999999"), 2)) == "0.12"
    assert to_plain_str(truncate_to(5, 2)) == "5.00"
    assert to_plain_str(truncate_to(from_literal("-0.001"), 2)) == "0.00"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_round_half_up_rounds_ties_away_from_zero():
    assert to_plain_str(round_half_up(from_literal("1.235"), 2)) == "1.24"
    assert to_plain_str(round_half_up(from_literal("1.234"), 2)) == "1.23"
    assert to_plain_str(round_half_up(from_literal("-1.235"), 2)) == "-1.24"
    assert to_plain_str(round_half_up(from_literal("2.7"), 0)) == "3"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_add_subtract_are_exact_and_truncate_to_result_decimals():
    assert to_plain_str(add(from_literal("0.1"), from_literal("0.7"), 2)) == "0.80"
    assert to_plain_str(add(from_literal("38.30"), from_literal("38.30"), 2)) == "76.60"
    assert to_plain_str(subtract(2023, 2020, 0)) == "3"
    thirty = from_literal("999999999999999999.999999999999")
    assert to_plain_str(add(thirty, from_literal("0.000000000001"), 12)) == (
        "1000000000000000000.000000000000"
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_multiply_is_exact_beyond_28_significant_digits():
    a = from_literal("123456789.123456789")
    b = from_literal("987654321.987654321")
    assert to_plain_str(multiply(a, b, 18)) == "121932631356500531.347203169112635269"
    assert to_plain_str(multiply(from_literal("4.35"), 100, 2)) == "435.00"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_divide_truncates_to_quotient_decimals():
    assert to_plain_str(divide(2023, 4, 0)) == "505"
    assert to_plain_str(divide(7, 2, 1)) == "3.5"
    assert to_plain_str(divide(1, 3, 9)) == "0.333333333"
    assert to_plain_str(divide(-7, 2, 0)) == "-3"
    assert (
        to_plain_str(divide(from_literal("0.99999999999999999999999999999999"), 1, 2))
        == "0.99"
    )
    with pytest.raises(ZeroDivisionError):
        divide(1, 0, 2)


@pytest.mark.parametrize(
    "value, total, decimals, scale, expected",
    [
        ("123.45", 5, 2, 0, (False, "12345")),
        ("-123.45", 5, 2, 0, (True, "12345")),
        ("1.237", 5, 2, 0, (False, "00123")),
        ("12.5", 3, 0, 0, (False, "012")),
        ("12300", 3, 0, 2, (False, "123")),
        ("123456", 3, 0, 0, (False, "456")),
        ("-0.001", 3, 2, 0, (True, "000")),
        ("0", 3, 0, 0, (False, "000")),
        ("0.00001", 6, 5, 0, (False, "000001")),
        ("5", 0, 0, 0, (False, "")),
    ],
)
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_digits_for_encode(value, total, decimals, scale, expected):
    assert digits_for_encode(from_literal(value), total, decimals, scale) == expected


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_digits_for_encode_accepts_int():
    assert digits_for_encode(7, 3, 0) == (False, "007")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_to_plain_str_never_uses_exponent_notation():
    for value in [
        scale_by(1, -10),
        scale_by(123, 3),
        scale_by(-1, -5),
        from_digits(0, 2),
    ]:
        rendered = to_plain_str(value)
        assert "E" not in rendered and "e" not in rendered
    assert to_plain_str(scale_by(1, -10)) == "0.0000000001"
    assert to_plain_str(scale_by(123, 3)) == "123000"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_as_whole_int():
    assert as_whole_int(from_literal("12.00")) == 12
    assert as_whole_int(from_literal("12.50")) is None
    assert as_whole_int(-4) == -4
