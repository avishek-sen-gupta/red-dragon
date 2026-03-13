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
from interpreter.typed_value import typed_from_runtime
from interpreter.vm import Operators
from interpreter.vm_types import SymbolicValue

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


class TestNibbleGet:
    def test_high_nibble(self):
        assert (
            _builtin_nibble_get(
                [typed_from_runtime(0xAB), typed_from_runtime("high")], None
            ).value
            == 0x0A
        )

    def test_low_nibble(self):
        assert (
            _builtin_nibble_get(
                [typed_from_runtime(0xAB), typed_from_runtime("low")], None
            ).value
            == 0x0B
        )

    def test_zero_byte(self):
        assert (
            _builtin_nibble_get(
                [typed_from_runtime(0x00), typed_from_runtime("high")], None
            ).value
            == 0
        )
        assert (
            _builtin_nibble_get(
                [typed_from_runtime(0x00), typed_from_runtime("low")], None
            ).value
            == 0
        )

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_nibble_get(
                [typed_from_runtime(sym), typed_from_runtime("high")], None
            ).value
            is _UNCOMPUTABLE
        )

    def test_invalid_position(self):
        assert (
            _builtin_nibble_get(
                [typed_from_runtime(0xAB), typed_from_runtime("mid")], None
            ).value
            is _UNCOMPUTABLE
        )


class TestNibbleSet:
    def test_set_high(self):
        assert (
            _builtin_nibble_set(
                [
                    typed_from_runtime(0x0B),
                    typed_from_runtime("high"),
                    typed_from_runtime(0x0A),
                ],
                None,
            ).value
            == 0xAB
        )

    def test_set_low(self):
        assert (
            _builtin_nibble_set(
                [
                    typed_from_runtime(0xA0),
                    typed_from_runtime("low"),
                    typed_from_runtime(0x0B),
                ],
                None,
            ).value
            == 0xAB
        )

    def test_replace_high(self):
        assert (
            _builtin_nibble_set(
                [
                    typed_from_runtime(0xF5),
                    typed_from_runtime("high"),
                    typed_from_runtime(0x0C),
                ],
                None,
            ).value
            == 0xC5
        )

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_nibble_set(
                [
                    typed_from_runtime(sym),
                    typed_from_runtime("high"),
                    typed_from_runtime(5),
                ],
                None,
            ).value
            is _UNCOMPUTABLE
        )


class TestByteFromInt:
    def test_normal_value(self):
        assert _builtin_byte_from_int([typed_from_runtime(42)], None).value == 42

    def test_clamp_overflow(self):
        assert _builtin_byte_from_int([typed_from_runtime(256)], None).value == 0
        assert _builtin_byte_from_int([typed_from_runtime(0x1FF)], None).value == 0xFF

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_byte_from_int([typed_from_runtime(sym)], None).value
            is _UNCOMPUTABLE
        )


class TestIntFromByte:
    def test_identity(self):
        assert _builtin_int_from_byte([typed_from_runtime(42)], None).value == 42

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_int_from_byte([typed_from_runtime(sym)], None).value
            is _UNCOMPUTABLE
        )


class TestBytesToString:
    def test_ascii_decode(self):
        assert (
            _builtin_bytes_to_string(
                [typed_from_runtime([72, 73]), typed_from_runtime("ascii")], None
            ).value
            == "HI"
        )

    def test_ebcdic_decode(self):
        # 0xC8 = EBCDIC 'H', 0xC9 = EBCDIC 'I'
        assert (
            _builtin_bytes_to_string(
                [typed_from_runtime([0xC8, 0xC9]), typed_from_runtime("ebcdic")], None
            ).value
            == "HI"
        )

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_bytes_to_string(
                [typed_from_runtime(sym), typed_from_runtime("ascii")], None
            ).value
            is _UNCOMPUTABLE
        )


class TestStringToBytes:
    def test_ascii_encode(self):
        assert _builtin_string_to_bytes(
            [typed_from_runtime("HI"), typed_from_runtime("ascii")], None
        ).value == [72, 73]

    def test_ebcdic_encode(self):
        result = _builtin_string_to_bytes(
            [typed_from_runtime("HI"), typed_from_runtime("ebcdic")], None
        ).value
        assert result == [0xC8, 0xC9]

    def test_round_trip_ebcdic(self):
        encoded = _builtin_string_to_bytes(
            [typed_from_runtime("HELLO"), typed_from_runtime("ebcdic")], None
        ).value
        decoded = _builtin_bytes_to_string(
            [typed_from_runtime(encoded), typed_from_runtime("ebcdic")], None
        ).value
        assert decoded == "HELLO"

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_string_to_bytes(
                [typed_from_runtime(sym), typed_from_runtime("ascii")], None
            ).value
            is _UNCOMPUTABLE
        )


