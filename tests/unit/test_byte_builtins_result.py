"""Unit tests verifying BYTE_BUILTINS return BuiltinResult."""

from interpreter.cobol.byte_builtins import (
    _builtin_nibble_get,
    _builtin_byte_from_int,
    _builtin_bytes_to_string,
    _builtin_list_get,
    _builtin_list_set,
    _builtin_make_list,
    _builtin_string_find,
    _builtin_cobol_prepare_digits,
    _builtin_int_to_binary_bytes,
    _builtin_cobol_blank_when_zero,
)
from interpreter.vm import Operators
from interpreter.vm_types import BuiltinResult


class TestByteBuiltinsReturnBuiltinResult:
    def test_nibble_get_returns_builtin_result(self):
        result = _builtin_nibble_get([0xAB, "high"], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == 0xA
        assert result.new_objects == []

    def test_byte_from_int_returns_builtin_result(self):
        result = _builtin_byte_from_int([256], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == 0

    def test_bytes_to_string_returns_builtin_result(self):
        result = _builtin_bytes_to_string([[72, 73], "ascii"], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == "HI"

    def test_list_get_returns_builtin_result(self):
        result = _builtin_list_get([[10, 20, 30], 1], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == 20

    def test_list_set_returns_builtin_result(self):
        result = _builtin_list_set([[1, 2, 3], 1, 99], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == [1, 99, 3]

    def test_make_list_returns_builtin_result(self):
        result = _builtin_make_list([3, 0], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == [0, 0, 0]

    def test_string_find_returns_builtin_result(self):
        result = _builtin_string_find(["hello", "ll"], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == 2

    def test_uncomputable_returns_builtin_result(self):
        result = _builtin_nibble_get([], None)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE

    def test_prepare_digits_returns_builtin_result(self):
        result = _builtin_cobol_prepare_digits(["10", 4, 0, False], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == [0, 0, 1, 0]

    def test_int_to_binary_bytes_returns_builtin_result(self):
        result = _builtin_int_to_binary_bytes([1234, 2, True], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == list((1234).to_bytes(2, "big", signed=True))

    def test_blank_when_zero_returns_builtin_result(self):
        result = _builtin_cobol_blank_when_zero([[0xF0, 0xF0], "0", 2], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == [0x40, 0x40]
