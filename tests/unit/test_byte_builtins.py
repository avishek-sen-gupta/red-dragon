"""Tests for primitive byte-manipulation builtins."""

from interpreter.func_name import FuncName
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
    _builtin_cobol_round,
    _builtin_string_find,
    _builtin_string_split,
    _builtin_string_count,
    _builtin_string_replace,
    _builtin_string_concat,
    _builtin_string_concat_pair,
    _builtin_string_slice,
    _builtin_string_splice,
    _builtin_upper_case,
    _builtin_lower_case,
    _builtin_cobol_trim,
    _builtin_is_numeric,
    _builtin_is_alphabetic,
    _builtin_is_alphabetic_lower,
    _builtin_is_alphabetic_upper,
    _builtin_current_date,
    _builtin_length,
    _builtin_string_convert,
    _builtin_numval,
    _builtin_numval_c,
    _builtin_test_numval,
    _builtin_test_numval_c,
    _builtin_integer_of_date,
    _builtin_mod,
    _builtin_date_of_integer,
    BYTE_BUILTINS,
)
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.features import CobolFeature
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm import Operators
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers

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
        ).value == [
            0,
            0,
            0,
            0,
            0,
        ]

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
            "__cobol_round",
            "__cobol_apply_edit_picture",
            "__string_slice",
            "__string_splice",
            "__string_zfill",
            "__upper_case",
            "__lower_case",
            "__cobol_trim",
            "__current_date",
            "__is_numeric",
            "__is_alphabetic",
            "__is_alphabetic_lower",
            "__is_alphabetic_upper",
            "__length",
            "__numval",
            "__numval_c",
            "__test_numval",
            "__test_numval_c",
            "__integer_of_date",
            "__date_of_integer",
            "__mod",
            "__string_convert",
        ]
        expected_func_names = [FuncName(n) for n in expected_names]
        for name in expected_func_names:
            assert name in BYTE_BUILTINS, f"{name} not in BYTE_BUILTINS"
        assert set(expected_func_names) == set(BYTE_BUILTINS.keys()), (
            f"Mismatch: expected {set(expected_func_names) - set(BYTE_BUILTINS.keys())} missing, "
            f"unexpected {set(BYTE_BUILTINS.keys()) - set(expected_func_names)} extra"
        )

    def test_builtins_merged_into_table(self):
        from interpreter.vm.builtins import Builtins

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
        assert FuncName("__cobol_blank_when_zero") in BYTE_BUILTINS


class TestStringSlice:
    """Tests for __string_slice builtin."""

    def test_string_slice_basic(self):
        # "ABCDE", start=1 (0-indexed), length=3 → "BCD"
        result = _builtin_string_slice(
            [typed_from_runtime("ABCDE"), typed_from_runtime(1), typed_from_runtime(3)],
            None,
        )
        assert result.value == "BCD"

    def test_string_slice_clamps_to_end(self):
        # "ABCDE", start=3, length=100 → "DE" (clamped)
        result = _builtin_string_slice(
            [
                typed_from_runtime("ABCDE"),
                typed_from_runtime(3),
                typed_from_runtime(100),
            ],
            None,
        )
        assert result.value == "DE"

    def test_string_slice_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_string_slice(
            [typed_from_runtime(sym), typed_from_runtime(0), typed_from_runtime(3)],
            None,
        )
        assert result.value is _UNCOMPUTABLE


class TestStringSplice:
    """Tests for __string_splice builtin."""

    def test_string_splice_basic(self):
        # Replace middle: "ABCDEFGHIJ"[1:4] with "XYZ" → "AXYZEFGHIJ"
        result = _builtin_string_splice(
            [
                typed_from_runtime("ABCDEFGHIJ"),
                typed_from_runtime(1),
                typed_from_runtime(3),
                typed_from_runtime("XYZ"),
            ],
            None,
        )
        assert result.value == "AXYZEFGHIJ"

    def test_string_splice_replacement_shorter(self):
        # "ABCDE"[1:3] with "X" → "AX" + "DE" = "AXDE"
        result = _builtin_string_splice(
            [
                typed_from_runtime("ABCDE"),
                typed_from_runtime(1),
                typed_from_runtime(2),
                typed_from_runtime("X"),
            ],
            None,
        )
        assert result.value == "AXDE"

    def test_string_splice_replacement_longer(self):
        # "ABCDE"[1:2] with "XXXX" → "A" + "XXXX" + "CDE" = "AXXXXCDE"
        result = _builtin_string_splice(
            [
                typed_from_runtime("ABCDE"),
                typed_from_runtime(1),
                typed_from_runtime(1),
                typed_from_runtime("XXXX"),
            ],
            None,
        )
        assert result.value == "AXXXXCDE"

    def test_string_splice_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_string_splice(
            [
                typed_from_runtime("ABCDE"),
                typed_from_runtime(sym),
                typed_from_runtime(2),
                typed_from_runtime("X"),
            ],
            None,
        )
        assert result.value is _UNCOMPUTABLE