class TestListGet:
    def test_get_element(self):
        assert (
            _builtin_list_get(
                [typed_from_runtime([10, 20, 30]), typed_from_runtime(1)], None
            ).value
            == 20
        )

    def test_out_of_bounds(self):
        assert (
            _builtin_list_get(
                [typed_from_runtime([10]), typed_from_runtime(5)], None
            ).value
            is _UNCOMPUTABLE
        )

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_list_get(
                [typed_from_runtime(sym), typed_from_runtime(0)], None
            ).value
            is _UNCOMPUTABLE
        )


class TestListSet:
    def test_set_element(self):
        result = _builtin_list_set(
            [
                typed_from_runtime([10, 20, 30]),
                typed_from_runtime(1),
                typed_from_runtime(99),
            ],
            None,
        ).value
        assert result == [10, 99, 30]

    def test_returns_new_list(self):
        original = [10, 20, 30]
        result = _builtin_list_set(
            [
                typed_from_runtime(original),
                typed_from_runtime(1),
                typed_from_runtime(99),
            ],
            None,
        ).value
        assert original == [10, 20, 30]  # original unchanged
        assert result == [10, 99, 30]


class TestListLen:
    def test_length(self):
        assert _builtin_list_len([typed_from_runtime([1, 2, 3])], None).value == 3

    def test_empty(self):
        assert _builtin_list_len([typed_from_runtime([])], None).value == 0


class TestListSlice:
    def test_slice(self):
        assert _builtin_list_slice(
            [
                typed_from_runtime([1, 2, 3, 4, 5]),
                typed_from_runtime(1),
                typed_from_runtime(3),
            ],
            None,
        ).value == [2, 3]

    def test_full_slice(self):
        assert _builtin_list_slice(
            [
                typed_from_runtime([1, 2, 3]),
                typed_from_runtime(0),
                typed_from_runtime(3),
            ],
            None,
        ).value == [1, 2, 3]


class TestListConcat:
    def test_concat(self):
        assert _builtin_list_concat(
            [typed_from_runtime([1, 2]), typed_from_runtime([3, 4])], None
        ).value == [1, 2, 3, 4]

    def test_concat_empty(self):
        assert _builtin_list_concat(
            [typed_from_runtime([]), typed_from_runtime([1])], None
        ).value == [1]


