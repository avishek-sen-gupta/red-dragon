"""Unit tests for the TypeExpr algebraic data type."""

from __future__ import annotations

import pytest

from interpreter.type_expr import (
    TypeExpr,
    ScalarType,
    ParameterizedType,
    UnionType,
    UnknownType,
    FunctionType,
    TypeVar,
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
    fn_type,
    tuple_of,
    typevar,
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


# ---------------------------------------------------------------------------
# FunctionType
# ---------------------------------------------------------------------------


class TestFunctionType:
    def test_str_with_params(self):
        t = FunctionType(
            params=(scalar("Int"), scalar("String")), return_type=scalar("Bool")
        )
        assert str(t) == "Fn(Int, String) -> Bool"

    def test_str_no_params(self):
        t = FunctionType(params=(), return_type=scalar("Int"))
        assert str(t) == "Fn() -> Int"

    def test_str_single_param(self):
        t = FunctionType(params=(scalar("Int"),), return_type=scalar("String"))
        assert str(t) == "Fn(Int) -> String"

    def test_equality(self):
        a = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        b = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        assert a == b

    def test_inequality_different_params(self):
        a = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        b = FunctionType(params=(scalar("String"),), return_type=scalar("Bool"))
        assert a != b

    def test_inequality_different_return(self):
        a = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        b = FunctionType(params=(scalar("Int"),), return_type=scalar("String"))
        assert a != b

    def test_inequality_different_arity(self):
        a = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        b = FunctionType(
            params=(scalar("Int"), scalar("Int")), return_type=scalar("Bool")
        )
        assert a != b

    def test_hashable(self):
        a = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        b = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        assert hash(a) == hash(b)
        s = {a, b}
        assert len(s) == 1

    def test_frozen(self):
        t = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        with pytest.raises(AttributeError):
            t.params = ()  # type: ignore[misc]

    def test_is_type_expr(self):
        t = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        assert isinstance(t, TypeExpr)

    def test_string_compatibility(self):
        t = FunctionType(
            params=(scalar("Int"), scalar("String")), return_type=scalar("Bool")
        )
        assert t == "Fn(Int, String) -> Bool"

    def test_string_compatibility_reverse(self):
        t = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        assert "Fn(Int) -> Bool" == t

    def test_hash_matches_string(self):
        t = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        assert hash(t) == hash("Fn(Int) -> Bool")

    def test_in_set_with_string(self):
        s = {FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))}
        assert "Fn(Int) -> Bool" in s

    def test_nested_function_type(self):
        """FunctionType with a FunctionType parameter."""
        inner = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        outer = FunctionType(params=(inner,), return_type=scalar("String"))
        assert str(outer) == "Fn(Fn(Int) -> Bool) -> String"

    def test_not_equals_scalar(self):
        t = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        assert t != scalar("Int")

    def test_not_equals_parameterized(self):
        t = FunctionType(params=(scalar("Int"),), return_type=scalar("Bool"))
        assert t != pointer(scalar("Int"))

    def test_truthy(self):
        t = FunctionType(params=(), return_type=scalar("Int"))
        assert t


class TestFnTypeConstructor:
    def test_fn_type_with_params(self):
        result = fn_type([scalar("Int"), scalar("String")], scalar("Bool"))
        assert isinstance(result, FunctionType)
        assert result.params == (scalar("Int"), scalar("String"))
        assert result.return_type == scalar("Bool")

    def test_fn_type_no_params(self):
        result = fn_type([], scalar("Int"))
        assert isinstance(result, FunctionType)
        assert result.params == ()
        assert result.return_type == scalar("Int")


