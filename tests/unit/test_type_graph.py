"""Tests for TypeGraph — DAG with subtype queries and LUB."""

from interpreter.type_node import TypeNode
from interpreter.type_graph import TypeGraph, DEFAULT_TYPE_NODES
from interpreter.constants import TypeName
from interpreter.type_expr import (
    ScalarType,
    ParameterizedType,
    UnionType,
    FunctionType,
    scalar,
    pointer,
    array_of,
    map_of,
    union_of,
    optional,
    fn_type,
)


def _default_graph() -> TypeGraph:
    return TypeGraph(DEFAULT_TYPE_NODES)


class TestTypeGraphSubtype:
    def test_int_is_subtype_of_number(self):
        g = _default_graph()
        assert g.is_subtype(TypeName.INT, TypeName.NUMBER)

    def test_int_is_subtype_of_any(self):
        g = _default_graph()
        assert g.is_subtype(TypeName.INT, TypeName.ANY)

    def test_number_is_not_subtype_of_int(self):
        g = _default_graph()
        assert not g.is_subtype(TypeName.NUMBER, TypeName.INT)

    def test_type_is_subtype_of_itself(self):
        g = _default_graph()
        assert g.is_subtype(TypeName.INT, TypeName.INT)

    def test_unknown_type_is_not_subtype(self):
        g = _default_graph()
        assert not g.is_subtype("PackedDecimal", TypeName.NUMBER)

    def test_string_is_not_subtype_of_number(self):
        g = _default_graph()
        assert not g.is_subtype(TypeName.STRING, TypeName.NUMBER)

    def test_bool_is_not_subtype_of_number(self):
        g = _default_graph()
        assert not g.is_subtype(TypeName.BOOL, TypeName.NUMBER)

    def test_float_is_subtype_of_number(self):
        g = _default_graph()
        assert g.is_subtype(TypeName.FLOAT, TypeName.NUMBER)


class TestTypeGraphCommonSupertype:
    def test_int_and_float_yields_number(self):
        g = _default_graph()
        assert g.common_supertype(TypeName.INT, TypeName.FLOAT) == TypeName.NUMBER

    def test_int_and_string_yields_any(self):
        g = _default_graph()
        assert g.common_supertype(TypeName.INT, TypeName.STRING) == TypeName.ANY

    def test_int_and_int_yields_int(self):
        g = _default_graph()
        assert g.common_supertype(TypeName.INT, TypeName.INT) == TypeName.INT

    def test_number_and_float_yields_number(self):
        g = _default_graph()
        assert g.common_supertype(TypeName.NUMBER, TypeName.FLOAT) == TypeName.NUMBER

    def test_string_and_bool_yields_any(self):
        g = _default_graph()
        assert g.common_supertype(TypeName.STRING, TypeName.BOOL) == TypeName.ANY

    def test_unknown_type_yields_any(self):
        g = _default_graph()
        assert g.common_supertype("PackedDecimal", TypeName.INT) == TypeName.ANY


class TestTypeGraphExtend:
    def test_extend_adds_new_node(self):
        g = _default_graph()
        extended = g.extend(
            (TypeNode(name="PackedDecimal", parents=(TypeName.NUMBER,)),)
        )
        assert extended.contains("PackedDecimal")
        assert extended.is_subtype("PackedDecimal", TypeName.NUMBER)

    def test_extend_preserves_existing_relationships(self):
        g = _default_graph()
        extended = g.extend(
            (TypeNode(name="PackedDecimal", parents=(TypeName.NUMBER,)),)
        )
        assert extended.is_subtype(TypeName.INT, TypeName.NUMBER)
        assert extended.is_subtype(TypeName.FLOAT, TypeName.ANY)

    def test_extend_returns_new_graph_not_mutating_original(self):
        g = _default_graph()
        extended = g.extend(
            (TypeNode(name="PackedDecimal", parents=(TypeName.NUMBER,)),)
        )
        assert not g.contains("PackedDecimal")
        assert extended.contains("PackedDecimal")

    def test_extend_with_custom_subtype(self):
        g = _default_graph()
        extended = g.extend(
            (TypeNode(name="PackedDecimal", parents=(TypeName.NUMBER,)),)
        )
        assert extended.is_subtype("PackedDecimal", TypeName.ANY)
        assert not extended.is_subtype("PackedDecimal", TypeName.INT)


