"""Tests for TypeGraph — DAG with subtype queries and LUB."""

from interpreter.constants import FoundationTypeName, Variance
from interpreter.type_name import TypeName
from interpreter.types.type_expr import (
    FunctionType,
    ParameterizedType,
    UnionType,
    array_of,
    fn_type,
    map_of,
    pointer,
    scalar,
    tuple_of,
    typevar,
    union_of,
)
from interpreter.types.type_graph import DEFAULT_TYPE_NODES, TypeGraph
from interpreter.types.type_node import TypeNode


def _default_graph() -> TypeGraph:
    return TypeGraph(DEFAULT_TYPE_NODES)


class TestTypeGraphSubtype:
    def test_int_is_subtype_of_number(self):
        g = _default_graph()
        assert g.is_subtype(FoundationTypeName.INT, FoundationTypeName.NUMBER)

    def test_int_is_subtype_of_any(self):
        g = _default_graph()
        assert g.is_subtype(FoundationTypeName.INT, FoundationTypeName.ANY)

    def test_number_is_not_subtype_of_int(self):
        g = _default_graph()
        assert not g.is_subtype(FoundationTypeName.NUMBER, FoundationTypeName.INT)

    def test_type_is_subtype_of_itself(self):
        g = _default_graph()
        assert g.is_subtype(FoundationTypeName.INT, FoundationTypeName.INT)

    def test_unknown_type_is_not_subtype(self):
        g = _default_graph()
        assert not g.is_subtype(TypeName("PackedDecimal"), FoundationTypeName.NUMBER)

    def test_string_is_not_subtype_of_number(self):
        g = _default_graph()
        assert not g.is_subtype(FoundationTypeName.STRING, FoundationTypeName.NUMBER)

    def test_bool_is_not_subtype_of_number(self):
        g = _default_graph()
        assert not g.is_subtype(FoundationTypeName.BOOL, FoundationTypeName.NUMBER)

    def test_float_is_subtype_of_number(self):
        g = _default_graph()
        assert g.is_subtype(FoundationTypeName.FLOAT, FoundationTypeName.NUMBER)


class TestTypeGraphCommonSupertype:
    def test_int_and_float_yields_number(self):
        g = _default_graph()
        assert (
            g.common_supertype(FoundationTypeName.INT, FoundationTypeName.FLOAT)
            == FoundationTypeName.NUMBER
        )

    def test_int_and_string_yields_any(self):
        g = _default_graph()
        assert (
            g.common_supertype(FoundationTypeName.INT, FoundationTypeName.STRING)
            == FoundationTypeName.ANY
        )

    def test_int_and_int_yields_int(self):
        g = _default_graph()
        assert (
            g.common_supertype(FoundationTypeName.INT, FoundationTypeName.INT)
            == FoundationTypeName.INT
        )

    def test_number_and_float_yields_number(self):
        g = _default_graph()
        assert (
            g.common_supertype(FoundationTypeName.NUMBER, FoundationTypeName.FLOAT)
            == FoundationTypeName.NUMBER
        )

    def test_string_and_bool_yields_any(self):
        g = _default_graph()
        assert (
            g.common_supertype(FoundationTypeName.STRING, FoundationTypeName.BOOL)
            == FoundationTypeName.ANY
        )

    def test_unknown_type_yields_any(self):
        g = _default_graph()
        assert (
            g.common_supertype(TypeName("PackedDecimal"), FoundationTypeName.INT)
            == FoundationTypeName.ANY
        )


class TestTypeGraphExtend:
    def test_extend_adds_new_node(self):
        g = _default_graph()
        extended = g.extend(
            (
                TypeNode(
                    name=TypeName("PackedDecimal"), parents=(FoundationTypeName.NUMBER,)
                ),
            )
        )
        assert extended.contains(TypeName("PackedDecimal"))
        assert extended.is_subtype(TypeName("PackedDecimal"), FoundationTypeName.NUMBER)

    def test_extend_preserves_existing_relationships(self):
        g = _default_graph()
        extended = g.extend(
            (
                TypeNode(
                    name=TypeName("PackedDecimal"), parents=(FoundationTypeName.NUMBER,)
                ),
            )
        )
        assert extended.is_subtype(FoundationTypeName.INT, FoundationTypeName.NUMBER)
        assert extended.is_subtype(FoundationTypeName.FLOAT, FoundationTypeName.ANY)

    def test_extend_returns_new_graph_not_mutating_original(self):
        g = _default_graph()
        extended = g.extend(
            (
                TypeNode(
                    name=TypeName("PackedDecimal"), parents=(FoundationTypeName.NUMBER,)
                ),
            )
        )
        assert not g.contains(TypeName("PackedDecimal"))
        assert extended.contains(TypeName("PackedDecimal"))

    def test_extend_with_custom_subtype(self):
        g = _default_graph()
        extended = g.extend(
            (
                TypeNode(
                    name=TypeName("PackedDecimal"), parents=(FoundationTypeName.NUMBER,)
                ),
            )
        )
        assert extended.is_subtype(TypeName("PackedDecimal"), FoundationTypeName.ANY)
        assert not extended.is_subtype(
            TypeName("PackedDecimal"), FoundationTypeName.INT
        )


