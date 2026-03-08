"""Unit tests for the TypeExpr algebraic data type."""

from __future__ import annotations

import pytest

from interpreter.type_expr import (
    TypeExpr,
    ScalarType,
    ParameterizedType,
    parse_type,
    scalar,
    pointer,
    array_of,
    map_of,
)


class TestScalarType:
    def test_str_returns_name(self):
        assert str(ScalarType("Int")) == "Int"

    def test_equality(self):
        assert ScalarType("Int") == ScalarType("Int")
        assert ScalarType("Int") != ScalarType("Float")

    def test_hashable(self):
        s = {ScalarType("Int"), ScalarType("Int"), ScalarType("Float")}
        assert len(s) == 2

    def test_frozen(self):
        t = ScalarType("Int")
        with pytest.raises(AttributeError):
            t.name = "Float"  # type: ignore[misc]

    def test_is_type_expr(self):
        assert isinstance(ScalarType("Int"), TypeExpr)


class TestParameterizedType:
    def test_str_single_param(self):
        t = ParameterizedType("Pointer", (ScalarType("Int"),))
        assert str(t) == "Pointer[Int]"

    def test_str_two_params(self):
        t = ParameterizedType("Map", (ScalarType("String"), ScalarType("Int")))
        assert str(t) == "Map[String, Int]"

    def test_str_nested(self):
        inner = ParameterizedType("Array", (ScalarType("Int"),))
        outer = ParameterizedType("Pointer", (inner,))
        assert str(outer) == "Pointer[Array[Int]]"

    def test_equality(self):
        a = ParameterizedType("Pointer", (ScalarType("Int"),))
        b = ParameterizedType("Pointer", (ScalarType("Int"),))
        assert a == b

    def test_inequality_different_constructor(self):
        a = ParameterizedType("Pointer", (ScalarType("Int"),))
        b = ParameterizedType("Array", (ScalarType("Int"),))
        assert a != b

    def test_inequality_different_args(self):
        a = ParameterizedType("Pointer", (ScalarType("Int"),))
        b = ParameterizedType("Pointer", (ScalarType("Float"),))
        assert a != b

    def test_hashable(self):
        a = ParameterizedType("Pointer", (ScalarType("Int"),))
        b = ParameterizedType("Pointer", (ScalarType("Int"),))
        assert hash(a) == hash(b)
        s = {a, b}
        assert len(s) == 1

    def test_frozen(self):
        t = ParameterizedType("Pointer", (ScalarType("Int"),))
        with pytest.raises(AttributeError):
            t.constructor = "Array"  # type: ignore[misc]

    def test_is_type_expr(self):
        assert isinstance(ParameterizedType("Pointer", (ScalarType("Int"),)), TypeExpr)


class TestParseType:
    def test_parse_scalar(self):
        assert parse_type("Int") == ScalarType("Int")

    def test_parse_scalar_string(self):
        assert parse_type("String") == ScalarType("String")

    def test_parse_single_param(self):
        result = parse_type("Pointer[Int]")
        expected = ParameterizedType("Pointer", (ScalarType("Int"),))
        assert result == expected

    def test_parse_two_params(self):
        result = parse_type("Map[String, Int]")
        expected = ParameterizedType("Map", (ScalarType("String"), ScalarType("Int")))
        assert result == expected

    def test_parse_nested(self):
        result = parse_type("Pointer[Array[Int]]")
        expected = ParameterizedType(
            "Pointer", (ParameterizedType("Array", (ScalarType("Int"),)),)
        )
        assert result == expected

    def test_parse_deeply_nested(self):
        result = parse_type("Map[String, Array[Pointer[Int]]]")
        expected = ParameterizedType(
            "Map",
            (
                ScalarType("String"),
                ParameterizedType(
                    "Array",
                    (ParameterizedType("Pointer", (ScalarType("Int"),)),),
                ),
            ),
        )
        assert result == expected

    def test_roundtrip_scalar(self):
        assert str(parse_type("Int")) == "Int"

    def test_roundtrip_parameterized(self):
        assert str(parse_type("Pointer[Int]")) == "Pointer[Int]"

    def test_roundtrip_nested(self):
        original = "Map[String, Array[Pointer[Int]]]"
        assert str(parse_type(original)) == original

    def test_parse_empty_string(self):
        assert parse_type("") == ScalarType("")

    def test_parse_unknown_type(self):
        """Unknown type names are valid scalars — frontends pass through raw names."""
        assert parse_type("MyClass") == ScalarType("MyClass")