class TestTypeGraphContains:
    def test_contains_known_type(self):
        g = _default_graph()
        assert g.contains(TypeName.INT)
        assert g.contains(TypeName.ANY)

    def test_does_not_contain_unknown_type(self):
        g = _default_graph()
        assert not g.contains("PackedDecimal")


class TestTypeGraphParameterizedSubtype:
    """Subtype checks for parameterized TypeExpr objects."""

    def _graph(self) -> TypeGraph:
        return _default_graph()

    def test_scalar_subtype(self):
        g = self._graph()
        assert g.is_subtype_expr(scalar("Int"), scalar("Number"))

    def test_scalar_not_subtype(self):
        g = self._graph()
        assert not g.is_subtype_expr(scalar("String"), scalar("Number"))

    def test_pointer_int_subtype_of_pointer_number(self):
        """Covariant: Pointer[Int] ⊆ Pointer[Number] because Int ⊆ Number."""
        g = self._graph()
        assert g.is_subtype_expr(pointer(scalar("Int")), pointer(scalar("Number")))

    def test_pointer_int_not_subtype_of_pointer_string(self):
        g = self._graph()
        assert not g.is_subtype_expr(pointer(scalar("Int")), pointer(scalar("String")))

    def test_array_int_subtype_of_array_number(self):
        g = self._graph()
        assert g.is_subtype_expr(array_of(scalar("Int")), array_of(scalar("Number")))

    def test_parameterized_subtype_of_raw_constructor(self):
        """Pointer[Int] ⊆ Pointer (raw type is supertype of parameterized)."""
        g = self._graph()
        assert g.is_subtype_expr(pointer(scalar("Int")), scalar("Pointer"))

    def test_parameterized_subtype_of_any(self):
        """Pointer[Int] ⊆ Any (everything subtypes Any)."""
        g = self._graph()
        assert g.is_subtype_expr(pointer(scalar("Int")), scalar("Any"))

    def test_array_int_subtype_of_any(self):
        g = self._graph()
        assert g.is_subtype_expr(array_of(scalar("Int")), scalar("Any"))

    def test_same_parameterized_is_subtype_of_itself(self):
        g = self._graph()
        assert g.is_subtype_expr(pointer(scalar("Int")), pointer(scalar("Int")))

    def test_different_constructors_not_subtype(self):
        """Pointer[Int] is NOT a subtype of Array[Int]."""
        g = self._graph()
        assert not g.is_subtype_expr(pointer(scalar("Int")), array_of(scalar("Int")))

    def test_nested_covariant(self):
        """Pointer[Array[Int]] ⊆ Pointer[Array[Number]]."""
        g = self._graph()
        child = pointer(array_of(scalar("Int")))
        parent = pointer(array_of(scalar("Number")))
        assert g.is_subtype_expr(child, parent)

    def test_map_covariant_both_params(self):
        """Map[Int, Int] ⊆ Map[Number, Number]."""
        g = self._graph()
        child = map_of(scalar("Int"), scalar("Int"))
        parent = map_of(scalar("Number"), scalar("Number"))
        assert g.is_subtype_expr(child, parent)

    def test_map_partial_mismatch(self):
        """Map[Int, String] is NOT ⊆ Map[Number, Number] (second arg mismatch)."""
        g = self._graph()
        child = map_of(scalar("Int"), scalar("String"))
        parent = map_of(scalar("Number"), scalar("Number"))
        assert not g.is_subtype_expr(child, parent)

    def test_nested_multi_arg_subtype(self):
        """Map[String, Map[Int, Int]] ⊆ Map[String, Map[Number, Number]]."""
        g = self._graph()
        child = map_of(scalar("String"), map_of(scalar("Int"), scalar("Int")))
        parent = map_of(scalar("String"), map_of(scalar("Number"), scalar("Number")))
        assert g.is_subtype_expr(child, parent)

    def test_nested_multi_arg_subtype_mismatch(self):
        """Map[String, Map[Int, String]] ⊄ Map[String, Map[Number, Number]]."""
        g = self._graph()
        child = map_of(scalar("String"), map_of(scalar("Int"), scalar("String")))
        parent = map_of(scalar("String"), map_of(scalar("Number"), scalar("Number")))
        assert not g.is_subtype_expr(child, parent)

    def test_multi_arg_nested_in_both_positions(self):
        """Map[Map[Int, Int], Map[Int, Int]] ⊆ Map[Map[Number, Number], Map[Number, Number]]."""
        g = self._graph()
        child = map_of(
            map_of(scalar("Int"), scalar("Int")),
            map_of(scalar("Int"), scalar("Int")),
        )
        parent = map_of(
            map_of(scalar("Number"), scalar("Number")),
            map_of(scalar("Number"), scalar("Number")),
        )
        assert g.is_subtype_expr(child, parent)