class TestMakeList:
    def test_make_list(self):
        assert _builtin_make_list(
            [typed_from_runtime(5), typed_from_runtime(0)], None
        ).value == [0, 0, 0, 0, 0]

    def test_make_list_with_fill(self):
        assert _builtin_make_list(
            [typed_from_runtime(3), typed_from_runtime(0xF0)], None
        ).value == [0xF0, 0xF0, 0xF0]


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
        """PIC 9(4), value '10' -> [0, 0, 1, 0]."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("10"),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(False),
            ],
            None,
        ).value == [
            0,
            0,
            1,
            0,
        ]

    def test_float_string_no_decimals(self):
        """PIC 9(4), value '10.0' -> [0, 0, 1, 0] (fractional part discarded)."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("10.0"),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(False),
            ],
            None,
        ).value == [
            0,
            0,
            1,
            0,
        ]

    def test_float_string_large_value(self):
        """PIC 9(4), value '105.0' -> [0, 1, 0, 5]."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("105.0"),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(False),
            ],
            None,
        ).value == [
            0,
            1,
            0,
            5,
        ]

    def test_float_string_zero(self):
        """PIC 9(4), value '0.0' -> [0, 0, 0, 0]."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("0.0"),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(False),
            ],
            None,
        ).value == [
            0,
            0,
            0,
            0,
        ]

    def test_float_string_one(self):
        """PIC 9(4), value '1.0' -> [0, 0, 0, 1]."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("1.0"),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(False),
            ],
            None,
        ).value == [
            0,
            0,
            0,
            1,
        ]

    def test_float_string_with_fractional_discarded(self):
        """PIC 9(4), value '15.75' -> [0, 0, 1, 5] (fractional part discarded)."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("15.75"),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(False),
            ],
            None,
        ).value == [
            0,
            0,
            1,
            5,
        ]

    def test_integer_fills_all_digits(self):
        """PIC 9(4), value '9999' -> [9, 9, 9, 9]."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("9999"),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(False),
            ],
            None,
        ).value == [
            9,
            9,
            9,
            9,
        ]

    def test_integer_zero(self):
        """PIC 9(4), value '0' -> [0, 0, 0, 0]."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("0"),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(False),
            ],
            None,
        ).value == [
            0,
            0,
            0,
            0,
        ]

    def test_with_decimal_digits(self):
        """PIC 9(2)V9(2), value '12.34' -> [1, 2, 3, 4]."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("12.34"),
                typed_from_runtime(4),
                typed_from_runtime(2),
                typed_from_runtime(False),
            ],
            None,
        ).value == [
            1,
            2,
            3,
            4,
        ]

    def test_with_decimal_digits_padding(self):
        """PIC 9(2)V9(2), value '5.1' -> [0, 5, 1, 0]."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("5.1"),
                typed_from_runtime(4),
                typed_from_runtime(2),
                typed_from_runtime(False),
            ],
            None,
        ).value == [
            0,
            5,
            1,
            0,
        ]

    def test_signed_positive_strips_plus(self):
        """Positive signed value strips '+' prefix."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("+25"),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(True),
            ],
            None,
        ).value == [
            0,
            0,
            2,
            5,
        ]

    def test_signed_negative_strips_minus(self):
        """Negative signed value strips '-' prefix."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("-5"),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(True),
            ],
            None,
        ).value == [
            0,
            0,
            0,
            5,
        ]

    def test_signed_negative_float(self):
        """Negative float value: '-5.0' -> [0, 0, 0, 5]."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("-5.0"),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(True),
            ],
            None,
        ).value == [
            0,
            0,
            0,
            5,
        ]

    def test_single_digit_pic(self):
        """PIC 9, value '7' -> [7]."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("7"),
                typed_from_runtime(1),
                typed_from_runtime(0),
                typed_from_runtime(False),
            ],
            None,
        ).value == [7]

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_cobol_prepare_digits(
                [
                    typed_from_runtime(sym),
                    typed_from_runtime(4),
                    typed_from_runtime(0),
                    typed_from_runtime(False),
                ],
                None,
            ).value
            is _UNCOMPUTABLE
        )

    def test_too_few_args_returns_uncomputable(self):
        assert (
            _builtin_cobol_prepare_digits(
                [typed_from_runtime("10"), typed_from_runtime(4)], None
            ).value
            is _UNCOMPUTABLE
        )

    def test_int_value_coerced_to_string(self):
        """Integer 42 should be coerced to '42' and produce [0, 0, 4, 2]."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime(42),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(False),
            ],
            None,
        ).value == [
            0,
            0,
            4,
            2,
        ]

    def test_float_value_coerced_to_string(self):
        """Float 10.0 should be coerced to '10.0' -> fractional discarded -> [0, 0, 1, 0]."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime(10.0),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(False),
            ],
            None,
        ).value == [
            0,
            0,
            1,
            0,
        ]

    def test_negative_int_coerced(self):
        """Negative int -5 should be coerced to '-5' -> [0, 0, 0, 5]."""
        assert _builtin_cobol_prepare_digits(
            [
                typed_from_runtime(-5),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(True),
            ],
            None,
        ).value == [
            0,
            0,
            0,
            5,
        ]

    def test_non_numeric_value_returns_uncomputable(self):
        assert (
            _builtin_cobol_prepare_digits(
                [
                    typed_from_runtime([]),
                    typed_from_runtime(4),
                    typed_from_runtime(0),
                    typed_from_runtime(False),
                ],
                None,
            ).value
            is _UNCOMPUTABLE
        )


