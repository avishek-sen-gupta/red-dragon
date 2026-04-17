"""Tests for assignment coercion — coerce_assignment on TypeConversionRules."""

import math

from interpreter.constants import FoundationTypeName
from interpreter.types.coercion.conversion_result import _identity
from interpreter.types.coercion.default_conversion_rules import (
    DefaultTypeConversionRules,
)
from interpreter.types.coercion.identity_conversion_rules import IdentityConversionRules
from interpreter.types.null_type_resolver import NullTypeResolver
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.types.type_resolver import TypeResolver


def _rules() -> DefaultTypeConversionRules:
    return DefaultTypeConversionRules()


class TestDefaultAssignmentCoercionNarrowing:
    def test_float_to_int_truncates(self):
        coercer = _rules().coerce_assignment(
            FoundationTypeName.FLOAT, FoundationTypeName.INT
        )
        assert coercer(3.7) == 3

    def test_float_to_int_truncates_negative(self):
        coercer = _rules().coerce_assignment(
            FoundationTypeName.FLOAT, FoundationTypeName.INT
        )
        assert coercer(-3.7) == -3

    def test_float_to_int_truncates_toward_zero(self):
        coercer = _rules().coerce_assignment(
            FoundationTypeName.FLOAT, FoundationTypeName.INT
        )
        assert coercer(-0.5) == 0


class TestDefaultAssignmentCoercionWidening:
    def test_int_to_float_promotes(self):
        coercer = _rules().coerce_assignment(
            FoundationTypeName.INT, FoundationTypeName.FLOAT
        )
        result = coercer(5)
        assert result == 5.0
        assert isinstance(result, float)

    def test_bool_to_int_promotes(self):
        coercer = _rules().coerce_assignment(
            FoundationTypeName.BOOL, FoundationTypeName.INT
        )
        assert coercer(True) == 1
        assert coercer(False) == 0


class TestDefaultAssignmentCoercionSameType:
    def test_int_to_int_is_identity(self):
        coercer = _rules().coerce_assignment(
            FoundationTypeName.INT, FoundationTypeName.INT
        )
        assert coercer(42) == 42

    def test_float_to_float_is_identity(self):
        coercer = _rules().coerce_assignment(
            FoundationTypeName.FLOAT, FoundationTypeName.FLOAT
        )
        assert coercer(3.14) == 3.14

    def test_string_to_string_is_identity(self):
        coercer = _rules().coerce_assignment(
            FoundationTypeName.STRING, FoundationTypeName.STRING
        )
        assert coercer("hello") == "hello"


class TestDefaultAssignmentCoercionFallback:
    def test_unknown_types_return_identity(self):
        coercer = _rules().coerce_assignment("PackedDecimal", FoundationTypeName.INT)
        assert coercer(42) == 42

    def test_string_to_int_returns_identity(self):
        coercer = _rules().coerce_assignment(
            FoundationTypeName.STRING, FoundationTypeName.INT
        )
        assert coercer("hello") == "hello"


class TestIdentityAssignmentCoercion:
    def test_always_returns_identity(self):
        rules = IdentityConversionRules()
        coercer = rules.coerce_assignment(
            FoundationTypeName.FLOAT, FoundationTypeName.INT
        )
        assert coercer(3.7) == 3.7

    def test_returns_identity_function(self):
        rules = IdentityConversionRules()
        coercer = rules.coerce_assignment(
            FoundationTypeName.INT, FoundationTypeName.FLOAT
        )
        assert coercer is _identity


class TestTypeResolverAssignment:
    def test_float_to_int_delegates_to_rules(self):
        resolver = TypeResolver(DefaultTypeConversionRules())
        coercer = resolver.resolve_assignment(
            FoundationTypeName.FLOAT, FoundationTypeName.INT
        )
        assert coercer(3.7) == 3

    def test_both_hints_empty_returns_identity(self):
        resolver = TypeResolver(DefaultTypeConversionRules())
        coercer = resolver.resolve_assignment("", "")
        assert coercer is _identity

    def test_value_hint_empty_returns_identity(self):
        resolver = TypeResolver(DefaultTypeConversionRules())
        coercer = resolver.resolve_assignment("", FoundationTypeName.INT)
        assert coercer is _identity

    def test_target_hint_empty_returns_identity(self):
        resolver = TypeResolver(DefaultTypeConversionRules())
        coercer = resolver.resolve_assignment(FoundationTypeName.FLOAT, "")
        assert coercer is _identity


class TestNullTypeResolverAssignment:
    def test_always_returns_identity(self):
        resolver = NullTypeResolver()
        coercer = resolver.resolve_assignment(
            FoundationTypeName.FLOAT, FoundationTypeName.INT
        )
        assert coercer is _identity

    def test_ignores_hints(self):
        resolver = NullTypeResolver()
        coercer = resolver.resolve_assignment(
            FoundationTypeName.INT, FoundationTypeName.FLOAT
        )
        assert coercer(42) == 42


class TestAssignmentCoercionTypeExpr:
    """coerce_assignment accepts TypeExpr arguments."""

    def test_float_to_int_with_type_expr(self):
        coercer = _rules().coerce_assignment(
            scalar(FoundationTypeName.FLOAT), scalar(FoundationTypeName.INT)
        )
        assert coercer(3.7) == 3

    def test_int_to_float_with_type_expr(self):
        coercer = _rules().coerce_assignment(
            scalar(FoundationTypeName.INT), scalar(FoundationTypeName.FLOAT)
        )
        result = coercer(5)
        assert isinstance(result, float)

    def test_same_type_returns_identity(self):
        coercer = _rules().coerce_assignment(
            scalar(FoundationTypeName.INT), scalar(FoundationTypeName.INT)
        )
        assert coercer(42) == 42

    def test_resolver_with_unknown_returns_identity(self):
        resolver = TypeResolver(DefaultTypeConversionRules())
        coercer = resolver.resolve_assignment(UNKNOWN, scalar(FoundationTypeName.INT))
        assert coercer is _identity