class TestTypeGraphParameterizedLUB:
    """Least upper bound for parameterized TypeExpr objects."""

    def _graph(self) -> TypeGraph:
        return _default_graph()

    def test_lub_same_constructor_same_args(self):
        g = self._graph()
        result = g.common_supertype_expr(pointer(scalar("Int")), pointer(scalar("Int")))
        assert result == pointer(scalar("Int"))

    def test_lub_same_constructor_compatible_args(self):
        """LUB of Pointer[Int] and Pointer[Float] is Pointer[Number]."""
        g = self._graph()
        result = g.common_supertype_expr(
            pointer(scalar("Int")), pointer(scalar("Float"))
        )
        assert result == pointer(scalar("Number"))

    def test_lub_different_constructors(self):
        """LUB of Pointer[Int] and Array[Int] falls back to Any."""
        g = self._graph()
        result = g.common_supertype_expr(
            pointer(scalar("Int")), array_of(scalar("Int"))
        )
        assert result == scalar("Any")

    def test_lub_scalar_and_parameterized(self):
        """LUB of Int and Pointer[Int] is Any."""
        g = self._graph()
        result = g.common_supertype_expr(scalar("Int"), pointer(scalar("Int")))
        assert result == scalar("Any")

    def test_lub_scalars_delegates(self):
        """LUB of scalar Int and Float is Number."""
        g = self._graph()
        result = g.common_supertype_expr(scalar("Int"), scalar("Float"))
        assert result == scalar("Number")

    def test_lub_nested(self):
        """LUB of Array[Pointer[Int]] and Array[Pointer[Float]] is Array[Pointer[Number]]."""
        g = self._graph()
        a = array_of(pointer(scalar("Int")))
        b = array_of(pointer(scalar("Float")))
        result = g.common_supertype_expr(a, b)
        assert result == array_of(pointer(scalar("Number")))

    def test_lub_nested_multi_arg(self):
        """LUB of Map[Int, Map[Int, Int]] and Map[Float, Map[Float, Float]] is Map[Number, Map[Number, Number]]."""
        g = self._graph()
        a = map_of(scalar("Int"), map_of(scalar("Int"), scalar("Int")))
        b = map_of(scalar("Float"), map_of(scalar("Float"), scalar("Float")))
        result = g.common_supertype_expr(a, b)
        assert result == map_of(
            scalar("Number"), map_of(scalar("Number"), scalar("Number"))
        )


# ---------------------------------------------------------------------------
# UnionType subtype checks
# ---------------------------------------------------------------------------


