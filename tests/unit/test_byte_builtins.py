"""Tests for primitive byte-manipulation builtins."""

import math
from decimal import Decimal

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
    _builtin_reverse,
    _builtin_max,
    _builtin_min,
    _builtin_sum,
    _builtin_random,
    _builtin_abs,
    _builtin_sqrt,
    _builtin_sin,
    _builtin_cos,
    _builtin_tan,
    _builtin_asin,
    _builtin_acos,
    _builtin_atan,
    _builtin_range,
    _builtin_mean,
    _builtin_median,
    _builtin_midrange,
    _builtin_variance,
    _builtin_ord_max,
    _builtin_ord_min,
    _builtin_concatenate,
    _builtin_exp,
    _builtin_log,
    _builtin_factorial,
    _builtin_integer,
    _builtin_integer_part,
    _builtin_fraction_part,
    _builtin_rem,
    _builtin_substitute,
    _builtin_exp10,
    _builtin_log10,
    _builtin_char,
    _builtin_ord,
    _builtin_day_of_integer,
    _builtin_integer_of_day,
    _builtin_annuity,
    _builtin_present_value,
    _builtin_date_to_yyyymmdd,
    _builtin_day_to_yyyyddd,
    _builtin_year_to_yyyy,
    BYTE_BUILTINS,
)
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.features import CobolFeature
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm import Operators
from interpreter.vm.vm_types import SymbolicValue, VMState
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
            "__multi_delimiter_split",
            "__multi_delimiter_consumed_length",
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
            "__string_boundary_slice",
            "__string_boundary_split",
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
            "__reverse",
            "__max",
            "__min",
            "__sum",
            "__random",
            "__abs",
            "__sqrt",
            "__sin",
            "__cos",
            "__tan",
            "__asin",
            "__acos",
            "__atan",
            "__range",
            "__mean",
            "__median",
            "__midrange",
            "__variance",
            "__ord_max",
            "__ord_min",
            "__concatenate",
            "__exp",
            "__log",
            "__factorial",
            "__integer",
            "__integer_part",
            "__fraction_part",
            "__rem",
            "__substitute",
            "__exp10",
            "__log10",
            "__char",
            "__ord_char",
            "__day_of_integer",
            "__integer_of_day",
            "__annuity",
            "__present_value",
            "__date_to_yyyymmdd",
            "__day_to_yyyyddd",
            "__year_to_yyyy",
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