class TestConvenienceConstructors:
    def test_scalar(self):
        assert scalar("Int") == ScalarType("Int")

    def test_pointer(self):
        result = pointer(scalar("Int"))
        assert result == ParameterizedType("Pointer", (ScalarType("Int"),))
        assert str(result) == "Pointer[Int]"

    def test_array_of(self):
        result = array_of(scalar("String"))
        assert result == ParameterizedType("Array", (ScalarType("String"),))
        assert str(result) == "Array[String]"

    def test_map_of(self):
        result = map_of(scalar("String"), scalar("Int"))
        assert result == ParameterizedType(
            "Map", (ScalarType("String"), ScalarType("Int"))
        )
        assert str(result) == "Map[String, Int]"

    def test_nested_convenience(self):
        result = pointer(array_of(scalar("Int")))
        assert str(result) == "Pointer[Array[Int]]"


class TestTypeExprStringCompatibility:
    """TypeExpr values compare equal to their string representations.

    This enables gradual migration: code that stores TypeExpr in dicts
    can still be queried with plain strings.
    """

    def test_scalar_equals_string(self):
        assert ScalarType("Int") == "Int"

    def test_scalar_equals_string_reverse(self):
        assert "Int" == ScalarType("Int")

    def test_scalar_not_equals_different_string(self):
        assert ScalarType("Int") != "Float"

    def test_parameterized_equals_string(self):
        t = ParameterizedType("Pointer", (ScalarType("Int"),))
        assert t == "Pointer[Int]"

    def test_parameterized_equals_string_reverse(self):
        t = ParameterizedType("Pointer", (ScalarType("Int"),))
        assert "Pointer[Int]" == t

    def test_nested_parameterized_equals_string(self):
        t = ParameterizedType(
            "Pointer", (ParameterizedType("Array", (ScalarType("Int"),)),)
        )
        assert t == "Pointer[Array[Int]]"

    def test_scalar_hash_matches_string_hash(self):
        """Required for correct dict/set behavior when mixing str and TypeExpr."""
        assert hash(ScalarType("Int")) == hash("Int")

    def test_parameterized_hash_matches_string_hash(self):
        t = ParameterizedType("Pointer", (ScalarType("Int"),))
        assert hash(t) == hash("Pointer[Int]")

    def test_scalar_in_set_with_string(self):
        """A set containing ScalarType('Int') should recognize 'Int' as duplicate."""
        s = {ScalarType("Int")}
        assert "Int" in s

    def test_string_in_set_with_scalar(self):
        s = {"Int"}
        assert ScalarType("Int") in s

    def test_empty_scalar_equals_empty_string(self):
        assert ScalarType("") == ""

    def test_scalar_not_equals_none(self):
        assert ScalarType("Int") != None  # noqa: E711

    def test_scalar_not_equals_int(self):
        assert ScalarType("Int") != 42


class TestTypeExprProperties:
    def test_scalar_constructor_name(self):
        """ScalarType has no constructor — it IS the base type."""
        t = ScalarType("Int")
        assert t.name == "Int"

    def test_parameterized_constructor_and_args(self):
        t = ParameterizedType("Pointer", (ScalarType("Int"),))
        assert t.constructor == "Pointer"
        assert t.arguments == (ScalarType("Int"),)

    def test_parameterized_base_name(self):
        """The constructor name is the 'base' for TypeGraph lookups."""
        t = ParameterizedType("Array", (ScalarType("Int"),))
        assert t.constructor == "Array"