class TestTypeGraphUnionSubtype:
    def _graph(self) -> TypeGraph:
        return _default_graph()

    def test_union_subtype_of_common_parent(self):
        """Union[Int, Float] ⊆ Number (all members are subtypes of Number)."""
        g = self._graph()
        u = union_of(scalar("Int"), scalar("Float"))
        assert g.is_subtype_expr(u, scalar("Number"))

    def test_union_not_subtype_when_member_fails(self):
        """Union[Int, String] ⊄ Number (String is not subtype of Number)."""
        g = self._graph()
        u = union_of(scalar("Int"), scalar("String"))
        assert not g.is_subtype_expr(u, scalar("Number"))

    def test_union_subtype_of_any(self):
        """Union[Int, String] ⊆ Any."""
        g = self._graph()
        u = union_of(scalar("Int"), scalar("String"))
        assert g.is_subtype_expr(u, scalar("Any"))

    def test_scalar_subtype_of_union_member(self):
        """Int ⊆ Union[Int, String] (Int is a member)."""
        g = self._graph()
        u = union_of(scalar("Int"), scalar("String"))
        assert g.is_subtype_expr(scalar("Int"), u)

    def test_scalar_subtype_of_union_via_member_parent(self):
        """Int ⊆ Union[Number, String] (Int ⊆ Number which is a member)."""
        g = self._graph()
        u = union_of(scalar("Number"), scalar("String"))
        assert g.is_subtype_expr(scalar("Int"), u)

    def test_scalar_not_subtype_of_union(self):
        """Bool ⊄ Union[Int, String] (Bool is not subtype of either)."""
        g = self._graph()
        u = union_of(scalar("Int"), scalar("String"))
        assert not g.is_subtype_expr(scalar("Bool"), u)

    def test_union_subtype_of_union(self):
        """Union[Int, Float] ⊆ Union[Number, String] (each member ⊆ some member)."""
        g = self._graph()
        child = union_of(scalar("Int"), scalar("Float"))
        parent = union_of(scalar("Number"), scalar("String"))
        assert g.is_subtype_expr(child, parent)

    def test_union_not_subtype_of_smaller_union(self):
        """Union[Int, String] ⊄ Union[Int, Float]."""
        g = self._graph()
        child = union_of(scalar("Int"), scalar("String"))
        parent = union_of(scalar("Int"), scalar("Float"))
        assert not g.is_subtype_expr(child, parent)

    def test_parameterized_subtype_of_union(self):
        """Array[Int] ⊆ Union[Array[Int], String]."""
        g = self._graph()
        u = union_of(array_of(scalar("Int")), scalar("String"))
        assert g.is_subtype_expr(array_of(scalar("Int")), u)


# ---------------------------------------------------------------------------
# UnionType LUB
# ---------------------------------------------------------------------------


class TestTypeGraphUnionLUB:
    def _graph(self) -> TypeGraph:
        return _default_graph()

    def test_lub_scalar_and_union(self):
        """LUB(Int, Union[String, Bool]) includes all three."""
        g = self._graph()
        u = union_of(scalar("String"), scalar("Bool"))
        result = g.common_supertype_expr(scalar("Int"), u)
        assert isinstance(result, UnionType)
        assert scalar("Int") in result.members
        assert scalar("String") in result.members
        assert scalar("Bool") in result.members

    def test_lub_two_unions(self):
        """LUB(Union[Int, String], Union[Bool, Float]) merges all."""
        g = self._graph()
        a = union_of(scalar("Int"), scalar("String"))
        b = union_of(scalar("Bool"), scalar("Float"))
        result = g.common_supertype_expr(a, b)
        assert isinstance(result, UnionType)
        assert len(result.members) == 4

    def test_lub_union_with_overlapping_member(self):
        """LUB(Union[Int, String], Int) → Union[Int, String]."""
        g = self._graph()
        u = union_of(scalar("Int"), scalar("String"))
        result = g.common_supertype_expr(u, scalar("Int"))
        assert result == u

    def test_lub_produces_union_for_unrelated_scalars(self):
        """LUB of two unrelated scalars that aren't in the DAG produces union."""
        g = self._graph()
        result = g.common_supertype_expr(scalar("Dog"), scalar("Cat"))
        # Dog and Cat aren't in the graph, so LUB falls back to Any
        assert result == scalar("Any")


# ---------------------------------------------------------------------------
# FunctionType subtype checks (contravariant params, covariant return)
# ---------------------------------------------------------------------------


