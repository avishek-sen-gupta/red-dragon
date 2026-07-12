"""Unit tests for TypeCompatibility — runtime arg vs declared type scoring."""

from interpreter.constants import FoundationTypeName
from interpreter.type_name import TypeName
from interpreter.types.coercion.type_compatibility import DefaultTypeCompatibility
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.types.type_graph import DEFAULT_TYPE_NODES, TypeGraph
from interpreter.types.type_node import TypeNode
from interpreter.types.typed_value import typed


def _default_graph() -> TypeGraph:
    return TypeGraph(DEFAULT_TYPE_NODES)


def _graph_with_classes() -> TypeGraph:
    class_nodes = (
        TypeNode(name=TypeName("Animal"), parents=(TypeName("Any"),)),
        TypeNode(name=TypeName("Dog"), parents=(TypeName("Animal"),)),
        TypeNode(name=TypeName("Cat"), parents=(TypeName("Animal"),)),
    )
    return TypeGraph(DEFAULT_TYPE_NODES + class_nodes)


class TestDefaultTypeCompatibilityTypedValue:
    """Tests using TypedValue args and TypeGraph injection."""

    def setup_method(self):
        self.compat = DefaultTypeCompatibility(_default_graph())

    # -- Exact matches (score 2) --

    def test_int_matches_int(self):
        assert (
            self.compat.score(
                typed(42, scalar(FoundationTypeName.INT)),
                scalar(FoundationTypeName.INT),
            )
            == 2
        )

    def test_float_matches_float(self):
        assert (
            self.compat.score(
                typed(3.14, scalar(FoundationTypeName.FLOAT)),
                scalar(FoundationTypeName.FLOAT),
            )
            == 2
        )

    def test_string_matches_string(self):
        assert (
            self.compat.score(
                typed("hello", scalar(FoundationTypeName.STRING)),
                scalar(FoundationTypeName.STRING),
            )
            == 2
        )

    def test_bool_matches_bool(self):
        assert (
            self.compat.score(
                typed(True, scalar(FoundationTypeName.BOOL)),
                scalar(FoundationTypeName.BOOL),
            )
            == 2
        )

    # -- Coercion pairs (score 1) --

    def test_int_compatible_with_float(self):
        assert (
            self.compat.score(
                typed(42, scalar(FoundationTypeName.INT)),
                scalar(FoundationTypeName.FLOAT),
            )
            == 1
        )

    def test_float_compatible_with_int(self):
        assert (
            self.compat.score(
                typed(3.14, scalar(FoundationTypeName.FLOAT)),
                scalar(FoundationTypeName.INT),
            )
            == 1
        )

    def test_bool_compatible_with_int(self):
        assert (
            self.compat.score(
                typed(True, scalar(FoundationTypeName.BOOL)),
                scalar(FoundationTypeName.INT),
            )
            == 1
        )

    # -- Neutral (score 0) --

    def test_unknown_arg_type_is_neutral(self):
        assert (
            self.compat.score(
                typed("obj_0", UNKNOWN), scalar(FoundationTypeName.STRING)
            )
            == 0
        )

    def test_unknown_declared_type_is_neutral(self):
        assert (
            self.compat.score(typed(42, scalar(FoundationTypeName.INT)), UNKNOWN) == 0
        )

    def test_none_with_unknown_type_is_neutral(self):
        assert (
            self.compat.score(typed(None, UNKNOWN), scalar(FoundationTypeName.INT)) == 0
        )

    # -- Mismatches (score -1) --

    def test_string_mismatches_int(self):
        assert (
            self.compat.score(
                typed("hello", scalar(FoundationTypeName.STRING)),
                scalar(FoundationTypeName.INT),
            )
            == -1
        )

    def test_int_mismatches_string(self):
        assert (
            self.compat.score(
                typed(42, scalar(FoundationTypeName.INT)),
                scalar(FoundationTypeName.STRING),
            )
            == -1
        )

    def test_float_mismatches_string(self):
        assert (
            self.compat.score(
                typed(3.14, scalar(FoundationTypeName.FLOAT)),
                scalar(FoundationTypeName.STRING),
            )
            == -1
        )

    def test_list_with_unknown_type_is_neutral(self):
        assert (
            self.compat.score(typed([1, 2], UNKNOWN), scalar(FoundationTypeName.ARRAY))
            == 0
        )


class TestSubtypeScoring:
    """Tests for subtype-aware scoring with class hierarchies."""

    def setup_method(self):
        self.compat = DefaultTypeCompatibility(_graph_with_classes())

    def test_exact_class_match(self):
        assert (
            self.compat.score(
                typed("obj_0", scalar(TypeName("Dog"))), scalar(TypeName("Dog"))
            )
            == 2
        )

    def test_subtype_match(self):
        assert (
            self.compat.score(
                typed("obj_0", scalar(TypeName("Dog"))), scalar(TypeName("Animal"))
            )
            == 1
        )

    def test_transitive_subtype(self):
        assert (
            self.compat.score(
                typed("obj_0", scalar(TypeName("Dog"))), scalar(TypeName("Any"))
            )
            == 1
        )

    def test_unrelated_class_mismatch(self):
        assert (
            self.compat.score(
                typed("obj_0", scalar(TypeName("Dog"))), scalar(TypeName("Cat"))
            )
            == -1
        )

    def test_sibling_classes_mismatch(self):
        assert (
            self.compat.score(
                typed("obj_0", scalar(TypeName("Cat"))), scalar(TypeName("Dog"))
            )
            == -1
        )

    def test_heap_address_with_class_type_not_confused_with_string(self):
        """obj_0 is a heap address string, but typed as Dog — should not match String."""
        assert (
            self.compat.score(
                typed("obj_0", scalar(TypeName("Dog"))),
                scalar(FoundationTypeName.STRING),
            )
            == -1
        )