class TestUpperCase:
    def test_lowercase_to_uppercase(self):
        result = _builtin_upper_case([typed_from_runtime("abc123")], None)
        assert result.value == "ABC123"

    def test_already_uppercase_unchanged(self):
        result = _builtin_upper_case([typed_from_runtime("ABC")], None)
        assert result.value == "ABC"

    def test_mixed_case(self):
        result = _builtin_upper_case([typed_from_runtime("AbCdEf")], None)
        assert result.value == "ABCDEF"

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_upper_case([typed_from_runtime(sym)], None)
        assert result.value is _UNCOMPUTABLE

    def test_non_string_returns_uncomputable(self):
        result = _builtin_upper_case([typed_from_runtime(42)], None)
        assert result.value is _UNCOMPUTABLE

    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.UPPER_CASE) in BYTE_BUILTINS


class TestCobolTrim:
    """FUNCTION TRIM strips leading + trailing spaces (red-dragon-ge72)."""

    def test_strips_both_ends(self):
        result = _builtin_cobol_trim([typed_from_runtime(" AB ")], None)
        assert result.value == "AB"

    def test_strips_only_spaces_not_inner(self):
        result = _builtin_cobol_trim([typed_from_runtime("  A B  ")], None)
        assert result.value == "A B"

    def test_no_padding_unchanged(self):
        result = _builtin_cobol_trim([typed_from_runtime("ABC")], None)
        assert result.value == "ABC"

    def test_all_spaces_to_empty(self):
        result = _builtin_cobol_trim([typed_from_runtime("    ")], None)
        assert result.value == ""

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_cobol_trim([typed_from_runtime(sym)], None)
        assert result.value is _UNCOMPUTABLE

    def test_non_string_returns_uncomputable(self):
        result = _builtin_cobol_trim([typed_from_runtime(42)], None)
        assert result.value is _UNCOMPUTABLE

    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.TRIM) in BYTE_BUILTINS


class TestLowerCase:
    def test_uppercase_to_lowercase(self):
        result = _builtin_lower_case([typed_from_runtime("ABC123")], None)
        assert result.value == "abc123"

    def test_mixed_case(self):
        result = _builtin_lower_case([typed_from_runtime("AbCdEf")], None)
        assert result.value == "abcdef"

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_lower_case([typed_from_runtime(sym)], None)
        assert result.value is _UNCOMPUTABLE

    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.LOWER_CASE) in BYTE_BUILTINS


class TestCurrentDate:
    def test_returns_21_char_string(self):
        result = _builtin_current_date([], None)
        assert isinstance(result.value, str)
        assert len(result.value) == 21

    def test_date_time_portion_is_digits(self):
        result = _builtin_current_date([], None)
        # First 16 chars: YYYYMMDDHHMMSShh — all digits.
        assert result.value[:16].isdigit()

    def test_year_is_plausible(self):
        result = _builtin_current_date([], None)
        year = int(result.value[:4])
        assert 2020 <= year <= 2100

    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.CURRENT_DATE) in BYTE_BUILTINS


class TestIsNumeric:
    def test_all_digits_true(self):
        result = _builtin_is_numeric([typed_from_runtime("01")], None)
        assert result.value is True

    def test_letters_false(self):
        result = _builtin_is_numeric([typed_from_runtime("AB")], None)
        assert result.value is False

    def test_mixed_false(self):
        result = _builtin_is_numeric([typed_from_runtime("A1")], None)
        assert result.value is False

    def test_trailing_spaces_false(self):
        result = _builtin_is_numeric([typed_from_runtime("12 ")], None)
        assert result.value is False

    def test_empty_false(self):
        result = _builtin_is_numeric([typed_from_runtime("")], None)
        assert result.value is False

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_is_numeric([typed_from_runtime(sym)], None)
        assert result.value is _UNCOMPUTABLE

    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.IS_NUMERIC) in BYTE_BUILTINS


