"""Unit tests for string identity builtins: to_string, String::from."""

from interpreter.vm.builtins import Builtins
from interpreter.types.typed_value import typed


class TestToStringBuiltin:
    def test_to_string_in_method_table(self):
        """to_string should be registered in METHOD_TABLE."""
        assert "to_string" in Builtins.METHOD_TABLE

    def test_to_string_returns_string_value(self):
        """to_string on a string should return the same string."""
        fn = Builtins.METHOD_TABLE["to_string"]
        result = fn(typed("hello"), [], None)
        assert result.value == "hello"

    def test_to_string_returns_int_as_string(self):
        """to_string on an int should return its string representation."""
        fn = Builtins.METHOD_TABLE["to_string"]
        result = fn(typed(42), [], None)
        assert result.value == "42"
