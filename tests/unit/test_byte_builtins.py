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
        ]
        for name in expected_names:
            assert name in BYTE_BUILTINS, f"{name} not in BYTE_BUILTINS"

    def test_builtins_merged_into_table(self):
        from interpreter.builtins import Builtins

        for name in BYTE_BUILTINS:
            assert name in Builtins.TABLE, f"{name} not in Builtins.TABLE"
