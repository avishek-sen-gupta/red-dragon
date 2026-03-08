"""Unit tests for the TypeExpr algebraic data type."""

from __future__ import annotations

import pytest

from interpreter.type_expr import (
    TypeExpr,
    ScalarType,
    ParameterizedType,
    UnionType,
    UnknownType,
    UNKNOWN,
    parse_type,
    scalar,
    pointer,
    array_of,
    map_of,
    union_of,
    optional,
    is_optional,
    unwrap_optional,
    unknown,
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

    def test_parse_multi_arg_nested_in_multi_arg(self):
        result = parse_type("Map[String, Map[Int, String]]")
        expected = ParameterizedType(
            "Map",
            (
                ScalarType("String"),
                ParameterizedType("Map", (ScalarType("Int"), ScalarType("String"))),
            ),
        )
        assert result == expected

    def test_parse_multi_arg_nested_both_positions(self):
        result = parse_type("Map[Map[Int, String], Map[Bool, Float]]")
        expected = ParameterizedType(
            "Map",
            (
                ParameterizedType("Map", (ScalarType("Int"), ScalarType("String"))),
                ParameterizedType("Map", (ScalarType("Bool"), ScalarType("Float"))),
            ),
        )
        assert result == expected

    def test_parse_three_type_args(self):
        result = parse_type("Triple[Int, String, Bool]")
        expected = ParameterizedType(
            "Triple",
            (ScalarType("Int"), ScalarType("String"), ScalarType("Bool")),
        )
        assert result == expected

    def test_roundtrip_multi_arg_nested(self):
        original = "Map[String, Map[Int, String]]"
        assert str(parse_type(original)) == original

    def test_roundtrip_multi_arg_nested_both_positions(self):
        original = "Map[Map[Int, String], Map[Bool, Float]]"
        assert str(parse_type(original)) == original

    def test_roundtrip_scalar(self):
        assert str(parse_type("Int")) == "Int"

    def test_roundtrip_parameterized(self):
        assert str(parse_type("Pointer[Int]")) == "Pointer[Int]"

    def test_roundtrip_nested(self):
        original = "Map[String, Array[Pointer[Int]]]"
        assert str(parse_type(original)) == original

    def test_parse_empty_string_returns_unknown(self):
        result = parse_type("")
        assert isinstance(result, UnknownType)
        assert result is UNKNOWN

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


class TestUnknownType:
    """Tests for the UnknownType sentinel representing 'type not yet known'."""

    def test_singleton_identity(self):
        assert unknown() is UNKNOWN

    def test_str_returns_empty(self):
        assert str(UNKNOWN) == ""

    def test_bool_is_falsy(self):
        assert not UNKNOWN
        assert bool(UNKNOWN) is False

    def test_equals_empty_string(self):
        assert UNKNOWN == ""

    def test_empty_string_equals_unknown(self):
        assert "" == UNKNOWN

    def test_not_equals_nonempty_string(self):
        assert UNKNOWN != "Int"

    def test_equals_another_unknown(self):
        assert UNKNOWN == UnknownType()

    def test_not_equals_scalar(self):
        assert UNKNOWN != ScalarType("Int")

    def test_not_equals_empty_scalar(self):
        """UnknownType is distinct from ScalarType('') — they represent different concepts."""
        # UnknownType means "type not known"; ScalarType("") would be a type named ""
        # After migration, ScalarType("") should not appear — parse_type("") returns UNKNOWN
        assert UNKNOWN != ScalarType("")

    def test_hash_matches_empty_string(self):
        assert hash(UNKNOWN) == hash("")

    def test_is_type_expr(self):
        assert isinstance(UNKNOWN, TypeExpr)

    def test_parse_type_roundtrip(self):
        """parse_type(str(UNKNOWN)) returns UNKNOWN."""
        assert parse_type(str(UNKNOWN)) is UNKNOWN

    def test_unknown_in_if_check(self):
        """Common pattern: 'if type_expr:' should be False for UNKNOWN."""
        result = UNKNOWN
        executed = False
        if result:
            executed = True
        assert not executed

    def test_known_type_in_if_check(self):
        """Contrast: ScalarType('Int') should be truthy."""
        result = scalar("Int")
        assert result


# ---------------------------------------------------------------------------
# UnionType
# ---------------------------------------------------------------------------


class TestUnionType:
    def test_str_canonical_sorted(self):
        """Union members are sorted alphabetically in str output."""
        u = union_of(scalar("String"), scalar("Int"))
        assert str(u) == "Union[Int, String]"

    def test_str_three_members(self):
        u = union_of(scalar("Bool"), scalar("String"), scalar("Int"))
        assert str(u) == "Union[Bool, Int, String]"

    def test_eq_with_string(self):
        u = union_of(scalar("Int"), scalar("String"))
        assert u == "Union[Int, String]"

    def test_eq_with_same_union(self):
        a = union_of(scalar("Int"), scalar("String"))
        b = union_of(scalar("String"), scalar("Int"))
        assert a == b

    def test_hash_consistent_with_str(self):
        u = union_of(scalar("Int"), scalar("String"))
        assert hash(u) == hash("Union[Int, String]")

    def test_hash_order_independent(self):
        a = union_of(scalar("Int"), scalar("String"))
        b = union_of(scalar("String"), scalar("Int"))
        assert hash(a) == hash(b)

    def test_truthy(self):
        u = union_of(scalar("Int"), scalar("String"))
        assert u

    def test_is_type_expr(self):
        u = union_of(scalar("Int"), scalar("String"))
        assert isinstance(u, TypeExpr)
        assert isinstance(u, UnionType)

    def test_members_frozenset(self):
        u = union_of(scalar("Int"), scalar("String"))
        assert isinstance(u, UnionType)
        assert u.members == frozenset({scalar("Int"), scalar("String")})

    def test_singleton_elimination(self):
        """Union of a single type collapses to that type."""
        result = union_of(scalar("Int"))
        assert isinstance(result, ScalarType)
        assert result == "Int"

    def test_dedup(self):
        """Duplicate members are removed, may collapse to singleton."""
        result = union_of(scalar("Int"), scalar("Int"))
        assert isinstance(result, ScalarType)
        assert result == "Int"

    def test_flatten_nested_unions(self):
        """Nested unions are flattened into a single union."""
        inner = union_of(scalar("Int"), scalar("String"))
        outer = union_of(inner, scalar("Bool"))
        assert isinstance(outer, UnionType)
        assert str(outer) == "Union[Bool, Int, String]"

    def test_empty_union_returns_unknown(self):
        """Union with no members returns UNKNOWN."""
        result = union_of()
        assert result is UNKNOWN

    def test_unknown_members_ignored(self):
        """UNKNOWN members are filtered out."""
        result = union_of(scalar("Int"), UNKNOWN)
        assert isinstance(result, ScalarType)
        assert result == "Int"

    def test_eq_different_members(self):
        a = union_of(scalar("Int"), scalar("String"))
        b = union_of(scalar("Int"), scalar("Bool"))
        assert a != b

    def test_eq_with_scalar_is_false(self):
        u = union_of(scalar("Int"), scalar("String"))
        assert u != scalar("Int")

    def test_parameterized_members(self):
        """Union can contain parameterized types."""
        u = union_of(array_of(scalar("Int")), scalar("String"))
        assert str(u) == "Union[Array[Int], String]"


class TestUnionTypeParsing:
    def test_parse_union(self):
        result = parse_type("Union[Int, String]")
        assert isinstance(result, UnionType)
        assert result.members == frozenset({scalar("Int"), scalar("String")})

    def test_parse_union_three_members(self):
        result = parse_type("Union[Bool, Int, String]")
        assert isinstance(result, UnionType)
        assert len(result.members) == 3

    def test_parse_union_with_parameterized(self):
        result = parse_type("Union[Array[Int], String]")
        assert isinstance(result, UnionType)
        assert array_of(scalar("Int")) in result.members

    def test_roundtrip(self):
        original = "Union[Array[Int], String]"
        assert str(parse_type(original)) == original

    def test_parse_optional(self):
        """Optional[Int] parses as Union[Int, Null]."""
        result = parse_type("Optional[Int]")
        assert isinstance(result, UnionType)
        assert scalar("Int") in result.members
        assert scalar("Null") in result.members

    def test_roundtrip_optional_becomes_union(self):
        """Optional[Int] round-trips as Union[Int, Null] (canonical form)."""
        result = parse_type("Optional[Int]")
        assert str(result) == "Union[Int, Null]"


class TestOptionalConvenience:
    def test_optional_creates_union_with_null(self):
        result = optional(scalar("Int"))
        assert isinstance(result, UnionType)
        assert scalar("Int") in result.members
        assert scalar("Null") in result.members

    def test_is_optional_true(self):
        assert is_optional(optional(scalar("Int")))

    def test_is_optional_false_for_scalar(self):
        assert not is_optional(scalar("Int"))

    def test_is_optional_false_for_union_without_null(self):
        assert not is_optional(union_of(scalar("Int"), scalar("String")))

    def test_unwrap_optional(self):
        result = unwrap_optional(optional(scalar("Int")))
        assert result == scalar("Int")

    def test_unwrap_optional_multi_member(self):
        """Optional of a union: unwrap removes Null, keeps rest as union."""
        t = union_of(scalar("Int"), scalar("String"), scalar("Null"))
        result = unwrap_optional(t)
        assert isinstance(result, UnionType)
        assert scalar("Null") not in result.members
        assert scalar("Int") in result.members
        assert scalar("String") in result.members

    def test_unwrap_non_optional_returns_as_is(self):
        result = unwrap_optional(scalar("Int"))
        assert result == scalar("Int")