class TestIsAlphabetic:
    def test_all_letters_true(self):
        result = _builtin_is_alphabetic([typed_from_runtime("AB")], None)
        assert result.value is True

    def test_letters_and_spaces_true(self):
        result = _builtin_is_alphabetic([typed_from_runtime("AB CD")], None)
        assert result.value is True

    def test_digits_false(self):
        result = _builtin_is_alphabetic([typed_from_runtime("01")], None)
        assert result.value is False

    def test_mixed_false(self):
        result = _builtin_is_alphabetic([typed_from_runtime("A1")], None)
        assert result.value is False

    def test_empty_true(self):
        # An empty (all-space) string is alphabetic in COBOL.
        result = _builtin_is_alphabetic([typed_from_runtime("   ")], None)
        assert result.value is True

    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_is_alphabetic([typed_from_runtime(sym)], None)
        assert result.value is _UNCOMPUTABLE

    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.IS_ALPHABETIC) in BYTE_BUILTINS


class TestIsAlphabeticLower:
    def test_all_lower_true(self):
        result = _builtin_is_alphabetic_lower([typed_from_runtime("ab cd")], None)
        assert result.value is True

    def test_upper_false(self):
        result = _builtin_is_alphabetic_lower([typed_from_runtime("AB")], None)
        assert result.value is False

    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.IS_ALPHABETIC_LOWER) in BYTE_BUILTINS


class TestIsAlphabeticUpper:
    def test_all_upper_true(self):
        result = _builtin_is_alphabetic_upper([typed_from_runtime("AB CD")], None)
        assert result.value is True

    def test_lower_false(self):
        result = _builtin_is_alphabetic_upper([typed_from_runtime("ab")], None)
        assert result.value is False

    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.IS_ALPHABETIC_UPPER) in BYTE_BUILTINS


class TestLength:
    """FUNCTION LENGTH(x) -> byte length of the argument (red-dragon-zuhj)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_string_length(self):
        result = _builtin_length([typed_from_runtime("ABC")], None)
        assert result.value == 3

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_pic_x10_field_length(self):
        # A PIC X(10) field arrives as a 10-char (space-padded) string.
        result = _builtin_length([typed_from_runtime("ABC       ")], None)
        assert result.value == 10

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_empty_string(self):
        result = _builtin_length([typed_from_runtime("")], None)
        assert result.value == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_length([typed_from_runtime(sym)], None)
        assert result.value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.LENGTH) in BYTE_BUILTINS


class TestStringConvert:
    """INSPECT ... CONVERTING from TO to: positional per-character translate."""

    @covers(CobolFeature.INSPECT_CONVERTING)
    def test_alpha_to_spaces(self):
        # Convert every uppercase letter to a space (CardDemo's alpha-only edit).
        upper = "".join(chr(c) for c in range(ord("A"), ord("Z") + 1))
        result = _builtin_string_convert(
            [
                typed_from_runtime("JOHN"),
                typed_from_runtime(upper),
                typed_from_runtime(" " * 26),
            ],
            None,
        )
        assert result.value == "    "

    @covers(CobolFeature.INSPECT_CONVERTING)
    def test_positional_mapping(self):
        # 'abc' -> 'xyz' positionally; unmatched chars untouched.
        result = _builtin_string_convert(
            [
                typed_from_runtime("cab1"),
                typed_from_runtime("abc"),
                typed_from_runtime("xyz"),
            ],
            None,
        )
        assert result.value == "zxy1"

    @covers(CobolFeature.INSPECT_CONVERTING)
    def test_last_mapping_wins_on_duplicate_from(self):
        # COBOL maps each FROM char to the same-position TO char; for a duplicate
        # FROM char the first occurrence's mapping applies.
        result = _builtin_string_convert(
            [
                typed_from_runtime("aa"),
                typed_from_runtime("aa"),
                typed_from_runtime("xy"),
            ],
            None,
        )
        assert result.value == "xx"

    @covers(CobolFeature.INSPECT_CONVERTING)
    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_string_convert(
            [typed_from_runtime(sym), typed_from_runtime("a"), typed_from_runtime("b")],
            None,
        )
        assert result.value is _UNCOMPUTABLE

    @covers(CobolFeature.INSPECT_CONVERTING)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.STRING_CONVERT) in BYTE_BUILTINS


class TestNumval:
    """FUNCTION NUMVAL(s) -> numeric value of a numeric string (red-dragon-zuhj)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_spaced_decimal(self):
        result = _builtin_numval([typed_from_runtime(" 1234.56 ")], None)
        assert float(result.value) == 1234.56

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_leading_minus(self):
        result = _builtin_numval([typed_from_runtime("-12")], None)
        assert result.value == -12

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_leading_plus(self):
        result = _builtin_numval([typed_from_runtime("+12")], None)
        assert result.value == 12

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_trailing_sign(self):
        result = _builtin_numval([typed_from_runtime("12-")], None)
        assert result.value == -12

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_trailing_cr(self):
        result = _builtin_numval([typed_from_runtime("100CR")], None)
        assert result.value == -100

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_trailing_db(self):
        result = _builtin_numval([typed_from_runtime("100DB")], None)
        assert result.value == -100

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_plain_integer_is_int(self):
        result = _builtin_numval([typed_from_runtime("42")], None)
        assert result.value == 42

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_all_blank_is_zero(self):
        result = _builtin_numval([typed_from_runtime("   ")], None)
        assert result.value == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_numval([typed_from_runtime(sym)], None)
        assert result.value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.NUMVAL) in BYTE_BUILTINS