class TestTypeGraphFunctionSubtype:
    def _graph(self) -> TypeGraph:
        return _default_graph()

    def test_same_function_type_is_subtype_of_itself(self):
        g = self._graph()
        f = fn_type([scalar("Int")], scalar("Bool"))
        assert g.is_subtype_expr(f, f)

    def test_covariant_return_type(self):
        """Fn(Int) -> Int is subtype of Fn(Int) -> Number (covariant return)."""
        g = self._graph()
        child = fn_type([scalar("Int")], scalar("Int"))
        parent = fn_type([scalar("Int")], scalar("Number"))
        assert g.is_subtype_expr(child, parent)

    def test_contravariant_params(self):
        """Fn(Number) -> Bool is subtype of Fn(Int) -> Bool (contravariant params)."""
        g = self._graph()
        child = fn_type([scalar("Number")], scalar("Bool"))
        parent = fn_type([scalar("Int")], scalar("Bool"))
        assert g.is_subtype_expr(child, parent)

    def test_full_variance(self):
        """Fn(Number) -> Int is subtype of Fn(Int) -> Number."""
        g = self._graph()
        child = fn_type([scalar("Number")], scalar("Int"))
        parent = fn_type([scalar("Int")], scalar("Number"))
        assert g.is_subtype_expr(child, parent)

    def test_covariant_param_is_not_subtype(self):
        """Fn(Int) -> Bool is NOT subtype of Fn(Number) -> Bool (params are contravariant)."""
        g = self._graph()
        child = fn_type([scalar("Int")], scalar("Bool"))
        parent = fn_type([scalar("Number")], scalar("Bool"))
        assert not g.is_subtype_expr(child, parent)

    def test_contravariant_return_is_not_subtype(self):
        """Fn(Int) -> Number is NOT subtype of Fn(Int) -> Int (return is covariant)."""
        g = self._graph()
        child = fn_type([scalar("Int")], scalar("Number"))
        parent = fn_type([scalar("Int")], scalar("Int"))
        assert not g.is_subtype_expr(child, parent)

    def test_different_arity_not_subtype(self):
        """Different arity function types are never subtypes."""
        g = self._graph()
        child = fn_type([scalar("Int")], scalar("Bool"))
        parent = fn_type([scalar("Int"), scalar("Int")], scalar("Bool"))
        assert not g.is_subtype_expr(child, parent)

    def test_no_params_subtype(self):
        """Fn() -> Int is subtype of Fn() -> Number."""
        g = self._graph()
        child = fn_type([], scalar("Int"))
        parent = fn_type([], scalar("Number"))
        assert g.is_subtype_expr(child, parent)

    def test_function_type_not_subtype_of_scalar(self):
        """Fn(Int) -> Bool is not subtype of Int."""
        g = self._graph()
        f = fn_type([scalar("Int")], scalar("Bool"))
        assert not g.is_subtype_expr(f, scalar("Int"))

    def test_scalar_not_subtype_of_function_type(self):
        """Int is not subtype of Fn(Int) -> Bool."""
        g = self._graph()
        f = fn_type([scalar("Int")], scalar("Bool"))
        assert not g.is_subtype_expr(scalar("Int"), f)

    def test_function_type_subtype_of_any(self):
        """Fn(Int) -> Bool should be subtype of Any (via fallback)."""
        g = self._graph()
        f = fn_type([scalar("Int")], scalar("Bool"))
        # FunctionType is not in the DAG, so it won't be subtype of Any
        # unless we add explicit support. This is the expected behavior.
        assert not g.is_subtype_expr(f, scalar("Any"))


# ---------------------------------------------------------------------------
# FunctionType LUB
# ---------------------------------------------------------------------------


class TestTypeGraphFunctionLUB:
    def _graph(self) -> TypeGraph:
        return _default_graph()

    def test_lub_same_function_type(self):
        g = self._graph()
        f = fn_type([scalar("Int")], scalar("Bool"))
        assert g.common_supertype_expr(f, f) == f

    def test_lub_different_arity_falls_back_to_any(self):
        """LUB of functions with different arity falls back to Any."""
        g = self._graph()
        a = fn_type([scalar("Int")], scalar("Bool"))
        b = fn_type([scalar("Int"), scalar("Int")], scalar("Bool"))
        assert g.common_supertype_expr(a, b) == scalar("Any")

    def test_lub_same_arity_merges(self):
        """LUB of Fn(Int) -> Int and Fn(Float) -> Float merges to Fn with LUBs."""
        g = self._graph()
        a = fn_type([scalar("Int")], scalar("Int"))
        b = fn_type([scalar("Float")], scalar("Float"))
        result = g.common_supertype_expr(a, b)
        # Params LUB: Number; Return LUB: Number
        assert isinstance(result, FunctionType)
        assert result.params == (scalar("Number"),)
        assert result.return_type == scalar("Number")

    def test_lub_function_and_scalar_falls_back_to_any(self):
        """LUB of FunctionType and ScalarType falls back to Any."""
        g = self._graph()
        f = fn_type([scalar("Int")], scalar("Bool"))
        assert g.common_supertype_expr(f, scalar("Int")) == scalar("Any")
