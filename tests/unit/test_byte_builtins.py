"""Tests for primitive byte-manipulation builtins."""

from interpreter.cobol.byte_builtins import (
    _builtin_nibble_get,
    _builtin_nibble_set,
    _builtin_byte_from_int,
    _builtin_int_from_byte,
    _builtin_bytes_to_string,
    _builtin_string_to_bytes,
    _builtin_list_get,
    _builtin_list_set,
    _builtin_list_len,
    _builtin_list_slice,
    _builtin_list_concat,
    _builtin_make_list,
    _builtin_cobol_prepare_digits,
    _builtin_cobol_prepare_sign,
    _builtin_int_to_binary_bytes,
    _builtin_binary_bytes_to_int,
    _builtin_float_to_bytes,
    _builtin_bytes_to_float,
    _builtin_cobol_blank_when_zero,
    _builtin_string_find,
    _builtin_string_split,
    _builtin_string_count,
    _builtin_string_replace,
    _builtin_string_concat,
    _builtin_string_concat_pair,
    BYTE_BUILTINS,
)
from interpreter.vm import Operators
from interpreter.vm_types import SymbolicValue

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


class TestNibbleGet:
    def test_high_nibble(self):
        assert _builtin_nibble_get([0xAB, "high"], None) == 0x0A

    def test_low_nibble(self):
        assert _builtin_nibble_get([0xAB, "low"], None) == 0x0B

    def test_zero_byte(self):
        assert _builtin_nibble_get([0x00, "high"], None) == 0
        assert _builtin_nibble_get([0x00, "low"], None) == 0

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_nibble_get([sym, "high"], None) is _UNCOMPUTABLE

    def test_invalid_position(self):
        assert _builtin_nibble_get([0xAB, "mid"], None) is _UNCOMPUTABLE


class TestNibbleSet:
    def test_set_high(self):
        assert _builtin_nibble_set([0x0B, "high", 0x0A], None) == 0xAB

    def test_set_low(self):
        assert _builtin_nibble_set([0xA0, "low", 0x0B], None) == 0xAB

    def test_replace_high(self):
        assert _builtin_nibble_set([0xF5, "high", 0x0C], None) == 0xC5

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_nibble_set([sym, "high", 5], None) is _UNCOMPUTABLE


class TestByteFromInt:
    def test_normal_value(self):
        assert _builtin_byte_from_int([42], None) == 42

    def test_clamp_overflow(self):
        assert _builtin_byte_from_int([256], None) == 0
        assert _builtin_byte_from_int([0x1FF], None) == 0xFF

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_byte_from_int([sym], None) is _UNCOMPUTABLE


class TestIntFromByte:
    def test_identity(self):
        assert _builtin_int_from_byte([42], None) == 42

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_int_from_byte([sym], None) is _UNCOMPUTABLE


class TestBytesToString:
    def test_ascii_decode(self):
        assert _builtin_bytes_to_string([[72, 73], "ascii"], None) == "HI"

    def test_ebcdic_decode(self):
        # 0xC8 = EBCDIC 'H', 0xC9 = EBCDIC 'I'
        assert _builtin_bytes_to_string([[0xC8, 0xC9], "ebcdic"], None) == "HI"

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_bytes_to_string([sym, "ascii"], None) is _UNCOMPUTABLE


class TestStringToBytes:
    def test_ascii_encode(self):
        assert _builtin_string_to_bytes(["HI", "ascii"], None) == [72, 73]

    def test_ebcdic_encode(self):
        result = _builtin_string_to_bytes(["HI", "ebcdic"], None)
        assert result == [0xC8, 0xC9]

    def test_round_trip_ebcdic(self):
        encoded = _builtin_string_to_bytes(["HELLO", "ebcdic"], None)
        decoded = _builtin_bytes_to_string([encoded, "ebcdic"], None)
        assert decoded == "HELLO"

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_string_to_bytes([sym, "ascii"], None) is _UNCOMPUTABLE


class TestListGet:
    def test_get_element(self):
        assert _builtin_list_get([[10, 20, 30], 1], None) == 20

    def test_out_of_bounds(self):
        assert _builtin_list_get([[10], 5], None) is _UNCOMPUTABLE

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_list_get([sym, 0], None) is _UNCOMPUTABLE


class TestListSet:
    def test_set_element(self):
        result = _builtin_list_set([[10, 20, 30], 1, 99], None)
        assert result == [10, 99, 30]

    def test_returns_new_list(self):
        original = [10, 20, 30]
        result = _builtin_list_set([original, 1, 99], None)
        assert original == [10, 20, 30]  # original unchanged
        assert result == [10, 99, 30]