class TestCobolPrepareSign:
    """Tests for __cobol_prepare_sign numeric encoding."""

    def test_unsigned_returns_0xf(self):
        assert (
            _builtin_cobol_prepare_sign(
                [typed_from_runtime("10"), typed_from_runtime(False)], None
            ).value
            == 0x0F
        )

    def test_signed_positive(self):
        assert (
            _builtin_cobol_prepare_sign(
                [typed_from_runtime("10"), typed_from_runtime(True)], None
            ).value
            == 0x0C
        )

    def test_signed_negative(self):
        assert (
            _builtin_cobol_prepare_sign(
                [typed_from_runtime("-10"), typed_from_runtime(True)], None
            ).value
            == 0x0D
        )

    def test_signed_negative_zero(self):
        """Negative zero is treated as positive."""
        assert (
            _builtin_cobol_prepare_sign(
                [typed_from_runtime("-0"), typed_from_runtime(True)], None
            ).value
            == 0x0C
        )

    def test_signed_positive_with_plus(self):
        assert (
            _builtin_cobol_prepare_sign(
                [typed_from_runtime("+5"), typed_from_runtime(True)], None
            ).value
            == 0x0C
        )

    def test_signed_negative_float(self):
        assert (
            _builtin_cobol_prepare_sign(
                [typed_from_runtime("-5.0"), typed_from_runtime(True)], None
            ).value
            == 0x0D
        )

    def test_unsigned_negative_still_unsigned(self):
        """Unsigned field ignores sign in value string."""
        assert (
            _builtin_cobol_prepare_sign(
                [typed_from_runtime("-10"), typed_from_runtime(False)], None
            ).value
            == 0x0F
        )

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_cobol_prepare_sign(
                [typed_from_runtime(sym), typed_from_runtime(True)], None
            ).value
            is _UNCOMPUTABLE
        )

    def test_too_few_args_returns_uncomputable(self):
        assert (
            _builtin_cobol_prepare_sign([typed_from_runtime("10")], None).value
            is _UNCOMPUTABLE
        )

    def test_int_value_coerced(self):
        """Integer 10 should be coerced to '10' -> positive."""
        assert (
            _builtin_cobol_prepare_sign(
                [typed_from_runtime(10), typed_from_runtime(True)], None
            ).value
            == 0x0C
        )

    def test_negative_float_coerced(self):
        """Float -5.0 should be coerced to '-5.0' -> negative."""
        assert (
            _builtin_cobol_prepare_sign(
                [typed_from_runtime(-5.0), typed_from_runtime(True)], None
            ).value
            == 0x0D
        )

    def test_non_numeric_returns_uncomputable(self):
        assert (
            _builtin_cobol_prepare_sign(
                [typed_from_runtime([]), typed_from_runtime(True)], None
            ).value
            is _UNCOMPUTABLE
        )


class TestIntToBinaryBytes:
    """Tests for __int_to_binary_bytes builtin."""

    def test_positive_signed(self):
        result = _builtin_int_to_binary_bytes(
            [typed_from_runtime(1234), typed_from_runtime(2), typed_from_runtime(True)],
            None,
        ).value
        assert result == list((1234).to_bytes(2, "big", signed=True))

    def test_negative_signed(self):
        result = _builtin_int_to_binary_bytes(
            [
                typed_from_runtime(-1234),
                typed_from_runtime(2),
                typed_from_runtime(True),
            ],
            None,
        ).value
        assert result == list((-1234).to_bytes(2, "big", signed=True))

    def test_unsigned(self):
        result = _builtin_int_to_binary_bytes(
            [
                typed_from_runtime(1234),
                typed_from_runtime(2),
                typed_from_runtime(False),
            ],
            None,
        ).value
        assert result == list((1234).to_bytes(2, "big", signed=False))

    def test_four_bytes(self):
        result = _builtin_int_to_binary_bytes(
            [
                typed_from_runtime(100000),
                typed_from_runtime(4),
                typed_from_runtime(False),
            ],
            None,
        ).value
        assert result == list((100000).to_bytes(4, "big", signed=False))

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_int_to_binary_bytes(
                [
                    typed_from_runtime(sym),
                    typed_from_runtime(2),
                    typed_from_runtime(True),
                ],
                None,
            ).value
            is _UNCOMPUTABLE
        )