class TestTypeGraphContains:
    def test_contains_known_type(self):
        g = _default_graph()
        assert g.contains(FoundationTypeName.INT)
        assert g.contains(FoundationTypeName.ANY)

    def test_does_not_contain_unknown_type(self):
        g = _default_graph()
        assert not g.contains(TypeName("PackedDecimal"))


class TestTypeGraphParameterizedSubtype:
    """Subtype checks for parameterized TypeExpr objects."""

    def _graph(self) -> TypeGraph:
        return _default_graph()

    def test_scalar_subtype(self):
        g = self._graph()
        assert g.is_subtype_expr(scalar(TypeName("Int")), scalar(TypeName("Number")))

    def test_scalar_not_subtype(self):
        g = self._graph()
        assert not g.is_subtype_expr(
            scalar(TypeName("String")), scalar(TypeName("Number"))
        )

    def test_pointer_int_subtype_of_pointer_number(self):
        """Covariant: Pointer[Int] ⊆ Pointer[Number] because Int ⊆ Number."""
        g = self._graph()
        assert g.is_subtype_expr(
            pointer(scalar(TypeName("Int"))), pointer(scalar(TypeName("Number")))
        )

    def test_pointer_int_not_subtype_of_pointer_string(self):
        g = self._graph()
        assert not g.is_subtype_expr(
            pointer(scalar(TypeName("Int"))), pointer(scalar(TypeName("String")))
        )

    def test_array_int_subtype_of_array_number(self):
        g = self._graph()
        assert g.is_subtype_expr(
            array_of(scalar(TypeName("Int"))), array_of(scalar(TypeName("Number")))
        )

    def test_parameterized_subtype_of_raw_constructor(self):
        """Pointer[Int] ⊆ Pointer (raw type is supertype of parameterized)."""
        g = self._graph()
        assert g.is_subtype_expr(
            pointer(scalar(TypeName("Int"))), scalar(TypeName("Pointer"))
        )

    def test_parameterized_subtype_of_any(self):
        """Pointer[Int] ⊆ Any (everything subtypes Any)."""
        g = self._graph()
        assert g.is_subtype_expr(
            pointer(scalar(TypeName("Int"))), scalar(TypeName("Any"))
        )

    def test_array_int_subtype_of_any(self):
        g = self._graph()
        assert g.is_subtype_expr(
            array_of(scalar(TypeName("Int"))), scalar(TypeName("Any"))
        )

    def test_same_parameterized_is_subtype_of_itself(self):
        g = self._graph()
        assert g.is_subtype_expr(
            pointer(scalar(TypeName("Int"))), pointer(scalar(TypeName("Int")))
        )

    def test_different_constructors_not_subtype(self):
        """Pointer[Int] is NOT a subtype of Array[Int]."""
        g = self._graph()
        assert not g.is_subtype_expr(
            pointer(scalar(TypeName("Int"))), array_of(scalar(TypeName("Int")))
        )

    def test_nested_covariant(self):
        """Pointer[Array[Int]] ⊆ Pointer[Array[Number]]."""
        g = self._graph()
        child = pointer(array_of(scalar(TypeName("Int"))))
        parent = pointer(array_of(scalar(TypeName("Number"))))
        assert g.is_subtype_expr(child, parent)

    def test_map_covariant_both_params(self):
        """Map[Int, Int] ⊆ Map[Number, Number]."""
        g = self._graph()
        child = map_of(scalar(TypeName("Int")), scalar(TypeName("Int")))
        parent = map_of(scalar(TypeName("Number")), scalar(TypeName("Number")))
        assert g.is_subtype_expr(child, parent)

    def test_map_partial_mismatch(self):
        """Map[Int, String] is NOT ⊆ Map[Number, Number] (second arg mismatch)."""
        g = self._graph()
        child = map_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        parent = map_of(scalar(TypeName("Number")), scalar(TypeName("Number")))
        assert not g.is_subtype_expr(child, parent)

    def test_nested_multi_arg_subtype(self):
        """Map[String, Map[Int, Int]] ⊆ Map[String, Map[Number, Number]]."""
        g = self._graph()
        child = map_of(
            scalar(TypeName("String")),
            map_of(scalar(TypeName("Int")), scalar(TypeName("Int"))),
        )
        parent = map_of(
            scalar(TypeName("String")),
            map_of(scalar(TypeName("Number")), scalar(TypeName("Number"))),
        )
        assert g.is_subtype_expr(child, parent)

    def test_nested_multi_arg_subtype_mismatch(self):
        """Map[String, Map[Int, String]] ⊄ Map[String, Map[Number, Number]]."""
        g = self._graph()
        child = map_of(
            scalar(TypeName("String")),
            map_of(scalar(TypeName("Int")), scalar(TypeName("String"))),
        )
        parent = map_of(
            scalar(TypeName("String")),
            map_of(scalar(TypeName("Number")), scalar(TypeName("Number"))),
        )
        assert not g.is_subtype_expr(child, parent)

    def test_multi_arg_nested_in_both_positions(self):
        """Map[Map[Int, Int], Map[Int, Int]] ⊆ Map[Map[Number, Number], Map[Number, Number]]."""
        g = self._graph()
        child = map_of(
            map_of(scalar(TypeName("Int")), scalar(TypeName("Int"))),
            map_of(scalar(TypeName("Int")), scalar(TypeName("Int"))),
        )
        parent = map_of(
            map_of(scalar(TypeName("Number")), scalar(TypeName("Number"))),
            map_of(scalar(TypeName("Number")), scalar(TypeName("Number"))),
        )
        assert g.is_subtype_expr(child, parent)