class TestListLen:
    def test_length(self):
        assert _builtin_list_len([[1, 2, 3]], None) == 3

    def test_empty(self):
        assert _builtin_list_len([[]], None) == 0


class TestListSlice:
    def test_slice(self):
        assert _builtin_list_slice([[1, 2, 3, 4, 5], 1, 3], None) == [2, 3]

    def test_full_slice(self):
        assert _builtin_list_slice([[1, 2, 3], 0, 3], None) == [1, 2, 3]


class TestListConcat:
    def test_concat(self):
        assert _builtin_list_concat([[1, 2], [3, 4]], None) == [1, 2, 3, 4]

    def test_concat_empty(self):
        assert _builtin_list_concat([[], [1]], None) == [1]


class TestMakeList:
    def test_make_list(self):
        assert _builtin_make_list([5, 0], None) == [0, 0, 0, 0, 0]

    def test_make_list_with_fill(self):
        assert _builtin_make_list([3, 0xF0], None) == [0xF0, 0xF0, 0xF0]


class TestByteBuiltinsRegistration:
    def test_all_builtins_registered(self):
        expected_names = [
            "__nibble_get",
            "__nibble_set",
            "__byte_from_int",
            "__int_from_byte",
            "__bytes_to_string",
            "__string_to_bytes",
            "__list_get",
            "__list_set",
            "__list_len",
            "__list_slice",
            "__list_concat",
            "__make_list",
            "__cobol_prepare_digits",
            "__cobol_prepare_sign",
            "__string_find",
            "__string_split",
            "__string_count",
            "__string_replace",
            "__string_concat",
            "__string_concat_pair",
            "__int_to_binary_bytes",
            "__binary_bytes_to_int",
            "__float_to_bytes",
            "__bytes_to_float",
            "__cobol_blank_when_zero",
        ]
        for name in expected_names:
            assert name in BYTE_BUILTINS, f"{name} not in BYTE_BUILTINS"
        assert set(expected_names) == set(BYTE_BUILTINS.keys()), (
            f"Mismatch: expected {set(expected_names) - set(BYTE_BUILTINS.keys())} missing, "
            f"unexpected {set(BYTE_BUILTINS.keys()) - set(expected_names)} extra"
        )

    def test_builtins_merged_into_table(self):
        from interpreter.builtins import Builtins

        for name in BYTE_BUILTINS:
            assert name in Builtins.TABLE, f"{name} not in Builtins.TABLE"


