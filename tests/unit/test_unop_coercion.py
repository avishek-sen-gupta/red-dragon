"""Unit tests for UnopCoercionStrategy implementations."""

from interpreter.type_expr import UNKNOWN, scalar
from interpreter.typed_value import TypedValue, typed
from interpreter.unop_coercion import DefaultUnopCoercion


class TestDefaultUnopCoercion:
    """DefaultUnopCoercion: no-op coercion, basic result type inference."""

    def setup_method(self):
        self.coercion = DefaultUnopCoercion()

    # --- coerce: no-op ---

    def test_coerce_returns_typed_value(self):
        operand = typed(42, scalar("Int"))
        result = self.coercion.coerce("-", operand)
        assert isinstance(result, TypedValue)
        assert result.value == 42
        assert result.type == scalar("Int")

    def test_coerce_passes_through_unchanged(self):
        operand = typed("hello", scalar("String"))
        result = self.coercion.coerce("!", operand)
        assert result is operand

    # --- result_type: negation ---

    def test_result_type_negate_int(self):
        operand = typed(5, scalar("Int"))
        assert self.coercion.result_type("-", operand) == scalar("Int")

    def test_result_type_negate_float(self):
        operand = typed(3.14, scalar("Float"))
        assert self.coercion.result_type("-", operand) == scalar("Float")

    def test_result_type_unary_plus_int(self):
        operand = typed(5, scalar("Int"))
        assert self.coercion.result_type("+", operand) == scalar("Int")

    def test_result_type_negate_unknown(self):
        operand = typed("x", UNKNOWN)
        assert self.coercion.result_type("-", operand) == UNKNOWN

    # --- result_type: logical not ---

    def test_result_type_not_returns_bool(self):
        operand = typed(True, scalar("Bool"))
        assert self.coercion.result_type("not", operand) == scalar("Bool")

    def test_result_type_bang_returns_bool(self):
        operand = typed(1, scalar("Int"))
        assert self.coercion.result_type("!", operand) == scalar("Bool")

    # --- result_type: bitwise not ---

    def test_result_type_bitwise_not_int(self):
        operand = typed(0xFF, scalar("Int"))
        assert self.coercion.result_type("~", operand) == scalar("Int")

    def test_result_type_bitwise_not_non_int(self):
        operand = typed(3.14, scalar("Float"))
        assert self.coercion.result_type("~", operand) == UNKNOWN

    # --- result_type: length ---

    def test_result_type_length_returns_int(self):
        operand = typed("hello", scalar("String"))
        assert self.coercion.result_type("#", operand) == scalar("Int")

    # --- result_type: identity ---

    def test_result_type_double_bang_preserves_type(self):
        operand = typed(42, scalar("Int"))
        assert self.coercion.result_type("!!", operand) == scalar("Int")

    # --- result_type: unknown op ---

    def test_result_type_unknown_op(self):
        operand = typed(42, scalar("Int"))
        assert self.coercion.result_type("???", operand) == UNKNOWN