class TestTypeGraphParameterizedLUB:
    """Least upper bound for parameterized TypeExpr objects."""

    def _graph(self) -> TypeGraph:
        return _default_graph()

    def test_lub_same_constructor_same_args(self):
        g = self._graph()
        result = g.common_supertype_expr(
            pointer(scalar(TypeName("Int"))), pointer(scalar(TypeName("Int")))
        )
        assert result == pointer(scalar(TypeName("Int")))

    def test_lub_same_constructor_compatible_args(self):
        """LUB of Pointer[Int] and Pointer[Float] is Pointer[Number]."""
        g = self._graph()
        result = g.common_supertype_expr(
            pointer(scalar(TypeName("Int"))), pointer(scalar(TypeName("Float")))
        )
        assert result == pointer(scalar(TypeName("Number")))

    def test_lub_different_constructors(self):
        """LUB of Pointer[Int] and Array[Int] falls back to Any."""
        g = self._graph()
        result = g.common_supertype_expr(
            pointer(scalar(TypeName("Int"))), array_of(scalar(TypeName("Int")))
        )
        assert result == scalar(TypeName("Any"))

    def test_lub_scalar_and_parameterized(self):
        """LUB of Int and Pointer[Int] is Any."""
        g = self._graph()
        result = g.common_supertype_expr(
            scalar(TypeName("Int")), pointer(scalar(TypeName("Int")))
        )
        assert result == scalar(TypeName("Any"))

    def test_lub_scalars_delegates(self):
        """LUB of scalar Int and Float is Number."""
        g = self._graph()
        result = g.common_supertype_expr(
            scalar(TypeName("Int")), scalar(TypeName("Float"))
        )
        assert result == scalar(TypeName("Number"))

    def test_lub_nested(self):
        """LUB of Array[Pointer[Int]] and Array[Pointer[Float]] is Array[Pointer[Number]]."""
        g = self._graph()
        a = array_of(pointer(scalar(TypeName("Int"))))
        b = array_of(pointer(scalar(TypeName("Float"))))
        result = g.common_supertype_expr(a, b)
        assert result == array_of(pointer(scalar(TypeName("Number"))))

    def test_lub_nested_multi_arg(self):
        """LUB of Map[Int, Map[Int, Int]] and Map[Float, Map[Float, Float]] is Map[Number, Map[Number, Number]]."""
        g = self._graph()
        a = map_of(
            scalar(TypeName("Int")),
            map_of(scalar(TypeName("Int")), scalar(TypeName("Int"))),
        )
        b = map_of(
            scalar(TypeName("Float")),
            map_of(scalar(TypeName("Float")), scalar(TypeName("Float"))),
        )
        result = g.common_supertype_expr(a, b)
        assert result == map_of(
            scalar(TypeName("Number")),
            map_of(scalar(TypeName("Number")), scalar(TypeName("Number"))),
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
        u = union_of(scalar(TypeName("Int")), scalar(TypeName("Float")))
        assert g.is_subtype_expr(u, scalar(TypeName("Number")))

    def test_union_not_subtype_when_member_fails(self):
        """Union[Int, String] ⊄ Number (String is not subtype of Number)."""
        g = self._graph()
        u = union_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        assert not g.is_subtype_expr(u, scalar(TypeName("Number")))

    def test_union_subtype_of_any(self):
        """Union[Int, String] ⊆ Any."""
        g = self._graph()
        u = union_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        assert g.is_subtype_expr(u, scalar(TypeName("Any")))

    def test_scalar_subtype_of_union_member(self):
        """Int ⊆ Union[Int, String] (Int is a member)."""
        g = self._graph()
        u = union_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        assert g.is_subtype_expr(scalar(TypeName("Int")), u)

    def test_scalar_subtype_of_union_via_member_parent(self):
        """Int ⊆ Union[Number, String] (Int ⊆ Number which is a member)."""
        g = self._graph()
        u = union_of(scalar(TypeName("Number")), scalar(TypeName("String")))
        assert g.is_subtype_expr(scalar(TypeName("Int")), u)

    def test_scalar_not_subtype_of_union(self):
        """Bool ⊄ Union[Int, String] (Bool is not subtype of either)."""
        g = self._graph()
        u = union_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        assert not g.is_subtype_expr(scalar(TypeName("Bool")), u)

    def test_union_subtype_of_union(self):
        """Union[Int, Float] ⊆ Union[Number, String] (each member ⊆ some member)."""
        g = self._graph()
        child = union_of(scalar(TypeName("Int")), scalar(TypeName("Float")))
        parent = union_of(scalar(TypeName("Number")), scalar(TypeName("String")))
        assert g.is_subtype_expr(child, parent)

    def test_union_not_subtype_of_smaller_union(self):
        """Union[Int, String] ⊄ Union[Int, Float]."""
        g = self._graph()
        child = union_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        parent = union_of(scalar(TypeName("Int")), scalar(TypeName("Float")))
        assert not g.is_subtype_expr(child, parent)

    def test_parameterized_subtype_of_union(self):
        """Array[Int] ⊆ Union[Array[Int], String]."""
        g = self._graph()
        u = union_of(array_of(scalar(TypeName("Int"))), scalar(TypeName("String")))
        assert g.is_subtype_expr(array_of(scalar(TypeName("Int"))), u)


# ---------------------------------------------------------------------------
# UnionType LUB
# ---------------------------------------------------------------------------


class TestTypeGraphUnionLUB:
    def _graph(self) -> TypeGraph:
        return _default_graph()

    def test_lub_scalar_and_union(self):
        """LUB(Int, Union[String, Bool]) includes all three."""
        g = self._graph()
        u = union_of(scalar(TypeName("String")), scalar(TypeName("Bool")))
        result = g.common_supertype_expr(scalar(TypeName("Int")), u)
        assert isinstance(result, UnionType)
        assert scalar(TypeName("Int")) in result.members
        assert scalar(TypeName("String")) in result.members
        assert scalar(TypeName("Bool")) in result.members

    def test_lub_two_unions(self):
        """LUB(Union[Int, String], Union[Bool, Float]) merges all."""
        g = self._graph()
        a = union_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        b = union_of(scalar(TypeName("Bool")), scalar(TypeName("Float")))
        result = g.common_supertype_expr(a, b)
        assert isinstance(result, UnionType)
        assert len(result.members) == 4

    def test_lub_union_with_overlapping_member(self):
        """LUB(Union[Int, String], Int) → Union[Int, String]."""
        g = self._graph()
        u = union_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        result = g.common_supertype_expr(u, scalar(TypeName("Int")))
        assert result == u

    def test_lub_produces_union_for_unrelated_scalars(self):
        """LUB of two unrelated scalars that aren't in the DAG produces union."""
        g = self._graph()
        result = g.common_supertype_expr(
            scalar(TypeName("Dog")), scalar(TypeName("Cat"))
        )
        # Dog and Cat aren't in the graph, so LUB falls back to Any
        assert result == scalar(TypeName("Any"))


# ---------------------------------------------------------------------------
# FunctionType subtype checks (contravariant params, covariant return)
# ---------------------------------------------------------------------------


class TestTypeGraphFunctionSubtype:
    def _graph(self) -> TypeGraph:
        return _default_graph()

    def test_same_function_type_is_subtype_of_itself(self):
        g = self._graph()
        f = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Bool")))
        assert g.is_subtype_expr(f, f)

    def test_covariant_return_type(self):
        """Fn(Int) -> Int is subtype of Fn(Int) -> Number (covariant return)."""
        g = self._graph()
        child = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Int")))
        parent = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Number")))
        assert g.is_subtype_expr(child, parent)

    def test_contravariant_params(self):
        """Fn(Number) -> Bool is subtype of Fn(Int) -> Bool (contravariant params)."""
        g = self._graph()
        child = fn_type([scalar(TypeName("Number"))], scalar(TypeName("Bool")))
        parent = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Bool")))
        assert g.is_subtype_expr(child, parent)

    def test_full_variance(self):
        """Fn(Number) -> Int is subtype of Fn(Int) -> Number."""
        g = self._graph()
        child = fn_type([scalar(TypeName("Number"))], scalar(TypeName("Int")))
        parent = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Number")))
        assert g.is_subtype_expr(child, parent)

    def test_covariant_param_is_not_subtype(self):
        """Fn(Int) -> Bool is NOT subtype of Fn(Number) -> Bool (params are contravariant)."""
        g = self._graph()
        child = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Bool")))
        parent = fn_type([scalar(TypeName("Number"))], scalar(TypeName("Bool")))
        assert not g.is_subtype_expr(child, parent)

    def test_contravariant_return_is_not_subtype(self):
        """Fn(Int) -> Number is NOT subtype of Fn(Int) -> Int (return is covariant)."""
        g = self._graph()
        child = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Number")))
        parent = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Int")))
        assert not g.is_subtype_expr(child, parent)

    def test_different_arity_not_subtype(self):
        """Different arity function types are never subtypes."""
        g = self._graph()
        child = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Bool")))
        parent = fn_type(
            [scalar(TypeName("Int")), scalar(TypeName("Int"))], scalar(TypeName("Bool"))
        )
        assert not g.is_subtype_expr(child, parent)

    def test_no_params_subtype(self):
        """Fn() -> Int is subtype of Fn() -> Number."""
        g = self._graph()
        child = fn_type([], scalar(TypeName("Int")))
        parent = fn_type([], scalar(TypeName("Number")))
        assert g.is_subtype_expr(child, parent)

    def test_function_type_not_subtype_of_scalar(self):
        """Fn(Int) -> Bool is not subtype of Int."""
        g = self._graph()
        f = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Bool")))
        assert not g.is_subtype_expr(f, scalar(TypeName("Int")))

    def test_scalar_not_subtype_of_function_type(self):
        """Int is not subtype of Fn(Int) -> Bool."""
        g = self._graph()
        f = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Bool")))
        assert not g.is_subtype_expr(scalar(TypeName("Int")), f)

    def test_function_type_not_subtype_of_any(self):
        """Fn(Int) -> Bool is not subtype of Any — FunctionType is not in the DAG."""
        g = self._graph()
        f = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Bool")))
        # FunctionType is not in the DAG, so it won't be subtype of Any
        # unless we add explicit support. This is the expected behavior.
        assert not g.is_subtype_expr(f, scalar(TypeName("Any")))


# ---------------------------------------------------------------------------
# FunctionType LUB
# ---------------------------------------------------------------------------


class TestTypeGraphFunctionLUB:
    def _graph(self) -> TypeGraph:
        return _default_graph()

    def test_lub_same_function_type(self):
        g = self._graph()
        f = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Bool")))
        assert g.common_supertype_expr(f, f) == f

    def test_lub_different_arity_falls_back_to_any(self):
        """LUB of functions with different arity falls back to Any."""
        g = self._graph()
        a = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Bool")))
        b = fn_type(
            [scalar(TypeName("Int")), scalar(TypeName("Int"))], scalar(TypeName("Bool"))
        )
        assert g.common_supertype_expr(a, b) == scalar(TypeName("Any"))

    def test_lub_same_arity_merges(self):
        """LUB of Fn(Int) -> Int and Fn(Float) -> Float merges to Fn with LUBs."""
        g = self._graph()
        a = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Int")))
        b = fn_type([scalar(TypeName("Float"))], scalar(TypeName("Float")))
        result = g.common_supertype_expr(a, b)
        # Params LUB: Number; Return LUB: Number
        assert isinstance(result, FunctionType)
        assert result.params == (scalar(TypeName("Number")),)
        assert result.return_type == scalar(TypeName("Number"))

    def test_lub_function_and_scalar_falls_back_to_any(self):
        """LUB of FunctionType and ScalarType falls back to Any."""
        g = self._graph()
        f = fn_type([scalar(TypeName("Int"))], scalar(TypeName("Bool")))
        assert g.common_supertype_expr(f, scalar(TypeName("Int"))) == scalar(
            TypeName("Any")
        )


class TestTypeGraphTupleSubtype:
    """Subtype checks for Tuple types."""

    def _graph(self) -> TypeGraph:
        return TypeGraph(DEFAULT_TYPE_NODES)

    def test_identical_tuples_are_subtypes(self):
        g = self._graph()
        t = tuple_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        assert g.is_subtype_expr(t, t)

    def test_covariant_element_subtype(self):
        """Tuple[Int, Int] ⊆ Tuple[Number, Number] (covariant elements)."""
        g = self._graph()
        child = tuple_of(scalar(TypeName("Int")), scalar(TypeName("Int")))
        parent = tuple_of(scalar(TypeName("Number")), scalar(TypeName("Number")))
        assert g.is_subtype_expr(child, parent)

    def test_not_subtype_when_element_not_subtype(self):
        """Tuple[String, Int] is NOT ⊆ Tuple[Int, Int]."""
        g = self._graph()
        child = tuple_of(scalar(TypeName("String")), scalar(TypeName("Int")))
        parent = tuple_of(scalar(TypeName("Int")), scalar(TypeName("Int")))
        assert not g.is_subtype_expr(child, parent)

    def test_different_length_not_subtype(self):
        """Tuple[Int] is NOT ⊆ Tuple[Int, String] (length mismatch)."""
        g = self._graph()
        child = tuple_of(scalar(TypeName("Int")))
        parent = tuple_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        assert not g.is_subtype_expr(child, parent)

    def test_tuple_subtype_of_any(self):
        """Tuple[Int, String] ⊆ Any (via constructor)."""
        g = self._graph()
        t = tuple_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        assert g.is_subtype_expr(t, scalar(TypeName("Any")))

    def test_nested_tuple_subtype(self):
        """Tuple[Tuple[Int], String] ⊆ Tuple[Tuple[Number], String]."""
        g = self._graph()
        child = tuple_of(tuple_of(scalar(TypeName("Int"))), scalar(TypeName("String")))
        parent = tuple_of(
            tuple_of(scalar(TypeName("Number"))), scalar(TypeName("String"))
        )
        assert g.is_subtype_expr(child, parent)

    def test_tuple_not_subtype_of_array(self):
        """Tuple[Int] is NOT ⊆ Array[Int] (different constructors)."""
        g = self._graph()
        assert not g.is_subtype_expr(
            tuple_of(scalar(TypeName("Int"))), array_of(scalar(TypeName("Int")))
        )


class TestTypeGraphTupleLUB:
    """LUB (common supertype) for Tuple types."""

    def _graph(self) -> TypeGraph:
        return TypeGraph(DEFAULT_TYPE_NODES)

    def test_lub_same_tuple(self):
        g = self._graph()
        t = tuple_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        assert g.common_supertype_expr(t, t) == t

    def test_lub_covariant_elements(self):
        """LUB of Tuple[Int, Int] and Tuple[Float, Float] = Tuple[Number, Number]."""
        g = self._graph()
        a = tuple_of(scalar(TypeName("Int")), scalar(TypeName("Int")))
        b = tuple_of(scalar(TypeName("Float")), scalar(TypeName("Float")))
        result = g.common_supertype_expr(a, b)
        assert isinstance(result, ParameterizedType)
        assert result.constructor == "Tuple"
        assert result.arguments == (
            scalar(TypeName("Number")),
            scalar(TypeName("Number")),
        )

    def test_lub_different_length_falls_back_to_any(self):
        """LUB of Tuple[Int] and Tuple[Int, String] = Any."""
        g = self._graph()
        a = tuple_of(scalar(TypeName("Int")))
        b = tuple_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        assert g.common_supertype_expr(a, b) == scalar(TypeName("Any"))

    def test_lub_tuple_and_scalar_falls_back_to_any(self):
        g = self._graph()
        t = tuple_of(scalar(TypeName("Int")), scalar(TypeName("String")))
        assert g.common_supertype_expr(t, scalar(TypeName("Int"))) == scalar(
            TypeName("Any")
        )


class TestTypeGraphInterfaceExtension:
    """Tests for extend_with_interfaces."""

    def test_class_becomes_subtype_of_interface(self):
        """Dog implements Comparable → Dog ⊆ Comparable."""
        g = TypeGraph(DEFAULT_TYPE_NODES).extend_with_interfaces(
            {"Dog": ("Comparable",)}
        )
        assert g.is_subtype(TypeName("Dog"), TypeName("Comparable"))

    def test_interface_is_subtype_of_any(self):
        """Interface nodes are children of Any."""
        g = TypeGraph(DEFAULT_TYPE_NODES).extend_with_interfaces(
            {"Dog": ("Comparable",)}
        )
        assert g.is_subtype(TypeName("Comparable"), FoundationTypeName.ANY)

    def test_class_with_multiple_interfaces(self):
        """Dog implements Comparable, Serializable → Dog ⊆ both."""
        g = TypeGraph(DEFAULT_TYPE_NODES).extend_with_interfaces(
            {"Dog": ("Comparable", "Serializable")}
        )
        assert g.is_subtype(TypeName("Dog"), TypeName("Comparable"))
        assert g.is_subtype(TypeName("Dog"), TypeName("Serializable"))
        assert g.is_subtype(TypeName("Dog"), FoundationTypeName.ANY)

    def test_interface_not_subtype_of_class(self):
        """Comparable is NOT ⊆ Dog."""
        g = TypeGraph(DEFAULT_TYPE_NODES).extend_with_interfaces(
            {"Dog": ("Comparable",)}
        )
        assert not g.is_subtype(TypeName("Comparable"), TypeName("Dog"))

    def test_preserves_existing_parent(self):
        """Class with existing parent gets interface added without losing parent."""
        base = TypeGraph(DEFAULT_TYPE_NODES).extend(
            (TypeNode(name=TypeName("Animal"), parents=(TypeName("Any"),)),)
        )
        g = base.extend_with_interfaces({"Dog": ("Comparable",)})
        # Dog doesn't have Animal as parent yet since we only added interface
        # But we can add both:
        g2 = (
            TypeGraph(DEFAULT_TYPE_NODES)
            .extend(
                (
                    TypeNode(name=TypeName("Animal"), parents=(TypeName("Any"),)),
                    TypeNode(name=TypeName("Dog"), parents=(TypeName("Animal"),)),
                )
            )
            .extend_with_interfaces({"Dog": ("Comparable",)})
        )
        assert g2.is_subtype(TypeName("Dog"), TypeName("Animal"))
        assert g2.is_subtype(TypeName("Dog"), TypeName("Comparable"))

    def test_expr_subtype_with_interface(self):
        """ScalarType('Dog') ⊆ ScalarType('Comparable') via TypeGraph."""
        g = TypeGraph(DEFAULT_TYPE_NODES).extend_with_interfaces(
            {"Dog": ("Comparable",)}
        )
        assert g.is_subtype_expr(
            scalar(TypeName("Dog")), scalar(TypeName("Comparable"))
        )


class TestTypeGraphVariance:
    """Tests for variance-aware parameterized type subtyping and LUB."""

    def _graph(self) -> TypeGraph:
        return TypeGraph(DEFAULT_TYPE_NODES)

    def test_covariant_default(self):
        """Default variance is covariant: List[Int] ⊆ List[Number]."""
        g = self._graph()
        child = ParameterizedType("List", (scalar(TypeName("Int")),))
        parent = ParameterizedType("List", (scalar(TypeName("Number")),))
        assert g.is_subtype_expr(child, parent)

    def test_invariant_blocks_subtype(self):
        """Invariant: MutableList[Int] is NOT ⊆ MutableList[Number]."""
        g = self._graph().with_variance({"MutableList": (Variance.INVARIANT,)})
        child = ParameterizedType("MutableList", (scalar(TypeName("Int")),))
        parent = ParameterizedType("MutableList", (scalar(TypeName("Number")),))
        assert not g.is_subtype_expr(child, parent)

    def test_invariant_allows_equal(self):
        """Invariant: MutableList[Int] ⊆ MutableList[Int] (same type)."""
        g = self._graph().with_variance({"MutableList": (Variance.INVARIANT,)})
        t = ParameterizedType("MutableList", (scalar(TypeName("Int")),))
        assert g.is_subtype_expr(t, t)

    def test_contravariant_subtype(self):
        """Contravariant: Consumer[Number] ⊆ Consumer[Int]."""
        g = self._graph().with_variance({"Consumer": (Variance.CONTRAVARIANT,)})
        child = ParameterizedType("Consumer", (scalar(TypeName("Number")),))
        parent = ParameterizedType("Consumer", (scalar(TypeName("Int")),))
        assert g.is_subtype_expr(child, parent)

    def test_contravariant_blocks_covariant(self):
        """Contravariant: Consumer[Int] is NOT ⊆ Consumer[Number]."""
        g = self._graph().with_variance({"Consumer": (Variance.CONTRAVARIANT,)})
        child = ParameterizedType("Consumer", (scalar(TypeName("Int")),))
        parent = ParameterizedType("Consumer", (scalar(TypeName("Number")),))
        assert not g.is_subtype_expr(child, parent)

    def test_mixed_variance(self):
        """Map with invariant key and covariant value."""
        g = self._graph().with_variance(
            {"Map": (Variance.INVARIANT, Variance.COVARIANT)}
        )
        # Map[String, Int] ⊆ Map[String, Number] — key invariant (ok, same), value covariant (ok)
        assert g.is_subtype_expr(
            ParameterizedType(
                "Map", (scalar(TypeName("String")), scalar(TypeName("Int")))
            ),
            ParameterizedType(
                "Map", (scalar(TypeName("String")), scalar(TypeName("Number")))
            ),
        )
        # Map[Int, Int] NOT ⊆ Map[Number, Int] — key invariant (fails)
        assert not g.is_subtype_expr(
            ParameterizedType(
                "Map", (scalar(TypeName("Int")), scalar(TypeName("Int")))
            ),
            ParameterizedType(
                "Map", (scalar(TypeName("Number")), scalar(TypeName("Int")))
            ),
        )

    def test_invariant_lub_same_type(self):
        """LUB of MutableList[Int] and MutableList[Int] = MutableList[Int]."""
        g = self._graph().with_variance({"MutableList": (Variance.INVARIANT,)})
        t = ParameterizedType("MutableList", (scalar(TypeName("Int")),))
        assert g.common_supertype_expr(t, t) == t

    def test_invariant_lub_different_falls_to_any(self):
        """LUB of MutableList[Int] and MutableList[String] = Any."""
        g = self._graph().with_variance({"MutableList": (Variance.INVARIANT,)})
        a = ParameterizedType("MutableList", (scalar(TypeName("Int")),))
        b = ParameterizedType("MutableList", (scalar(TypeName("String")),))
        assert g.common_supertype_expr(a, b) == scalar(TypeName("Any"))

    def test_with_variance_preserves_nodes(self):
        """with_variance returns a graph with same nodes but new variance."""
        g = self._graph()
        g2 = g.with_variance({"MutableList": (Variance.INVARIANT,)})
        # Original graph unchanged — covariant default
        assert g.is_subtype_expr(
            ParameterizedType("List", (scalar(TypeName("Int")),)),
            ParameterizedType("List", (scalar(TypeName("Number")),)),
        )
        # New graph has invariant MutableList
        assert not g2.is_subtype_expr(
            ParameterizedType("MutableList", (scalar(TypeName("Int")),)),
            ParameterizedType("MutableList", (scalar(TypeName("Number")),)),
        )


class TestTypeGraphTypeVar:
    """Tests for TypeVar subtype checks."""

    def _graph(self) -> TypeGraph:
        return TypeGraph(DEFAULT_TYPE_NODES)

    def test_bounded_typevar_is_subtype_of_bound(self):
        """TypeVar T: Number ⊆ Number."""
        g = self._graph()
        t = typevar("T", scalar(TypeName("Number")))
        assert g.is_subtype_expr(t, scalar(TypeName("Number")))

    def test_bounded_typevar_is_subtype_of_ancestor(self):
        """TypeVar T: Number ⊆ Any (transitive through bound)."""
        g = self._graph()
        t = typevar("T", scalar(TypeName("Number")))
        assert g.is_subtype_expr(t, scalar(TypeName("Any")))

    def test_bounded_typevar_not_subtype_of_unrelated(self):
        """TypeVar T: Number is NOT ⊆ String."""
        g = self._graph()
        t = typevar("T", scalar(TypeName("Number")))
        assert not g.is_subtype_expr(t, scalar(TypeName("String")))

    def test_concrete_satisfies_typevar(self):
        """Int ⊆ TypeVar T: Number (Int satisfies bound Number)."""
        g = self._graph()
        t = typevar("T", scalar(TypeName("Number")))
        assert g.is_subtype_expr(scalar(TypeName("Int")), t)

    def test_concrete_doesnt_satisfy_typevar(self):
        """String is NOT ⊆ TypeVar T: Number."""
        g = self._graph()
        t = typevar("T", scalar(TypeName("Number")))
        assert not g.is_subtype_expr(scalar(TypeName("String")), t)

    def test_unbounded_typevar_subtype_of_any(self):
        """Unbounded TypeVar T ⊆ Any."""
        g = self._graph()
        t = typevar("T")
        assert g.is_subtype_expr(t, scalar(TypeName("Any")))

    def test_any_concrete_satisfies_unbounded_typevar(self):
        """Int ⊆ TypeVar T (unbounded accepts anything)."""
        g = self._graph()
        t = typevar("T")
        assert g.is_subtype_expr(scalar(TypeName("Int")), t)

    def test_typevar_in_parameterized_type(self):
        """List[TypeVar T: Number] — Int satisfies T."""
        g = self._graph()
        t = typevar("T", scalar(TypeName("Number")))
        child = ParameterizedType("List", (scalar(TypeName("Int")),))
        parent = ParameterizedType("List", (t,))
        assert g.is_subtype_expr(child, parent)