class TestCobolPrepareDigits:
    """Tests for __cobol_prepare_digits numeric encoding."""

    def test_integer_string_pic9_4(self):
        """PIC 9(4), value '10' → [0, 0, 1, 0]."""
        assert _builtin_cobol_prepare_digits(["10", 4, 0, False], None) == [0, 0, 1, 0]

    def test_float_string_no_decimals(self):
        """PIC 9(4), value '10.0' → [0, 0, 1, 0] (fractional part discarded)."""
        assert _builtin_cobol_prepare_digits(["10.0", 4, 0, False], None) == [
            0,
            0,
            1,
            0,
        ]

    def test_float_string_large_value(self):
        """PIC 9(4), value '105.0' → [0, 1, 0, 5]."""
        assert _builtin_cobol_prepare_digits(["105.0", 4, 0, False], None) == [
            0,
            1,
            0,
            5,
        ]

    def test_float_string_zero(self):
        """PIC 9(4), value '0.0' → [0, 0, 0, 0]."""
        assert _builtin_cobol_prepare_digits(["0.0", 4, 0, False], None) == [0, 0, 0, 0]

    def test_float_string_one(self):
        """PIC 9(4), value '1.0' → [0, 0, 0, 1]."""
        assert _builtin_cobol_prepare_digits(["1.0", 4, 0, False], None) == [0, 0, 0, 1]

    def test_float_string_with_fractional_discarded(self):
        """PIC 9(4), value '15.75' → [0, 0, 1, 5] (fractional part discarded)."""
        assert _builtin_cobol_prepare_digits(["15.75", 4, 0, False], None) == [
            0,
            0,
            1,
            5,
        ]

    def test_integer_fills_all_digits(self):
        """PIC 9(4), value '9999' → [9, 9, 9, 9]."""
        assert _builtin_cobol_prepare_digits(["9999", 4, 0, False], None) == [
            9,
            9,
            9,
            9,
        ]

    def test_integer_zero(self):
        """PIC 9(4), value '0' → [0, 0, 0, 0]."""
        assert _builtin_cobol_prepare_digits(["0", 4, 0, False], None) == [0, 0, 0, 0]

    def test_with_decimal_digits(self):
        """PIC 9(2)V9(2), value '12.34' → [1, 2, 3, 4]."""
        assert _builtin_cobol_prepare_digits(["12.34", 4, 2, False], None) == [
            1,
            2,
            3,
            4,
        ]

    def test_with_decimal_digits_padding(self):
        """PIC 9(2)V9(2), value '5.1' → [0, 5, 1, 0]."""
        assert _builtin_cobol_prepare_digits(["5.1", 4, 2, False], None) == [0, 5, 1, 0]

    def test_signed_positive_strips_plus(self):
        """Positive signed value strips '+' prefix."""
        assert _builtin_cobol_prepare_digits(["+25", 4, 0, True], None) == [0, 0, 2, 5]

    def test_signed_negative_strips_minus(self):
        """Negative signed value strips '-' prefix."""
        assert _builtin_cobol_prepare_digits(["-5", 4, 0, True], None) == [0, 0, 0, 5]

    def test_signed_negative_float(self):
        """Negative float value: '-5.0' → [0, 0, 0, 5]."""
        assert _builtin_cobol_prepare_digits(["-5.0", 4, 0, True], None) == [0, 0, 0, 5]

    def test_single_digit_pic(self):
        """PIC 9, value '7' → [7]."""
        assert _builtin_cobol_prepare_digits(["7", 1, 0, False], None) == [7]

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_cobol_prepare_digits([sym, 4, 0, False], None) is _UNCOMPUTABLE

    def test_too_few_args_returns_uncomputable(self):
        assert _builtin_cobol_prepare_digits(["10", 4], None) is _UNCOMPUTABLE

    def test_int_value_coerced_to_string(self):
        """Integer 42 should be coerced to '42' and produce [0, 0, 4, 2]."""
        assert _builtin_cobol_prepare_digits([42, 4, 0, False], None) == [0, 0, 4, 2]

    def test_float_value_coerced_to_string(self):
        """Float 10.0 should be coerced to '10.0' → fractional discarded → [0, 0, 1, 0]."""
        assert _builtin_cobol_prepare_digits([10.0, 4, 0, False], None) == [0, 0, 1, 0]

    def test_negative_int_coerced(self):
        """Negative int -5 should be coerced to '-5' → [0, 0, 0, 5]."""
        assert _builtin_cobol_prepare_digits([-5, 4, 0, True], None) == [0, 0, 0, 5]

    def test_non_numeric_value_returns_uncomputable(self):
        assert _builtin_cobol_prepare_digits([[], 4, 0, False], None) is _UNCOMPUTABLE


class TestCobolPrepareSign:
    """Tests for __cobol_prepare_sign numeric encoding."""

    def test_unsigned_returns_0xf(self):
        assert _builtin_cobol_prepare_sign(["10", False], None) == 0x0F

    def test_signed_positive(self):
        assert _builtin_cobol_prepare_sign(["10", True], None) == 0x0C

    def test_signed_negative(self):
        assert _builtin_cobol_prepare_sign(["-10", True], None) == 0x0D

    def test_signed_negative_zero(self):
        """Negative zero is treated as positive."""
        assert _builtin_cobol_prepare_sign(["-0", True], None) == 0x0C

    def test_signed_positive_with_plus(self):
        assert _builtin_cobol_prepare_sign(["+5", True], None) == 0x0C

    def test_signed_negative_float(self):
        assert _builtin_cobol_prepare_sign(["-5.0", True], None) == 0x0D

    def test_unsigned_negative_still_unsigned(self):
        """Unsigned field ignores sign in value string."""
        assert _builtin_cobol_prepare_sign(["-10", False], None) == 0x0F

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_cobol_prepare_sign([sym, True], None) is _UNCOMPUTABLE

    def test_too_few_args_returns_uncomputable(self):
        assert _builtin_cobol_prepare_sign(["10"], None) is _UNCOMPUTABLE

    def test_int_value_coerced(self):
        """Integer 10 should be coerced to '10' → positive."""
        assert _builtin_cobol_prepare_sign([10, True], None) == 0x0C

    def test_negative_float_coerced(self):
        """Float -5.0 should be coerced to '-5.0' → negative."""
        assert _builtin_cobol_prepare_sign([-5.0, True], None) == 0x0D

    def test_non_numeric_returns_uncomputable(self):
        assert _builtin_cobol_prepare_sign([[], True], None) is _UNCOMPUTABLE