class TestBinaryBytesToInt:
    """Tests for __binary_bytes_to_int builtin."""

    def test_positive_signed(self):
        data = list((1234).to_bytes(2, "big", signed=True))
        assert (
            _builtin_binary_bytes_to_int(
                [typed_from_runtime(data), typed_from_runtime(True)], None
            ).value
            == 1234
        )

    def test_negative_signed(self):
        data = list((-1234).to_bytes(2, "big", signed=True))
        assert (
            _builtin_binary_bytes_to_int(
                [typed_from_runtime(data), typed_from_runtime(True)], None
            ).value
            == -1234
        )

    def test_unsigned(self):
        data = list((1234).to_bytes(2, "big", signed=False))
        assert (
            _builtin_binary_bytes_to_int(
                [typed_from_runtime(data), typed_from_runtime(False)], None
            ).value
            == 1234
        )

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_binary_bytes_to_int(
                [typed_from_runtime(sym), typed_from_runtime(True)], None
            ).value
            is _UNCOMPUTABLE
        )


class TestFloatToBytes:
    """Tests for __float_to_bytes builtin."""

    def test_single_precision(self):
        import struct

        result = _builtin_float_to_bytes(
            [typed_from_runtime(3.14), typed_from_runtime(4)], None
        ).value
        assert result == list(struct.pack(">f", 3.14))

    def test_double_precision(self):
        import struct

        result = _builtin_float_to_bytes(
            [typed_from_runtime(3.14), typed_from_runtime(8)], None
        ).value
        assert result == list(struct.pack(">d", 3.14))

    def test_integer_coerced_to_float(self):
        import struct

        result = _builtin_float_to_bytes(
            [typed_from_runtime(42), typed_from_runtime(4)], None
        ).value
        assert result == list(struct.pack(">f", 42.0))

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_float_to_bytes(
                [typed_from_runtime(sym), typed_from_runtime(4)], None
            ).value
            is _UNCOMPUTABLE
        )


class TestBytesToFloat:
    """Tests for __bytes_to_float builtin."""

    def test_single_precision(self):
        import struct

        data = list(struct.pack(">f", 3.14))
        result = _builtin_bytes_to_float(
            [typed_from_runtime(data), typed_from_runtime(4)], None
        ).value
        assert abs(result - 3.14) < 1e-5

    def test_double_precision(self):
        import struct

        data = list(struct.pack(">d", 3.14))
        result = _builtin_bytes_to_float(
            [typed_from_runtime(data), typed_from_runtime(8)], None
        ).value
        assert abs(result - 3.14) < 1e-10

    def test_round_trip_single(self):
        encoded = _builtin_float_to_bytes(
            [typed_from_runtime(42.0), typed_from_runtime(4)], None
        ).value
        decoded = _builtin_bytes_to_float(
            [typed_from_runtime(encoded), typed_from_runtime(4)], None
        ).value
        assert decoded == 42.0

    def test_round_trip_double(self):
        encoded = _builtin_float_to_bytes(
            [typed_from_runtime(42.0), typed_from_runtime(8)], None
        ).value
        decoded = _builtin_bytes_to_float(
            [typed_from_runtime(encoded), typed_from_runtime(8)], None
        ).value
        assert decoded == 42.0

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_bytes_to_float(
                [typed_from_runtime(sym), typed_from_runtime(4)], None
            ).value
            is _UNCOMPUTABLE
        )


class TestStringFind:
    """Tests for __string_find builtin."""

    def test_found(self):
        assert (
            _builtin_string_find(
                [typed_from_runtime("hello world"), typed_from_runtime("world")], None
            ).value
            == 6
        )

    def test_not_found(self):
        assert (
            _builtin_string_find(
                [typed_from_runtime("hello"), typed_from_runtime("xyz")], None
            ).value
            == -1
        )

    def test_empty_needle(self):
        assert (
            _builtin_string_find(
                [typed_from_runtime("hello"), typed_from_runtime("")], None
            ).value
            == 0
        )

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_string_find(
                [typed_from_runtime(sym), typed_from_runtime("a")], None
            ).value
            is _UNCOMPUTABLE
        )

    def test_too_few_args_returns_uncomputable(self):
        assert (
            _builtin_string_find([typed_from_runtime("hello")], None).value
            is _UNCOMPUTABLE
        )