class TestNumvalC:
    """FUNCTION NUMVAL-C(s) -> currency/grouping-aware numeric (red-dragon-zuhj)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_currency_and_grouping(self):
        result = _builtin_numval_c([typed_from_runtime("$1,234.56")], None)
        assert float(result.value) == 1234.56

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_grouping_only(self):
        result = _builtin_numval_c([typed_from_runtime("1,000")], None)
        assert result.value == 1000

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_negative_with_currency(self):
        result = _builtin_numval_c([typed_from_runtime("-$50.00")], None)
        assert float(result.value) == -50.0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_plain_number(self):
        result = _builtin_numval_c([typed_from_runtime("99")], None)
        assert result.value == 99

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_numval_c([typed_from_runtime(sym)], None)
        assert result.value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.NUMVAL_C) in BYTE_BUILTINS


class TestTestNumval:
    """FUNCTION TEST-NUMVAL(s) -> 0 if valid else 1-based bad-char pos."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_valid_digits(self):
        result = _builtin_test_numval([typed_from_runtime("1234")], None)
        assert result.value == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_valid_signed_decimal(self):
        result = _builtin_test_numval([typed_from_runtime(" -12.50 ")], None)
        assert result.value == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_bad_char_position(self):
        result = _builtin_test_numval([typed_from_runtime("12A4")], None)
        assert result.value == 3

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_all_blank_valid(self):
        result = _builtin_test_numval([typed_from_runtime("   ")], None)
        assert result.value == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_test_numval([typed_from_runtime(sym)], None)
        assert result.value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.TEST_NUMVAL) in BYTE_BUILTINS


class TestTestNumvalC:
    """FUNCTION TEST-NUMVAL-C(s) -> 0 if valid NUMVAL-C arg else bad-char pos."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_valid_currency_grouping(self):
        result = _builtin_test_numval_c([typed_from_runtime("$1,234")], None)
        assert result.value == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_valid_plain(self):
        result = _builtin_test_numval_c([typed_from_runtime("1234")], None)
        assert result.value == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_bad_char(self):
        result = _builtin_test_numval_c([typed_from_runtime("12X4")], None)
        assert result.value == 3

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_test_numval_c([typed_from_runtime(sym)], None)
        assert result.value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.TEST_NUMVAL_C) in BYTE_BUILTINS


class TestIntegerOfDate:
    """FUNCTION INTEGER-OF-DATE(yyyymmdd) -> days since 1600-12-31."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_known_reference(self):
        # 2024-01-01 is 154498 days after the 1600-12-31 COBOL epoch.
        result = _builtin_integer_of_date([typed_from_runtime(20240101)], None)
        assert result.value == 154498

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_epoch_plus_one(self):
        # 1601-01-01 is day 1.
        result = _builtin_integer_of_date([typed_from_runtime(16010101)], None)
        assert result.value == 1

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_string_arg(self):
        result = _builtin_integer_of_date([typed_from_runtime("20240101")], None)
        assert result.value == 154498

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_returns_uncomputable(self):
        sym = SymbolicValue("s0")
        result = _builtin_integer_of_date([typed_from_runtime(sym)], None)
        assert result.value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.INTEGER_OF_DATE) in BYTE_BUILTINS


