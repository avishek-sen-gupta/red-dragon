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
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm import Operators
from interpreter.vm.vm_types import BuiltinResult


class TestByteBuiltinsReturnBuiltinResult:
    def test_nibble_get_returns_builtin_result(self):
        result = _builtin_nibble_get(
            [typed_from_runtime(0xAB), typed_from_runtime("high")], None
        )
        assert isinstance(result, BuiltinResult)
        assert result.value == 0xA
        assert result.new_objects == []

    def test_byte_from_int_returns_builtin_result(self):
        result = _builtin_byte_from_int([typed_from_runtime(256)], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == 0

    def test_bytes_to_string_returns_builtin_result(self):
        result = _builtin_bytes_to_string(
            [typed_from_runtime([72, 73]), typed_from_runtime("ascii")], None
        )
        assert isinstance(result, BuiltinResult)
        assert result.value == "HI"

    def test_list_get_returns_builtin_result(self):
        result = _builtin_list_get(
            [typed_from_runtime([10, 20, 30]), typed_from_runtime(1)], None
        )
        assert isinstance(result, BuiltinResult)
        assert result.value == 20

    def test_list_set_returns_builtin_result(self):
        result = _builtin_list_set(
            [
                typed_from_runtime([1, 2, 3]),
                typed_from_runtime(1),
                typed_from_runtime(99),
            ],
            None,
        )
        assert isinstance(result, BuiltinResult)
        assert result.value == [1, 99, 3]

    def test_make_list_returns_builtin_result(self):
        result = _builtin_make_list(
            [typed_from_runtime(3), typed_from_runtime(0)], None
        )
        assert isinstance(result, BuiltinResult)
        assert result.value == [0, 0, 0]

    def test_string_find_returns_builtin_result(self):
        result = _builtin_string_find(
            [typed_from_runtime("hello"), typed_from_runtime("ll")], None
        )
        assert isinstance(result, BuiltinResult)
        assert result.value == 2

    def test_uncomputable_returns_builtin_result(self):
        result = _builtin_nibble_get([], None)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE

    def test_prepare_digits_returns_builtin_result(self):
        result = _builtin_cobol_prepare_digits(
            [
                typed_from_runtime("10"),
                typed_from_runtime(4),
                typed_from_runtime(0),
                typed_from_runtime(False),
            ],
            None,
        )
        assert isinstance(result, BuiltinResult)
        assert result.value == [0, 0, 1, 0]

    def test_int_to_binary_bytes_returns_builtin_result(self):
        result = _builtin_int_to_binary_bytes(
            [typed_from_runtime(1234), typed_from_runtime(2), typed_from_runtime(True)],
            None,
        )
        assert isinstance(result, BuiltinResult)
        assert result.value == list((1234).to_bytes(2, "big", signed=True))

    def test_blank_when_zero_returns_builtin_result(self):
        result = _builtin_cobol_blank_when_zero(
            [
                typed_from_runtime([0xF0, 0xF0]),
                typed_from_runtime("0"),
                typed_from_runtime(2),
            ],
            None,
        )
        assert isinstance(result, BuiltinResult)
        assert result.value == [0x40, 0x40]