class TestIntToBinaryBytes:
    """Tests for __int_to_binary_bytes builtin."""

    def test_positive_signed(self):
        result = _builtin_int_to_binary_bytes([1234, 2, True], None)
        assert result == list((1234).to_bytes(2, "big", signed=True))

    def test_negative_signed(self):
        result = _builtin_int_to_binary_bytes([-1234, 2, True], None)
        assert result == list((-1234).to_bytes(2, "big", signed=True))

    def test_unsigned(self):
        result = _builtin_int_to_binary_bytes([1234, 2, False], None)
        assert result == list((1234).to_bytes(2, "big", signed=False))

    def test_four_bytes(self):
        result = _builtin_int_to_binary_bytes([100000, 4, False], None)
        assert result == list((100000).to_bytes(4, "big", signed=False))

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_int_to_binary_bytes([sym, 2, True], None) is _UNCOMPUTABLE


class TestBinaryBytesToInt:
    """Tests for __binary_bytes_to_int builtin."""

    def test_positive_signed(self):
        data = list((1234).to_bytes(2, "big", signed=True))
        assert _builtin_binary_bytes_to_int([data, True], None) == 1234

    def test_negative_signed(self):
        data = list((-1234).to_bytes(2, "big", signed=True))
        assert _builtin_binary_bytes_to_int([data, True], None) == -1234

    def test_unsigned(self):
        data = list((1234).to_bytes(2, "big", signed=False))
        assert _builtin_binary_bytes_to_int([data, False], None) == 1234

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_binary_bytes_to_int([sym, True], None) is _UNCOMPUTABLE


class TestFloatToBytes:
    """Tests for __float_to_bytes builtin."""

    def test_single_precision(self):
        import struct

        result = _builtin_float_to_bytes([3.14, 4], None)
        assert result == list(struct.pack(">f", 3.14))

    def test_double_precision(self):
        import struct

        result = _builtin_float_to_bytes([3.14, 8], None)
        assert result == list(struct.pack(">d", 3.14))

    def test_integer_coerced_to_float(self):
        import struct

        result = _builtin_float_to_bytes([42, 4], None)
        assert result == list(struct.pack(">f", 42.0))

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_float_to_bytes([sym, 4], None) is _UNCOMPUTABLE


class TestBytesToFloat:
    """Tests for __bytes_to_float builtin."""

    def test_single_precision(self):
        import struct

        data = list(struct.pack(">f", 3.14))
        result = _builtin_bytes_to_float([data, 4], None)
        assert abs(result - 3.14) < 1e-5

    def test_double_precision(self):
        import struct

        data = list(struct.pack(">d", 3.14))
        result = _builtin_bytes_to_float([data, 8], None)
        assert abs(result - 3.14) < 1e-10

    def test_round_trip_single(self):
        encoded = _builtin_float_to_bytes([42.0, 4], None)
        decoded = _builtin_bytes_to_float([encoded, 4], None)
        assert decoded == 42.0

    def test_round_trip_double(self):
        encoded = _builtin_float_to_bytes([42.0, 8], None)
        decoded = _builtin_bytes_to_float([encoded, 8], None)
        assert decoded == 42.0

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_bytes_to_float([sym, 4], None) is _UNCOMPUTABLE


class TestStringFind:
    """Tests for __string_find builtin."""

    def test_found(self):
        assert _builtin_string_find(["hello world", "world"], None) == 6

    def test_not_found(self):
        assert _builtin_string_find(["hello", "xyz"], None) == -1

    def test_empty_needle(self):
        assert _builtin_string_find(["hello", ""], None) == 0

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_string_find([sym, "a"], None) is _UNCOMPUTABLE

    def test_too_few_args_returns_uncomputable(self):
        assert _builtin_string_find(["hello"], None) is _UNCOMPUTABLE


class TestStringSplit:
    """Tests for __string_split builtin."""

    def test_split(self):
        assert _builtin_string_split(["a,b,c", ","], None) == ["a", "b", "c"]

    def test_no_delimiter_match(self):
        assert _builtin_string_split(["hello", ","], None) == ["hello"]

    def test_empty_delimiter_returns_single_element_list(self):
        assert _builtin_string_split(["hello", ""], None) == ["hello"]

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_string_split([sym, ","], None) is _UNCOMPUTABLE