class TestMod:
    """FUNCTION MOD(x, y) -> floored modulo; result carries the sign of y."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert (
            _builtin_mod([typed_from_runtime(17), typed_from_runtime(5)], None).value
            == 2
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_negative_dividend_floored(self):
        # COBOL MOD = x - y * FUNCTION INTEGER(x / y); MOD(-7, 3) = 2.
        assert (
            _builtin_mod([typed_from_runtime(-7), typed_from_runtime(3)], None).value
            == 2
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_negative_divisor(self):
        assert (
            _builtin_mod([typed_from_runtime(7), typed_from_runtime(-3)], None).value
            == -2
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_string_args(self):
        assert (
            _builtin_mod(
                [typed_from_runtime("17"), typed_from_runtime("5")], None
            ).value
            == 2
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_divisor_zero_uncomputable(self):
        assert (
            _builtin_mod([typed_from_runtime(5), typed_from_runtime(0)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_mod([typed_from_runtime(sym), typed_from_runtime(5)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.MOD) in BYTE_BUILTINS


class TestDateOfInteger:
    """FUNCTION DATE-OF-INTEGER(n) -> CCYYMMDD; inverse of INTEGER-OF-DATE."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_known_reference(self):
        # Day 154498 after the 1600-12-31 COBOL epoch is 2024-01-01.
        assert (
            _builtin_date_of_integer([typed_from_runtime(154498)], None).value
            == 20240101
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_epoch_plus_one(self):
        assert _builtin_date_of_integer([typed_from_runtime(1)], None).value == 16010101

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_round_trip_with_integer_of_date(self):
        n = _builtin_integer_of_date([typed_from_runtime(20240101)], None).value
        assert _builtin_date_of_integer([typed_from_runtime(n)], None).value == 20240101

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_string_arg(self):
        assert (
            _builtin_date_of_integer([typed_from_runtime("154498")], None).value
            == 20240101
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_date_of_integer([typed_from_runtime(sym)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.DATE_OF_INTEGER) in BYTE_BUILTINS


class TestCobolRound:
    """COBOL ROUNDED clause — half-away-from-zero rounding."""

    @covers(CobolFeature.ROUNDED_CLAUSE)
    def test_rounds_up_at_halfway(self):
        result = _builtin_cobol_round(
            [typed_from_runtime("1.235"), typed_from_runtime(2)], None
        )
        assert result.value == "1.24"

    @covers(CobolFeature.ROUNDED_CLAUSE)
    def test_rounds_down_below_halfway(self):
        result = _builtin_cobol_round(
            [typed_from_runtime("1.234"), typed_from_runtime(2)], None
        )
        assert result.value == "1.23"

    @covers(CobolFeature.ROUNDED_CLAUSE)
    def test_rounds_away_from_zero_for_negatives(self):
        result = _builtin_cobol_round(
            [typed_from_runtime("-1.235"), typed_from_runtime(2)], None
        )
        assert result.value == "-1.24"

    @covers(CobolFeature.ROUNDED_CLAUSE)
    def test_zero_decimal_digits_rounds_to_integer(self):
        result = _builtin_cobol_round(
            [typed_from_runtime("2.7"), typed_from_runtime(0)], None
        )
        assert result.value == "3"

    @covers(CobolFeature.ROUNDED_CLAUSE)
    def test_zero_decimal_digits_rounds_down(self):
        result = _builtin_cobol_round(
            [typed_from_runtime("2.3"), typed_from_runtime(0)], None
        )
        assert result.value == "2"

    @covers(CobolFeature.ROUNDED_CLAUSE)
    def test_symbolic_returns_uncomputable(self):
        sym = typed_from_runtime(Operators.UNCOMPUTABLE)
        result = _builtin_cobol_round([sym, typed_from_runtime(2)], None)
        assert result.value == _UNCOMPUTABLE
