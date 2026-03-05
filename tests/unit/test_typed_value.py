"""Tests for TypedValue — value + type hint wrapper."""

import pytest

from interpreter.typed_value import TypedValue


class TestTypedValue:
    def test_wraps_value_and_hint(self):
        tv = TypedValue(value=42, type_hint="Int")
        assert tv.value == 42
        assert tv.type_hint == "Int"

    def test_default_hint_is_empty_string(self):
        tv = TypedValue(value=3.14)
        assert tv.type_hint == ""

    def test_frozen_immutable(self):
        tv = TypedValue(value=42, type_hint="Int")
        with pytest.raises(AttributeError):
            tv.value = 99

    def test_unwrap_returns_raw_value(self):
        tv = TypedValue(value="hello", type_hint="String")
        assert tv.value == "hello"

    def test_equality(self):
        a = TypedValue(value=42, type_hint="Int")
        b = TypedValue(value=42, type_hint="Int")
        assert a == b

    def test_inequality_different_hint(self):
        a = TypedValue(value=42, type_hint="Int")
        b = TypedValue(value=42, type_hint="Float")
        assert a != b
