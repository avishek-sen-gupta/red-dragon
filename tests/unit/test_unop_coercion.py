"""Unit tests for UnopCoercionStrategy implementations."""

from interpreter.type_name import TypeName
from interpreter.types.coercion.unop_coercion import DefaultUnopCoercion
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.types.typed_value import TypedValue, typed


class TestDefaultUnopCoercion:
    """DefaultUnopCoercion: no-op coercion, basic result type inference."""

    def setup_method(self):
        self.coercion = DefaultUnopCoercion()

    # --- coerce: no-op ---

    def test_coerce_returns_typed_value(self):
        operand = typed(42, scalar(TypeName("Int")))
        result = self.coercion.coerce("-", operand)
        assert isinstance(result, TypedValue)
        assert result.value == 42
        assert result.type == scalar(TypeName("Int"))

    def test_coerce_passes_through_unchanged(self):
        operand = typed("hello", scalar(TypeName("String")))
        result = self.coercion.coerce("!", operand)
        assert result is operand

    # --- result_type: negation ---

    def test_result_type_negate_int(self):
        operand = typed(5, scalar(TypeName("Int")))
        assert self.coercion.result_type("-", operand) == scalar(TypeName("Int"))

    def test_result_type_negate_float(self):
        operand = typed(3.14, scalar(TypeName("Float")))
        assert self.coercion.result_type("-", operand) == scalar(TypeName("Float"))

    def test_result_type_unary_plus_int(self):
        operand = typed(5, scalar(TypeName("Int")))
        assert self.coercion.result_type("+", operand) == scalar(TypeName("Int"))

    def test_result_type_negate_unknown(self):
        operand = typed("x", UNKNOWN)
        assert self.coercion.result_type("-", operand) == UNKNOWN

    # --- result_type: logical not ---

    def test_result_type_not_returns_bool(self):
        operand = typed(True, scalar(TypeName("Bool")))
        assert self.coercion.result_type("not", operand) == scalar(TypeName("Bool"))

    def test_result_type_bang_returns_bool(self):
        operand = typed(1, scalar(TypeName("Int")))
        assert self.coercion.result_type("!", operand) == scalar(TypeName("Bool"))

    # --- result_type: bitwise not ---

    def test_result_type_bitwise_not_int(self):
        operand = typed(0xFF, scalar(TypeName("Int")))
        assert self.coercion.result_type("~", operand) == scalar(TypeName("Int"))

    def test_result_type_bitwise_not_non_int(self):
        operand = typed(3.14, scalar(TypeName("Float")))
        assert self.coercion.result_type("~", operand) == UNKNOWN

    # --- result_type: length ---

    def test_result_type_length_returns_int(self):
        operand = typed("hello", scalar(TypeName("String")))
        assert self.coercion.result_type("#", operand) == scalar(TypeName("Int"))

    # --- result_type: identity ---

    def test_result_type_double_bang_preserves_type(self):
        operand = typed(42, scalar(TypeName("Int")))
        assert self.coercion.result_type("!!", operand) == scalar(TypeName("Int"))

    # --- result_type: unknown op ---

    def test_result_type_unknown_op(self):
        operand = typed(42, scalar(TypeName("Int")))
        assert self.coercion.result_type("???", operand) == UNKNOWN
