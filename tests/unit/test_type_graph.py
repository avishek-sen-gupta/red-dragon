"""Tests for TypeGraph — DAG with subtype queries and LUB."""

from interpreter.type_node import TypeNode
from interpreter.type_graph import TypeGraph, DEFAULT_TYPE_NODES
from interpreter.constants import TypeName
from interpreter.type_expr import (
    ScalarType,
    ParameterizedType,
    scalar,
    pointer,
    array_of,
    map_of,
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
