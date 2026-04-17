"""Tests for TypeConversionRules — DefaultTypeConversionRules and IdentityConversionRules."""

from interpreter.constants import FoundationTypeName
from interpreter.types.coercion.conversion_result import IDENTITY_CONVERSION
from interpreter.types.coercion.default_conversion_rules import (
    DefaultTypeConversionRules,
)
from interpreter.types.coercion.identity_conversion_rules import IdentityConversionRules
from interpreter.types.type_expr import ScalarType, TypeExpr, UNKNOWN, scalar


def _rules() -> DefaultTypeConversionRules:
    return DefaultTypeConversionRules()


class TestDefaultTypeConversionRulesArithmetic:
    def test_int_plus_int_yields_int(self):
        result = _rules().resolve("+", FoundationTypeName.INT, FoundationTypeName.INT)
        assert result.result_type == FoundationTypeName.INT
        assert result.operator_override == ""

    def test_int_plus_float_yields_float_with_left_coercion(self):
        result = _rules().resolve("+", FoundationTypeName.INT, FoundationTypeName.FLOAT)
        assert result.result_type == FoundationTypeName.FLOAT
        assert result.left_coercer(3) == 3.0
        assert isinstance(result.left_coercer(3), float)

    def test_float_plus_int_yields_float_with_right_coercion(self):
        result = _rules().resolve("+", FoundationTypeName.FLOAT, FoundationTypeName.INT)
        assert result.result_type == FoundationTypeName.FLOAT
        assert result.right_coercer(3) == 3.0
        assert isinstance(result.right_coercer(3), float)

    def test_int_div_int_yields_int_with_floor_div_override(self):
        result = _rules().resolve("/", FoundationTypeName.INT, FoundationTypeName.INT)
        assert result.result_type == FoundationTypeName.INT
        assert result.operator_override == "//"

    def test_int_div_float_yields_float(self):
        result = _rules().resolve("/", FoundationTypeName.INT, FoundationTypeName.FLOAT)
        assert result.result_type == FoundationTypeName.FLOAT
        assert result.operator_override == ""

    def test_float_div_int_yields_float(self):
        result = _rules().resolve("/", FoundationTypeName.FLOAT, FoundationTypeName.INT)
        assert result.result_type == FoundationTypeName.FLOAT
        assert result.operator_override == ""

    def test_int_mod_int_yields_int(self):
        result = _rules().resolve("%", FoundationTypeName.INT, FoundationTypeName.INT)
        assert result.result_type == FoundationTypeName.INT

    def test_int_minus_float_yields_float(self):
        result = _rules().resolve("-", FoundationTypeName.INT, FoundationTypeName.FLOAT)
        assert result.result_type == FoundationTypeName.FLOAT

    def test_int_times_float_yields_float(self):
        result = _rules().resolve("*", FoundationTypeName.INT, FoundationTypeName.FLOAT)
        assert result.result_type == FoundationTypeName.FLOAT


class TestDefaultTypeConversionRulesComparison:
    def test_int_eq_int_yields_bool(self):
        result = _rules().resolve("==", FoundationTypeName.INT, FoundationTypeName.INT)
        assert result.result_type == FoundationTypeName.BOOL

    def test_float_lt_int_yields_bool(self):
        result = _rules().resolve("<", FoundationTypeName.FLOAT, FoundationTypeName.INT)
        assert result.result_type == FoundationTypeName.BOOL

    def test_string_eq_string_yields_bool(self):
        result = _rules().resolve(
            "==", FoundationTypeName.STRING, FoundationTypeName.STRING
        )
        assert result.result_type == FoundationTypeName.BOOL


class TestDefaultTypeConversionRulesBoolPromotion:
    def test_bool_plus_int_coerces_bool_to_int(self):
        result = _rules().resolve("+", FoundationTypeName.BOOL, FoundationTypeName.INT)
        assert result.result_type == FoundationTypeName.INT
        assert result.left_coercer(True) == 1

    def test_int_plus_bool_coerces_bool_to_int(self):
        result = _rules().resolve("+", FoundationTypeName.INT, FoundationTypeName.BOOL)
        assert result.result_type == FoundationTypeName.INT
        assert result.right_coercer(False) == 0