class TestStringCount:
    """Tests for __string_count builtin."""

    def test_all_mode(self):
        assert _builtin_string_count(["abcabc", "abc", "all"], None) == 2

    def test_all_mode_no_match(self):
        assert _builtin_string_count(["hello", "xyz", "all"], None) == 0

    def test_leading_mode(self):
        assert _builtin_string_count(["aaab", "a", "leading"], None) == 3

    def test_leading_mode_no_leading(self):
        assert _builtin_string_count(["baaa", "a", "leading"], None) == 0

    def test_characters_mode(self):
        assert _builtin_string_count(["hello", "", "characters"], None) == 5

    def test_unknown_mode_returns_uncomputable(self):
        assert _builtin_string_count(["hello", "l", "unknown"], None) is _UNCOMPUTABLE

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_string_count([sym, "a", "all"], None) is _UNCOMPUTABLE


class TestStringReplace:
    """Tests for __string_replace builtin."""

    def test_all_mode(self):
        assert _builtin_string_replace(["aXaXa", "X", "Y", "all"], None) == "aYaYa"

    def test_first_mode(self):
        assert _builtin_string_replace(["aXaXa", "X", "Y", "first"], None) == "aYaXa"

    def test_leading_mode(self):
        # "XXa" → replace leading "X" with "Y" → "YXa" (result no longer starts with "X")
        assert _builtin_string_replace(["XXa", "X", "Y", "leading"], None) == "YXa"

    def test_leading_mode_repeating(self):
        # "XXXb" with from="XX" → "YXb" (one leading match consumed)
        assert _builtin_string_replace(["XXXb", "XX", "Y", "leading"], None) == "YXb"

    def test_empty_from_pat_returns_source(self):
        assert _builtin_string_replace(["hello", "", "Y", "all"], None) == "hello"

    def test_unknown_mode_returns_uncomputable(self):
        assert (
            _builtin_string_replace(["a", "a", "b", "unknown"], None) is _UNCOMPUTABLE
        )

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_string_replace([sym, "a", "b", "all"], None) is _UNCOMPUTABLE


class TestStringConcat:
    """Tests for __string_concat builtin."""

    def test_concat_list(self):
        assert _builtin_string_concat([["a", "b", "c"]], None) == "abc"

    def test_empty_list(self):
        assert _builtin_string_concat([[]], None) == ""

    def test_single_element(self):
        assert _builtin_string_concat([["hello"]], None) == "hello"

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_string_concat([sym], None) is _UNCOMPUTABLE


class TestStringConcatPair:
    """Tests for __string_concat_pair builtin."""

    def test_concat_pair(self):
        assert _builtin_string_concat_pair(["hello", " world"], None) == "hello world"

    def test_coerces_to_string(self):
        assert _builtin_string_concat_pair([42, "!"], None) == "42!"

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_string_concat_pair([sym, "a"], None) is _UNCOMPUTABLE


class TestCobolBlankWhenZero:
    """Tests for __cobol_blank_when_zero builtin."""

    def test_zero_value_returns_spaces(self):
        """When value is zero, return EBCDIC spaces (0x40)."""
        encoded = [0xF0, 0xF0, 0xF0]
        result = _builtin_cobol_blank_when_zero([encoded, "0", 3], None)
        assert result == [0x40, 0x40, 0x40]

    def test_non_zero_value_returns_encoded(self):
        """When value is non-zero, return original encoded bytes."""
        encoded = [0xF1, 0xF2, 0xF3]
        result = _builtin_cobol_blank_when_zero([encoded, "123", 3], None)
        assert result == [0xF1, 0xF2, 0xF3]

    def test_zero_float_returns_spaces(self):
        """Float zero (0.0) triggers blank replacement."""
        encoded = [0xF0, 0xF0]
        result = _builtin_cobol_blank_when_zero([encoded, "0.0", 2], None)
        assert result == [0x40, 0x40]

    def test_negative_zero_returns_spaces(self):
        """Negative zero is still zero."""
        encoded = [0xF0, 0xF0]
        result = _builtin_cobol_blank_when_zero([encoded, "-0", 2], None)
        assert result == [0x40, 0x40]

    def test_non_numeric_string_returns_encoded(self):
        """Non-numeric value string returns encoded bytes unchanged."""
        encoded = [0xC1, 0xC2]
        result = _builtin_cobol_blank_when_zero([encoded, "AB", 2], None)
        assert result == [0xC1, 0xC2]

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert _builtin_cobol_blank_when_zero([sym, "0", 3], None) is _UNCOMPUTABLE

    def test_too_few_args_returns_uncomputable(self):
        assert _builtin_cobol_blank_when_zero([[0xF0], "0"], None) is _UNCOMPUTABLE

    def test_registered_in_builtins(self):
        assert "__cobol_blank_when_zero" in BYTE_BUILTINS
