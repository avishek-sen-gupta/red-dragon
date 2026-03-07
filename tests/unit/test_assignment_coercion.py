"""Tests for assignment coercion — coerce_assignment on TypeConversionRules."""

import math

from interpreter.constants import TypeName
from interpreter.conversion_result import _identity
from interpreter.default_conversion_rules import DefaultConversionRules
from interpreter.identity_conversion_rules import IdentityConversionRules
from interpreter.null_type_resolver import NullTypeResolver
from interpreter.type_resolver import TypeResolver


def _rules() -> DefaultConversionRules:
    return DefaultConversionRules()


class TestDefaultAssignmentCoercionNarrowing:
    def test_float_to_int_truncates(self):
        coercer = _rules().coerce_assignment(TypeName.FLOAT, TypeName.INT)
        assert coercer(3.7) == 3

    def test_float_to_int_truncates_negative(self):
        coercer = _rules().coerce_assignment(TypeName.FLOAT, TypeName.INT)
        assert coercer(-3.7) == -3

    def test_float_to_int_truncates_toward_zero(self):
        coercer = _rules().coerce_assignment(TypeName.FLOAT, TypeName.INT)
        assert coercer(-0.5) == 0


class TestDefaultAssignmentCoercionWidening:
    def test_int_to_float_promotes(self):
        coercer = _rules().coerce_assignment(TypeName.INT, TypeName.FLOAT)
        result = coercer(5)
        assert result == 5.0
        assert isinstance(result, float)

    def test_bool_to_int_promotes(self):
        coercer = _rules().coerce_assignment(TypeName.BOOL, TypeName.INT)
        assert coercer(True) == 1
        assert coercer(False) == 0


class TestDefaultAssignmentCoercionSameType:
    def test_int_to_int_is_identity(self):
        coercer = _rules().coerce_assignment(TypeName.INT, TypeName.INT)
        assert coercer(42) == 42

    def test_float_to_float_is_identity(self):
        coercer = _rules().coerce_assignment(TypeName.FLOAT, TypeName.FLOAT)
        assert coercer(3.14) == 3.14

    def test_string_to_string_is_identity(self):
        coercer = _rules().coerce_assignment(TypeName.STRING, TypeName.STRING)
        assert coercer("hello") == "hello"


class TestDefaultAssignmentCoercionFallback:
    def test_unknown_types_return_identity(self):
        coercer = _rules().coerce_assignment("PackedDecimal", TypeName.INT)
        assert coercer(42) == 42

    def test_string_to_int_returns_identity(self):
        coercer = _rules().coerce_assignment(TypeName.STRING, TypeName.INT)
        assert coercer("hello") == "hello"


class TestIdentityAssignmentCoercion:
    def test_always_returns_identity(self):
        rules = IdentityConversionRules()
        coercer = rules.coerce_assignment(TypeName.FLOAT, TypeName.INT)
        assert coercer(3.7) == 3.7

    def test_returns_identity_function(self):
        rules = IdentityConversionRules()
        coercer = rules.coerce_assignment(TypeName.INT, TypeName.FLOAT)
        assert coercer is _identity


class TestTypeResolverAssignment:
    def test_float_to_int_delegates_to_rules(self):
        resolver = TypeResolver(DefaultConversionRules())
        coercer = resolver.resolve_assignment(TypeName.FLOAT, TypeName.INT)
        assert coercer(3.7) == 3

    def test_both_hints_empty_returns_identity(self):
        resolver = TypeResolver(DefaultConversionRules())
        coercer = resolver.resolve_assignment("", "")
        assert coercer is _identity

    def test_value_hint_empty_returns_identity(self):
        resolver = TypeResolver(DefaultConversionRules())
        coercer = resolver.resolve_assignment("", TypeName.INT)
        assert coercer is _identity

    def test_target_hint_empty_returns_identity(self):
        resolver = TypeResolver(DefaultConversionRules())
        coercer = resolver.resolve_assignment(TypeName.FLOAT, "")
        assert coercer is _identity


class TestNullTypeResolverAssignment:
    def test_always_returns_identity(self):
        resolver = NullTypeResolver()
        coercer = resolver.resolve_assignment(TypeName.FLOAT, TypeName.INT)
        assert coercer is _identity

    def test_ignores_hints(self):
        resolver = NullTypeResolver()
        coercer = resolver.resolve_assignment(TypeName.INT, TypeName.FLOAT)
        assert coercer(42) == 42
