"""Tests for TypeResolver and NullTypeResolver."""

from interpreter.constants import TypeName
from interpreter.conversion_result import IDENTITY_CONVERSION
from interpreter.default_conversion_rules import DefaultConversionRules
from interpreter.null_type_resolver import NullTypeResolver
from interpreter.type_resolver import TypeResolver


def _resolver() -> TypeResolver:
    return TypeResolver(DefaultConversionRules())


class TestTypeResolverWithHints:
    def test_int_plus_float_delegates_to_rules(self):
        result = _resolver().resolve_binop("+", TypeName.INT, TypeName.FLOAT)
        assert result.result_type == TypeName.FLOAT

    def test_int_div_int_returns_floor_div_override(self):
        result = _resolver().resolve_binop("/", TypeName.INT, TypeName.INT)
        assert result.operator_override == "//"
        assert result.result_type == TypeName.INT

    def test_comparison_returns_bool_type(self):
        result = _resolver().resolve_binop("==", TypeName.INT, TypeName.FLOAT)
        assert result.result_type == TypeName.BOOL


class TestTypeResolverWithoutHints:
    def test_both_empty_returns_identity(self):
        result = _resolver().resolve_binop("+", "", "")
        assert result is IDENTITY_CONVERSION

    def test_no_operator_override_when_no_hints(self):
        result = _resolver().resolve_binop("/", "", "")
        assert result.operator_override == ""

    def test_identity_coercers_when_no_hints(self):
        result = _resolver().resolve_binop("+", "", "")
        assert result.left_coercer(42) == 42
        assert result.right_coercer(3.14) == 3.14


class TestTypeResolverPartialHints:
    def test_left_hint_only_assumes_symmetric(self):
        result = _resolver().resolve_binop("/", TypeName.INT, "")
        assert result.operator_override == "//"
        assert result.result_type == TypeName.INT

    def test_right_hint_only_assumes_symmetric(self):
        result = _resolver().resolve_binop("/", "", TypeName.INT)
        assert result.operator_override == "//"
        assert result.result_type == TypeName.INT


class TestTypeResolverWithIdentityRules:
    def test_always_returns_identity_regardless_of_hints(self):
        from interpreter.identity_conversion_rules import IdentityConversionRules

        resolver = TypeResolver(IdentityConversionRules())
        result = resolver.resolve_binop("/", TypeName.INT, TypeName.INT)
        assert result is IDENTITY_CONVERSION


class TestNullTypeResolver:
    def test_always_returns_identity_conversion(self):
        resolver = NullTypeResolver()
        result = resolver.resolve_binop("+", TypeName.INT, TypeName.FLOAT)
        assert result is IDENTITY_CONVERSION

    def test_ignores_type_hints_entirely(self):
        resolver = NullTypeResolver()
        result = resolver.resolve_binop("/", TypeName.INT, TypeName.INT)
        assert result.operator_override == ""

    def test_no_operator_override(self):
        resolver = NullTypeResolver()
        result = resolver.resolve_binop("/", TypeName.FLOAT, TypeName.INT)
        assert result.operator_override == ""
