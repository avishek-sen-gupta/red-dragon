"""Tests for TypeGraph — DAG with subtype queries and LUB."""

from interpreter.type_node import TypeNode
from interpreter.type_graph import TypeGraph, DEFAULT_TYPE_NODES
from interpreter.constants import TypeName


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