class TestStringSplit:
    """Tests for __string_split builtin."""

    def test_split(self):
        assert _builtin_string_split(
            [typed_from_runtime("a,b,c"), typed_from_runtime(",")], None
        ).value == ["a", "b", "c"]

    def test_no_delimiter_match(self):
        assert _builtin_string_split(
            [typed_from_runtime("hello"), typed_from_runtime(",")], None
        ).value == ["hello"]

    def test_empty_delimiter_returns_single_element_list(self):
        assert _builtin_string_split(
            [typed_from_runtime("hello"), typed_from_runtime("")], None
        ).value == ["hello"]

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_string_split(
                [typed_from_runtime(sym), typed_from_runtime(",")], None
            ).value
            is _UNCOMPUTABLE
        )


class TestStringCount:
    """Tests for __string_count builtin."""

    def test_all_mode(self):
        assert (
            _builtin_string_count(
                [
                    typed_from_runtime("abcabc"),
                    typed_from_runtime("abc"),
                    typed_from_runtime("all"),
                ],
                None,
            ).value
            == 2
        )

    def test_all_mode_no_match(self):
        assert (
            _builtin_string_count(
                [
                    typed_from_runtime("hello"),
                    typed_from_runtime("xyz"),
                    typed_from_runtime("all"),
                ],
                None,
            ).value
            == 0
        )

    def test_leading_mode(self):
        assert (
            _builtin_string_count(
                [
                    typed_from_runtime("aaab"),
                    typed_from_runtime("a"),
                    typed_from_runtime("leading"),
                ],
                None,
            ).value
            == 3
        )

    def test_leading_mode_no_leading(self):
        assert (
            _builtin_string_count(
                [
                    typed_from_runtime("baaa"),
                    typed_from_runtime("a"),
                    typed_from_runtime("leading"),
                ],
                None,
            ).value
            == 0
        )

    def test_characters_mode(self):
        assert (
            _builtin_string_count(
                [
                    typed_from_runtime("hello"),
                    typed_from_runtime(""),
                    typed_from_runtime("characters"),
                ],
                None,
            ).value
            == 5
        )

    def test_unknown_mode_returns_uncomputable(self):
        assert (
            _builtin_string_count(
                [
                    typed_from_runtime("hello"),
                    typed_from_runtime("l"),
                    typed_from_runtime("unknown"),
                ],
                None,
            ).value
            is _UNCOMPUTABLE
        )

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_string_count(
                [
                    typed_from_runtime(sym),
                    typed_from_runtime("a"),
                    typed_from_runtime("all"),
                ],
                None,
            ).value
            is _UNCOMPUTABLE
        )


class TestStringReplace:
    """Tests for __string_replace builtin."""

    def test_all_mode(self):
        assert (
            _builtin_string_replace(
                [
                    typed_from_runtime("aXaXa"),
                    typed_from_runtime("X"),
                    typed_from_runtime("Y"),
                    typed_from_runtime("all"),
                ],
                None,
            ).value
            == "aYaYa"
        )

    def test_first_mode(self):
        assert (
            _builtin_string_replace(
                [
                    typed_from_runtime("aXaXa"),
                    typed_from_runtime("X"),
                    typed_from_runtime("Y"),
                    typed_from_runtime("first"),
                ],
                None,
            ).value
            == "aYaXa"
        )

    def test_leading_mode(self):
        # "XXa" -> replace leading "X" with "Y" -> "YXa" (result no longer starts with "X")
        assert (
            _builtin_string_replace(
                [
                    typed_from_runtime("XXa"),
                    typed_from_runtime("X"),
                    typed_from_runtime("Y"),
                    typed_from_runtime("leading"),
                ],
                None,
            ).value
            == "YXa"
        )

    def test_leading_mode_repeating(self):
        # "XXXb" with from="XX" -> "YXb" (one leading match consumed)
        assert (
            _builtin_string_replace(
                [
                    typed_from_runtime("XXXb"),
                    typed_from_runtime("XX"),
                    typed_from_runtime("Y"),
                    typed_from_runtime("leading"),
                ],
                None,
            ).value
            == "YXb"
        )

    def test_empty_from_pat_returns_source(self):
        assert (
            _builtin_string_replace(
                [
                    typed_from_runtime("hello"),
                    typed_from_runtime(""),
                    typed_from_runtime("Y"),
                    typed_from_runtime("all"),
                ],
                None,
            ).value
            == "hello"
        )

    def test_unknown_mode_returns_uncomputable(self):
        assert (
            _builtin_string_replace(
                [
                    typed_from_runtime("a"),
                    typed_from_runtime("a"),
                    typed_from_runtime("b"),
                    typed_from_runtime("unknown"),
                ],
                None,
            ).value
            is _UNCOMPUTABLE
        )

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_string_replace(
                [
                    typed_from_runtime(sym),
                    typed_from_runtime("a"),
                    typed_from_runtime("b"),
                    typed_from_runtime("all"),
                ],
                None,
            ).value
            is _UNCOMPUTABLE
        )