class TestDefaultTypeConversionRulesFallback:
    def test_unknown_types_return_identity_coercers(self):
        result = _rules().resolve("+", "PackedDecimal", "PackedDecimal")
        assert result.left_coercer(42) == 42
        assert result.right_coercer(42) == 42
        assert result.operator_override == ""

    def test_string_plus_string_returns_identity(self):
        result = _rules().resolve(
            "+", FoundationTypeName.STRING, FoundationTypeName.STRING
        )
        assert result.left_coercer("hello") == "hello"
        assert result.operator_override == ""


class TestIdentityConversionRules:
    def test_always_returns_identity_coercers(self):
        rules = IdentityConversionRules()
        result = rules.resolve("+", FoundationTypeName.INT, FoundationTypeName.FLOAT)
        assert result.left_coercer(42) == 42
        assert result.right_coercer(3.14) == 3.14

    def test_no_operator_override(self):
        rules = IdentityConversionRules()
        result = rules.resolve("/", FoundationTypeName.INT, FoundationTypeName.INT)
        assert result.operator_override == ""

    def test_empty_result_type(self):
        rules = IdentityConversionRules()
        result = rules.resolve("*", FoundationTypeName.FLOAT, FoundationTypeName.INT)
        assert result.result_type == ""

    def test_returns_identity_conversion_singleton(self):
        rules = IdentityConversionRules()
        result = rules.resolve("+", FoundationTypeName.INT, FoundationTypeName.INT)
        assert result is IDENTITY_CONVERSION


class TestConversionResultTypeExpr:
    """ConversionResult.result_type should be TypeExpr, not str."""

    def test_arithmetic_result_type_is_type_expr(self):
        result = _rules().resolve(
            "+", scalar(FoundationTypeName.INT), scalar(FoundationTypeName.INT)
        )
        assert isinstance(result.result_type, TypeExpr)
        assert isinstance(result.result_type, ScalarType)

    def test_comparison_result_type_is_type_expr(self):
        result = _rules().resolve(
            "==", scalar(FoundationTypeName.INT), scalar(FoundationTypeName.FLOAT)
        )
        assert isinstance(result.result_type, ScalarType)
        assert result.result_type == FoundationTypeName.BOOL

    def test_identity_conversion_result_type_is_unknown(self):
        assert IDENTITY_CONVERSION.result_type is UNKNOWN
        assert not IDENTITY_CONVERSION.result_type

    def test_accepts_type_expr_arguments(self):
        """resolve() should accept TypeExpr objects, not just strings."""
        result = _rules().resolve(
            "+", scalar(FoundationTypeName.INT), scalar(FoundationTypeName.FLOAT)
        )
        assert result.result_type == FoundationTypeName.FLOAT
        assert isinstance(result.left_coercer(3), float)

    def test_division_with_type_expr_returns_type_expr(self):
        result = _rules().resolve(
            "/", scalar(FoundationTypeName.INT), scalar(FoundationTypeName.INT)
        )
        assert isinstance(result.result_type, ScalarType)
        assert result.result_type == FoundationTypeName.INT
        assert result.operator_override == "//"

    def test_modulo_with_type_expr_returns_type_expr(self):
        result = _rules().resolve(
            "%", scalar(FoundationTypeName.INT), scalar(FoundationTypeName.INT)
        )
        assert isinstance(result.result_type, ScalarType)

    def test_bool_promotion_with_type_expr(self):
        result = _rules().resolve(
            "+", scalar(FoundationTypeName.BOOL), scalar(FoundationTypeName.INT)
        )
        assert isinstance(result.result_type, ScalarType)
        assert result.result_type == FoundationTypeName.INT