class TestReverse:
    """FUNCTION REVERSE(s) -> s with characters in reverse order."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert _builtin_reverse([typed_from_runtime("ABCDE")], None).value == "EDCBA"

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_empty_string(self):
        assert _builtin_reverse([typed_from_runtime("")], None).value == ""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_non_string_uncomputable(self):
        assert _builtin_reverse([typed_from_runtime(5)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_reverse([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.REVERSE) in BYTE_BUILTINS


class TestMax:
    """FUNCTION MAX(a, b, ...) -> the largest argument."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert (
            _builtin_max(
                [
                    typed_from_runtime(3),
                    typed_from_runtime(7),
                    typed_from_runtime(5),
                ],
                None,
            ).value
            == 7
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_string_args(self):
        assert (
            _builtin_max([typed_from_runtime("3"), typed_from_runtime("7")], None).value
            == 7
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_decimal_args(self):
        assert _builtin_max(
            [typed_from_runtime("2.5"), typed_from_runtime("2.75")], None
        ).value == Decimal("2.75")

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_no_args_uncomputable(self):
        assert _builtin_max([], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_max([typed_from_runtime(sym), typed_from_runtime(5)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.MAX) in BYTE_BUILTINS


class TestMin:
    """FUNCTION MIN(a, b, ...) -> the smallest argument."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert (
            _builtin_min(
                [
                    typed_from_runtime(8),
                    typed_from_runtime(3),
                    typed_from_runtime(5),
                ],
                None,
            ).value
            == 3
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_string_args(self):
        assert (
            _builtin_min([typed_from_runtime("3"), typed_from_runtime("7")], None).value
            == 3
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_decimal_args(self):
        assert _builtin_min(
            [typed_from_runtime("2.5"), typed_from_runtime("2.75")], None
        ).value == Decimal("2.5")

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_no_args_uncomputable(self):
        assert _builtin_min([], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_min([typed_from_runtime(sym), typed_from_runtime(5)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.MIN) in BYTE_BUILTINS


class TestSum:
    """FUNCTION SUM(a, b, ...) -> the sum of all arguments."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert (
            _builtin_sum(
                [
                    typed_from_runtime(3),
                    typed_from_runtime(7),
                    typed_from_runtime(5),
                ],
                None,
            ).value
            == 15
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_no_args_is_zero(self):
        assert _builtin_sum([], None).value == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_decimal_args(self):
        assert _builtin_sum(
            [typed_from_runtime("2.5"), typed_from_runtime("2.75")], None
        ).value == Decimal("5.25")

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_sum([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.SUM) in BYTE_BUILTINS


class TestRandom:
    """FUNCTION RANDOM([seed]) -> next value in [0,1) from a VM-scoped sequence.

    Python's random module is an accepted deviation from ISO COBOL's
    implementation-defined generator (red-dragon-clpn): only reproducibility
    for a fixed seed and the [0,1) range are contractually required.
    """

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_no_seed_in_unit_range(self):
        vm = VMState()
        result = _builtin_random([], vm).value
        assert 0 <= result < 1

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_positive_seed_is_reproducible(self):
        first = _builtin_random([typed_from_runtime(42)], VMState()).value
        second = _builtin_random([typed_from_runtime(42)], VMState()).value
        assert first == second

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_successive_unseeded_calls_differ(self):
        vm = VMState()
        first = _builtin_random([], vm).value
        second = _builtin_random([], vm).value
        assert first != second

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_negative_seed_replays_last_positive_seed(self):
        vm = VMState()
        first = _builtin_random([typed_from_runtime(7)], vm).value
        _builtin_random([], vm)  # advance the sequence
        replayed = _builtin_random([typed_from_runtime(-1)], vm).value
        assert replayed == first

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_seed_uncomputable(self):
        vm = VMState()
        sym = SymbolicValue("s0")
        assert _builtin_random([typed_from_runtime(sym)], vm).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.RANDOM) in BYTE_BUILTINS


class TestAbs:
    """FUNCTION ABS(x) -> the absolute value of x."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert _builtin_abs([typed_from_runtime(-5)], None).value == 5

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_decimal_arg(self):
        assert _builtin_abs([typed_from_runtime("-2.5")], None).value == Decimal("2.5")

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_abs([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.ABS) in BYTE_BUILTINS


class TestSqrt:
    """FUNCTION SQRT(x) -> the (non-negative) square root of x."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_perfect_square(self):
        assert _builtin_sqrt([typed_from_runtime(4)], None).value == 2

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_non_perfect_square(self):
        result = _builtin_sqrt([typed_from_runtime(2)], None).value
        assert math.isclose(float(result), 1.4142135623730951, rel_tol=1e-9)

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_negative_uncomputable(self):
        assert _builtin_sqrt([typed_from_runtime(-4)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_sqrt([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.SQRT) in BYTE_BUILTINS


class TestSin:
    """FUNCTION SIN(x) -> the sine of x (radians)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert _builtin_sin([typed_from_runtime(0)], None).value == 0.0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_sin([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.SIN) in BYTE_BUILTINS


class TestCos:
    """FUNCTION COS(x) -> the cosine of x (radians)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert _builtin_cos([typed_from_runtime(0)], None).value == 1.0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_cos([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.COS) in BYTE_BUILTINS


class TestTan:
    """FUNCTION TAN(x) -> the tangent of x (radians)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert _builtin_tan([typed_from_runtime(0)], None).value == 0.0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_tan([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.TAN) in BYTE_BUILTINS


class TestAsin:
    """FUNCTION ASIN(x) -> the arcsine of x, x in [-1,1] (radians)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        result = _builtin_asin([typed_from_runtime(1)], None).value
        assert math.isclose(result, math.pi / 2, rel_tol=1e-9)

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_out_of_domain_uncomputable(self):
        assert _builtin_asin([typed_from_runtime(2)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_asin([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.ASIN) in BYTE_BUILTINS


class TestAcos:
    """FUNCTION ACOS(x) -> the arccosine of x, x in [-1,1] (radians)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert _builtin_acos([typed_from_runtime(1)], None).value == 0.0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_out_of_domain_uncomputable(self):
        assert _builtin_acos([typed_from_runtime(-2)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_acos([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.ACOS) in BYTE_BUILTINS


class TestAtan:
    """FUNCTION ATAN(x) -> the arctangent of x (radians)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        result = _builtin_atan([typed_from_runtime(1)], None).value
        assert math.isclose(result, math.pi / 4, rel_tol=1e-9)

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_atan([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.ATAN) in BYTE_BUILTINS


class TestRange:
    """FUNCTION RANGE(a, b, ...) -> max(args) - min(args)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert (
            _builtin_range(
                [
                    typed_from_runtime(3),
                    typed_from_runtime(7),
                    typed_from_runtime(5),
                ],
                None,
            ).value
            == 4
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_no_args_uncomputable(self):
        assert _builtin_range([], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_range([typed_from_runtime(sym), typed_from_runtime(5)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.RANGE) in BYTE_BUILTINS


class TestMean:
    """FUNCTION MEAN(a, b, ...) -> the arithmetic mean of the arguments."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert (
            _builtin_mean(
                [
                    typed_from_runtime(2),
                    typed_from_runtime(4),
                    typed_from_runtime(6),
                ],
                None,
            ).value
            == 4
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_no_args_uncomputable(self):
        assert _builtin_mean([], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.MEAN) in BYTE_BUILTINS


class TestMedian:
    """FUNCTION MEDIAN(a, b, ...) -> the middle value; the average of the two
    middle values for an even number of arguments."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_odd_count(self):
        assert (
            _builtin_median(
                [
                    typed_from_runtime(3),
                    typed_from_runtime(7),
                    typed_from_runtime(5),
                ],
                None,
            ).value
            == 5
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_even_count_averages_middle_two(self):
        assert _builtin_median(
            [
                typed_from_runtime(1),
                typed_from_runtime(2),
                typed_from_runtime(3),
                typed_from_runtime(4),
            ],
            None,
        ).value == Decimal("2.5")

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_no_args_uncomputable(self):
        assert _builtin_median([], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.MEDIAN) in BYTE_BUILTINS


class TestMidrange:
    """FUNCTION MIDRANGE(a, b, ...) -> (max(args) + min(args)) / 2."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert (
            _builtin_midrange(
                [typed_from_runtime(2), typed_from_runtime(8)], None
            ).value
            == 5
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_no_args_uncomputable(self):
        assert _builtin_midrange([], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.MIDRANGE) in BYTE_BUILTINS


class TestVariance:
    """FUNCTION VARIANCE(a, b, ...) -> sample variance (n-1 divisor); 0 for a
    single argument."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_single_arg_is_zero(self):
        assert _builtin_variance([typed_from_runtime(5)], None).value == 0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert (
            _builtin_variance(
                [
                    typed_from_runtime(2),
                    typed_from_runtime(4),
                    typed_from_runtime(6),
                ],
                None,
            ).value
            == 4
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_no_args_uncomputable(self):
        assert _builtin_variance([], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.VARIANCE) in BYTE_BUILTINS


class TestOrdMax:
    """FUNCTION ORD-MAX(a, b, ...) -> 1-based position of the first
    occurrence of the largest argument."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert (
            _builtin_ord_max(
                [
                    typed_from_runtime(3),
                    typed_from_runtime(7),
                    typed_from_runtime(5),
                ],
                None,
            ).value
            == 2
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_tie_returns_first_occurrence(self):
        assert (
            _builtin_ord_max(
                [
                    typed_from_runtime(7),
                    typed_from_runtime(3),
                    typed_from_runtime(7),
                ],
                None,
            ).value
            == 1
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_no_args_uncomputable(self):
        assert _builtin_ord_max([], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.ORD_MAX) in BYTE_BUILTINS


class TestOrdMin:
    """FUNCTION ORD-MIN(a, b, ...) -> 1-based position of the first
    occurrence of the smallest argument."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert (
            _builtin_ord_min(
                [
                    typed_from_runtime(3),
                    typed_from_runtime(7),
                    typed_from_runtime(5),
                ],
                None,
            ).value
            == 1
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_no_args_uncomputable(self):
        assert _builtin_ord_min([], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.ORD_MIN) in BYTE_BUILTINS


class TestConcatenate:
    """FUNCTION CONCATENATE(a, b, ...) -> all string arguments joined in order."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert (
            _builtin_concatenate(
                [
                    typed_from_runtime("AB"),
                    typed_from_runtime("CD"),
                    typed_from_runtime("EF"),
                ],
                None,
            ).value
            == "ABCDEF"
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_non_string_uncomputable(self):
        assert (
            _builtin_concatenate(
                [typed_from_runtime("AB"), typed_from_runtime(5)], None
            ).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_concatenate([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.CONCATENATE) in BYTE_BUILTINS


class TestExp:
    """FUNCTION EXP(x) -> e^x."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert _builtin_exp([typed_from_runtime(0)], None).value == 1.0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_one(self):
        result = _builtin_exp([typed_from_runtime(1)], None).value
        assert math.isclose(result, math.e, rel_tol=1e-9)

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_exp([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.EXP) in BYTE_BUILTINS


class TestLog:
    """FUNCTION LOG(x) -> the natural logarithm of x; x must be > 0."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert _builtin_log([typed_from_runtime(1)], None).value == 0.0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_e(self):
        result = _builtin_log([typed_from_runtime(math.e)], None).value
        assert math.isclose(result, 1.0, rel_tol=1e-9)

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_zero_uncomputable(self):
        assert _builtin_log([typed_from_runtime(0)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_negative_uncomputable(self):
        assert _builtin_log([typed_from_runtime(-1)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_log([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.LOG) in BYTE_BUILTINS


class TestFactorial:
    """FUNCTION FACTORIAL(n) -> n! for a non-negative integer n."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert _builtin_factorial([typed_from_runtime(5)], None).value == 120

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_zero(self):
        assert _builtin_factorial([typed_from_runtime(0)], None).value == 1

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_negative_uncomputable(self):
        assert _builtin_factorial([typed_from_runtime(-1)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_non_integer_uncomputable(self):
        assert (
            _builtin_factorial([typed_from_runtime("2.5")], None).value is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_factorial([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.FACTORIAL) in BYTE_BUILTINS


class TestInteger:
    """FUNCTION INTEGER(x) -> the greatest integer not greater than x (floor)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_positive(self):
        assert _builtin_integer([typed_from_runtime("3.7")], None).value == 3

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_negative_floors_down(self):
        assert _builtin_integer([typed_from_runtime("-3.2")], None).value == -4

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_integer([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.INTEGER) in BYTE_BUILTINS


class TestIntegerPart:
    """FUNCTION INTEGER-PART(x) -> x truncated toward zero."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_positive(self):
        assert _builtin_integer_part([typed_from_runtime("3.7")], None).value == 3

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_negative_truncates_toward_zero(self):
        assert _builtin_integer_part([typed_from_runtime("-3.2")], None).value == -3

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_integer_part([typed_from_runtime(sym)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.INTEGER_PART) in BYTE_BUILTINS


class TestFractionPart:
    """FUNCTION FRACTION-PART(x) -> x - INTEGER-PART(x)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_positive(self):
        assert _builtin_fraction_part(
            [typed_from_runtime("3.7")], None
        ).value == Decimal("0.7")

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_negative(self):
        assert _builtin_fraction_part(
            [typed_from_runtime("-3.7")], None
        ).value == Decimal("-0.7")

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_fraction_part([typed_from_runtime(sym)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.FRACTION_PART) in BYTE_BUILTINS


class TestRem:
    """FUNCTION REM(x, y) -> x - y * FUNCTION INTEGER-PART(x / y); result sign
    follows the dividend x (unlike MOD, which follows the divisor y)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert (
            _builtin_rem([typed_from_runtime(7), typed_from_runtime(3)], None).value
            == 1
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_negative_dividend_differs_from_mod(self):
        # trunc(-7/3) = -2; REM = -7 - 3*(-2) = -1 (MOD(-7,3) is 2 — floored).
        assert (
            _builtin_rem([typed_from_runtime(-7), typed_from_runtime(3)], None).value
            == -1
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_negative_divisor_differs_from_mod(self):
        # trunc(7/-3) = -2; REM = 7 - (-3)*(-2) = 1 (MOD(7,-3) is -2 — floored).
        assert (
            _builtin_rem([typed_from_runtime(7), typed_from_runtime(-3)], None).value
            == 1
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_divisor_zero_uncomputable(self):
        assert (
            _builtin_rem([typed_from_runtime(5), typed_from_runtime(0)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_rem([typed_from_runtime(sym), typed_from_runtime(3)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.REM) in BYTE_BUILTINS


class TestSubstitute:
    """FUNCTION SUBSTITUTE(source, search-1, replace-1 [, search-2, replace-2]...):
    every occurrence of each search string replaced by its paired replacement,
    applied in order over the running result."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic_all_occurrences(self):
        assert (
            _builtin_substitute(
                [
                    typed_from_runtime("ABCABC"),
                    typed_from_runtime("A"),
                    typed_from_runtime("X"),
                ],
                None,
            ).value
            == "XBCXBC"
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_multiple_pairs_applied_in_order(self):
        assert (
            _builtin_substitute(
                [
                    typed_from_runtime("ABCD"),
                    typed_from_runtime("A"),
                    typed_from_runtime("X"),
                    typed_from_runtime("C"),
                    typed_from_runtime("Y"),
                ],
                None,
            ).value
            == "XBYD"
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_unpaired_args_uncomputable(self):
        assert (
            _builtin_substitute(
                [typed_from_runtime("AB"), typed_from_runtime("A")], None
            ).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_substitute(
                [
                    typed_from_runtime(sym),
                    typed_from_runtime("A"),
                    typed_from_runtime("X"),
                ],
                None,
            ).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.SUBSTITUTE) in BYTE_BUILTINS


class TestExp10:
    """FUNCTION EXP10(x) -> 10^x."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert _builtin_exp10([typed_from_runtime(2)], None).value == 100.0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_zero(self):
        assert _builtin_exp10([typed_from_runtime(0)], None).value == 1.0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_exp10([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.EXP10) in BYTE_BUILTINS


class TestLog10:
    """FUNCTION LOG10(x) -> the base-10 logarithm of x; x must be > 0."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_basic(self):
        assert _builtin_log10([typed_from_runtime(100)], None).value == 2.0

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_zero_uncomputable(self):
        assert _builtin_log10([typed_from_runtime(0)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_negative_uncomputable(self):
        assert _builtin_log10([typed_from_runtime(-1)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_log10([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.LOG10) in BYTE_BUILTINS


class TestChar:
    """FUNCTION CHAR(n) -> the nth character (1-based) in the program
    collating sequence (this codebase's EBCDIC table)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_letter_a(self):
        # EBCDIC byte 0xC1 (193 decimal) is 'A' -> n = 193 + 1 = 194.
        assert _builtin_char([typed_from_runtime(194)], None).value == "A"

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_digit_zero(self):
        # EBCDIC byte 0xF0 (240 decimal) is '0' -> n = 240 + 1 = 241.
        assert _builtin_char([typed_from_runtime(241)], None).value == "0"

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_out_of_range_uncomputable(self):
        assert _builtin_char([typed_from_runtime(0)], None).value is _UNCOMPUTABLE
        assert _builtin_char([typed_from_runtime(257)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_char([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.CHAR) in BYTE_BUILTINS


class TestOrd:
    """FUNCTION ORD(c) -> the 1-based ordinal position of c in the program
    collating sequence; ORD(CHAR(n)) == n for printable characters."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_letter_a(self):
        assert _builtin_ord([typed_from_runtime("A")], None).value == 194

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_digit_zero(self):
        assert _builtin_ord([typed_from_runtime("0")], None).value == 241

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_round_trips_with_char(self):
        n = 194
        char_result = _builtin_char([typed_from_runtime(n)], None).value
        assert _builtin_ord([typed_from_runtime(char_result)], None).value == n

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_multi_char_uncomputable(self):
        assert _builtin_ord([typed_from_runtime("AB")], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert _builtin_ord([typed_from_runtime(sym)], None).value is _UNCOMPUTABLE

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.ORD) in BYTE_BUILTINS


class TestDayOfInteger:
    """FUNCTION DAY-OF-INTEGER(n) -> the Julian date YYYYDDD, n days after the
    COBOL standard epoch (1600-12-31)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_known_reference(self):
        # day 154498 after the epoch is 2024-01-01 (day 1 of 2024).
        assert _builtin_day_of_integer([typed_from_runtime(154498)], None).value == (
            2024001
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_day_of_integer([typed_from_runtime(sym)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.DAY_OF_INTEGER) in BYTE_BUILTINS


class TestIntegerOfDay:
    """FUNCTION INTEGER-OF-DAY(yyyyddd) -> integer day count since the COBOL
    standard epoch (1600-12-31); inverse of DAY-OF-INTEGER."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_known_reference(self):
        assert (
            _builtin_integer_of_day([typed_from_runtime(2024001)], None).value == 154498
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_invalid_day_of_year_uncomputable(self):
        # 2023 is not a leap year, so day 366 doesn't exist.
        assert (
            _builtin_integer_of_day([typed_from_runtime(2023366)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_integer_of_day([typed_from_runtime(sym)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.INTEGER_OF_DAY) in BYTE_BUILTINS


class TestAnnuity:
    """FUNCTION ANNUITY(rate, periods) -> the amortizing payment factor for a
    loan of 1 unit repaid over `periods` periods at interest `rate`."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_zero_rate(self):
        assert _builtin_annuity(
            [typed_from_runtime(0), typed_from_runtime(4)], None
        ).value == Decimal("0.25")

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_nonzero_rate(self):
        result = _builtin_annuity(
            [typed_from_runtime("0.05"), typed_from_runtime(10)], None
        ).value
        assert math.isclose(float(result), 0.129504575, rel_tol=1e-6)

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_non_positive_periods_uncomputable(self):
        assert (
            _builtin_annuity(
                [typed_from_runtime("0.05"), typed_from_runtime(0)], None
            ).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_annuity(
                [typed_from_runtime(sym), typed_from_runtime(4)], None
            ).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.ANNUITY) in BYTE_BUILTINS


class TestPresentValue:
    """FUNCTION PRESENT-VALUE(rate, cashflow-1, ...) -> sum of cashflow-i
    discounted at `rate` for i periods."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_zero_rate_sums_cashflows(self):
        assert _builtin_present_value(
            [
                typed_from_runtime(0),
                typed_from_runtime(100),
                typed_from_runtime(100),
            ],
            None,
        ).value == Decimal("200")

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_nonzero_rate(self):
        result = _builtin_present_value(
            [typed_from_runtime("0.10"), typed_from_runtime(110)], None
        ).value
        assert math.isclose(float(result), 100.0, rel_tol=1e-9)

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_no_cashflows_uncomputable(self):
        assert (
            _builtin_present_value([typed_from_runtime(0)], None).value is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_present_value(
                [typed_from_runtime(sym), typed_from_runtime(100)], None
            ).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.PRESENT_VALUE) in BYTE_BUILTINS


class TestDateToYyyymmdd:
    """FUNCTION DATE-TO-YYYYMMDD(yymmdd [, cutoff]) -> yymmdd expanded to an
    8-digit YYYYMMDD; default cutoff is 50 (yy >= 50 -> 19yy, else 20yy),
    matching the common production COBOL default (IBM/GnuCOBOL)."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_below_default_cutoff(self):
        assert (
            _builtin_date_to_yyyymmdd([typed_from_runtime(240101)], None).value
            == 20240101
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_at_or_above_default_cutoff(self):
        assert (
            _builtin_date_to_yyyymmdd([typed_from_runtime(990101)], None).value
            == 19990101
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_explicit_cutoff_override(self):
        assert (
            _builtin_date_to_yyyymmdd(
                [typed_from_runtime(750101), typed_from_runtime(80)], None
            ).value
            == 20750101
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_date_to_yyyymmdd([typed_from_runtime(sym)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.DATE_TO_YYYYMMDD) in BYTE_BUILTINS


class TestDayToYyyyddd:
    """FUNCTION DAY-TO-YYYYDDD(yyddd [, cutoff]) -> yyddd expanded to a
    7-digit YYYYDDD; same default-50 windowing as DATE-TO-YYYYMMDD."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_below_default_cutoff(self):
        assert (
            _builtin_day_to_yyyyddd([typed_from_runtime(24001)], None).value == 2024001
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_at_or_above_default_cutoff(self):
        assert (
            _builtin_day_to_yyyyddd([typed_from_runtime(99001)], None).value == 1999001
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_day_to_yyyyddd([typed_from_runtime(sym)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.DAY_TO_YYYYDDD) in BYTE_BUILTINS


class TestYearToYyyy:
    """FUNCTION YEAR-TO-YYYY(yy [, cutoff]) -> yy expanded to a 4-digit year;
    same default-50 windowing as DATE-TO-YYYYMMDD."""

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_below_default_cutoff(self):
        assert _builtin_year_to_yyyy([typed_from_runtime(24)], None).value == 2024

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_at_or_above_default_cutoff(self):
        assert _builtin_year_to_yyyy([typed_from_runtime(99)], None).value == 1999

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_explicit_cutoff_override(self):
        assert (
            _builtin_year_to_yyyy(
                [typed_from_runtime(75), typed_from_runtime(80)], None
            ).value
            == 2075
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_symbolic_uncomputable(self):
        sym = SymbolicValue("s0")
        assert (
            _builtin_year_to_yyyy([typed_from_runtime(sym)], None).value
            is _UNCOMPUTABLE
        )

    @covers(CobolFeature.INTRINSIC_FUNCTION)
    def test_registered_in_builtins(self):
        assert FuncName(BuiltinName.YEAR_TO_YYYY) in BYTE_BUILTINS