class TestFunctionTypeParsing:
    def test_parse_no_params(self):
        result = parse_type("Fn() -> Int")
        assert isinstance(result, FunctionType)
        assert result.params == ()
        assert result.return_type == scalar("Int")

    def test_parse_single_param(self):
        result = parse_type("Fn(Int) -> Bool")
        assert isinstance(result, FunctionType)
        assert result.params == (scalar("Int"),)
        assert result.return_type == scalar("Bool")

    def test_parse_two_params(self):
        result = parse_type("Fn(Int, String) -> Bool")
        assert isinstance(result, FunctionType)
        assert result.params == (scalar("Int"), scalar("String"))
        assert result.return_type == scalar("Bool")

    def test_parse_parameterized_return(self):
        result = parse_type("Fn(Int) -> Array[String]")
        assert isinstance(result, FunctionType)
        assert result.return_type == array_of(scalar("String"))

    def test_parse_parameterized_param(self):
        result = parse_type("Fn(Array[Int]) -> Bool")
        assert isinstance(result, FunctionType)
        assert result.params == (array_of(scalar("Int")),)

    def test_parse_nested_function_type(self):
        """Fn(Fn(Int) -> Bool) -> String"""
        result = parse_type("Fn(Fn(Int) -> Bool) -> String")
        assert isinstance(result, FunctionType)
        inner = result.params[0]
        assert isinstance(inner, FunctionType)
        assert inner.params == (scalar("Int"),)
        assert inner.return_type == scalar("Bool")
        assert result.return_type == scalar("String")

    def test_roundtrip_no_params(self):
        original = "Fn() -> Int"
        assert str(parse_type(original)) == original

    def test_roundtrip_two_params(self):
        original = "Fn(Int, String) -> Bool"
        assert str(parse_type(original)) == original

    def test_roundtrip_nested(self):
        original = "Fn(Fn(Int) -> Bool) -> String"
        assert str(parse_type(original)) == original

    def test_roundtrip_parameterized_return(self):
        original = "Fn(Int) -> Array[String]"
        assert str(parse_type(original)) == original

    def test_fn_as_scalar_name_without_parens(self):
        """Bare 'Fn' without parens should parse as a scalar type."""
        result = parse_type("Fn")
        assert isinstance(result, ScalarType)
        assert result.name == "Fn"


class TestTupleOfConstructor:
    """Tests for the tuple_of() convenience constructor."""

    def test_single_element_tuple(self):
        t = tuple_of(scalar("Int"))
        assert isinstance(t, ParameterizedType)
        assert t.constructor == "Tuple"
        assert t.arguments == (scalar("Int"),)
        assert str(t) == "Tuple[Int]"

    def test_two_element_tuple(self):
        t = tuple_of(scalar("Int"), scalar("String"))
        assert str(t) == "Tuple[Int, String]"
        assert t.arguments == (scalar("Int"), scalar("String"))

    def test_three_element_tuple(self):
        t = tuple_of(scalar("Int"), scalar("String"), scalar("Bool"))
        assert str(t) == "Tuple[Int, String, Bool]"

    def test_nested_tuple(self):
        inner = tuple_of(scalar("Int"), scalar("String"))
        outer = tuple_of(inner, scalar("Bool"))
        assert str(outer) == "Tuple[Tuple[Int, String], Bool]"

    def test_tuple_with_parameterized_element(self):
        t = tuple_of(array_of(scalar("Int")), scalar("String"))
        assert str(t) == "Tuple[Array[Int], String]"

    def test_tuple_equality_with_string(self):
        t = tuple_of(scalar("Int"), scalar("String"))
        assert t == "Tuple[Int, String]"

    def test_tuple_roundtrip_through_parser(self):
        original = "Tuple[Int, String, Bool]"
        assert str(parse_type(original)) == original

    def test_nested_tuple_roundtrip(self):
        original = "Tuple[Tuple[Int, String], Bool]"
        assert str(parse_type(original)) == original

    def test_tuple_hash_consistency(self):
        t1 = tuple_of(scalar("Int"), scalar("String"))
        t2 = parse_type("Tuple[Int, String]")
        assert hash(t1) == hash(t2)
        assert t1 == t2


class TestTypeVar:
    """Tests for TypeVar type expressions."""

    def test_unbounded_typevar_str(self):
        t = typevar("T")
        assert str(t) == "T"

    def test_bounded_typevar_str(self):
        t = typevar("T", scalar("Number"))
        assert str(t) == "T: Number"

    def test_typevar_equality(self):
        a = typevar("T", scalar("Number"))
        b = typevar("T", scalar("Number"))
        assert a == b

    def test_typevar_inequality_name(self):
        a = typevar("T", scalar("Number"))
        b = typevar("U", scalar("Number"))
        assert a != b

    def test_typevar_inequality_bound(self):
        a = typevar("T", scalar("Number"))
        b = typevar("T", scalar("String"))
        assert a != b

    def test_typevar_not_equal_to_scalar(self):
        t = typevar("T")
        assert t != scalar("T")

    def test_typevar_hash_consistency(self):
        a = typevar("T", scalar("Number"))
        b = typevar("T", scalar("Number"))
        assert hash(a) == hash(b)

    def test_typevar_string_comparison(self):
        t = typevar("T", scalar("Number"))
        assert t == "T: Number"

    def test_typevar_is_truthy(self):
        assert bool(typevar("T"))

    def test_typevar_constructor(self):
        t = typevar("T", scalar("Int"))
        assert isinstance(t, TypeVar)
        assert t.name == "T"
        assert t.bound == scalar("Int")