class TestStringConcat:
    """Tests for __string_concat builtin."""

    def test_concat_list(self):
        assert (
            _builtin_string_concat([typed_from_runtime(["a", "b", "c"])], None).value
            == "abc"
        )

    def test_empty_list(self):
        assert _builtin_string_concat([typed_from_runtime([])], None).value == ""

    def test_single_element(self):
        assert (
            _builtin_string_concat([typed_from_runtime(["hello"])], None).value
            == "hello"
        )

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_string_concat([typed_from_runtime(sym)], None).value
            is _UNCOMPUTABLE
        )


class TestStringConcatPair:
    """Tests for __string_concat_pair builtin."""

    def test_concat_pair(self):
        assert (
            _builtin_string_concat_pair(
                [typed_from_runtime("hello"), typed_from_runtime(" world")], None
            ).value
            == "hello world"
        )

    def test_coerces_to_string(self):
        assert (
            _builtin_string_concat_pair(
                [typed_from_runtime(42), typed_from_runtime("!")], None
            ).value
            == "42!"
        )

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_string_concat_pair(
                [typed_from_runtime(sym), typed_from_runtime("a")], None
            ).value
            is _UNCOMPUTABLE
        )


class TestCobolBlankWhenZero:
    """Tests for __cobol_blank_when_zero builtin."""

    def test_zero_value_returns_spaces(self):
        """When value is zero, return EBCDIC spaces (0x40)."""
        encoded = [0xF0, 0xF0, 0xF0]
        result = _builtin_cobol_blank_when_zero(
            [
                typed_from_runtime(encoded),
                typed_from_runtime("0"),
                typed_from_runtime(3),
            ],
            None,
        ).value
        assert result == [0x40, 0x40, 0x40]

    def test_non_zero_value_returns_encoded(self):
        """When value is non-zero, return original encoded bytes."""
        encoded = [0xF1, 0xF2, 0xF3]
        result = _builtin_cobol_blank_when_zero(
            [
                typed_from_runtime(encoded),
                typed_from_runtime("123"),
                typed_from_runtime(3),
            ],
            None,
        ).value
        assert result == [0xF1, 0xF2, 0xF3]

    def test_zero_float_returns_spaces(self):
        """Float zero (0.0) triggers blank replacement."""
        encoded = [0xF0, 0xF0]
        result = _builtin_cobol_blank_when_zero(
            [
                typed_from_runtime(encoded),
                typed_from_runtime("0.0"),
                typed_from_runtime(2),
            ],
            None,
        ).value
        assert result == [0x40, 0x40]

    def test_negative_zero_returns_spaces(self):
        """Negative zero is still zero."""
        encoded = [0xF0, 0xF0]
        result = _builtin_cobol_blank_when_zero(
            [
                typed_from_runtime(encoded),
                typed_from_runtime("-0"),
                typed_from_runtime(2),
            ],
            None,
        ).value
        assert result == [0x40, 0x40]

    def test_non_numeric_string_returns_encoded(self):
        """Non-numeric value string returns encoded bytes unchanged."""
        encoded = [0xC1, 0xC2]
        result = _builtin_cobol_blank_when_zero(
            [
                typed_from_runtime(encoded),
                typed_from_runtime("AB"),
                typed_from_runtime(2),
            ],
            None,
        ).value
        assert result == [0xC1, 0xC2]

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue(name="x")
        assert (
            _builtin_cobol_blank_when_zero(
                [
                    typed_from_runtime(sym),
                    typed_from_runtime("0"),
                    typed_from_runtime(3),
                ],
                None,
            ).value
            is _UNCOMPUTABLE
        )

    def test_too_few_args_returns_uncomputable(self):
        assert (
            _builtin_cobol_blank_when_zero(
                [typed_from_runtime([0xF0]), typed_from_runtime("0")], None
            ).value
            is _UNCOMPUTABLE
        )

    def test_registered_in_builtins(self):
        assert "__cobol_blank_when_zero" in BYTE_BUILTINS
