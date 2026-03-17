"""Unit tests for BinopCoercionStrategy implementations."""

from interpreter.binop_coercion import (
    DefaultBinopCoercion,
    JavaBinopCoercion,
    _java_stringify,
)
from interpreter.type_expr import UNKNOWN, scalar
from interpreter.typed_value import TypedValue, typed


class TestDefaultBinopCoercion:
    """DefaultBinopCoercion: no-op coercion, basic result type inference."""

    def setup_method(self):
        self.coercion = DefaultBinopCoercion()

    # --- coerce: no-op ---

    def test_coerce_returns_typed_values(self):
        lhs = typed(42, scalar("Int"))
        rhs = typed(3, scalar("Int"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert isinstance(a, TypedValue)
        assert isinstance(b, TypedValue)
        assert a.value == 42
        assert b.value == 3
        assert a.type == scalar("Int")
        assert b.type == scalar("Int")

    def test_coerce_string_plus_int_no_coercion(self):
        lhs = typed("hello", scalar("String"))
        rhs = typed(42, scalar("Int"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a.value == "hello"
        assert b.value == 42

    # --- result_type ---

    def test_result_type_int_plus_int(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2, scalar("Int"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("Int")

    def test_result_type_float_plus_float(self):
        lhs = typed(1.0, scalar("Float"))
        rhs = typed(2.0, scalar("Float"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("Float")

    def test_result_type_int_plus_float(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2.0, scalar("Float"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("Float")

    def test_result_type_string_plus_string(self):
        lhs = typed("a", scalar("String"))
        rhs = typed("b", scalar("String"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("String")

    def test_result_type_comparison_returns_bool(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2, scalar("Int"))
        for op in ("==", "!=", "<", ">", "<=", ">="):
            assert self.coercion.result_type(op, lhs, rhs) == scalar("Bool")

    def test_result_type_c_family_logical_returns_bool(self):
        lhs = typed(True, scalar("Bool"))
        rhs = typed(False, scalar("Bool"))
        assert self.coercion.result_type("&&", lhs, rhs) == scalar("Bool")
        assert self.coercion.result_type("||", lhs, rhs) == scalar("Bool")

    def test_result_type_python_and_or_returns_unknown(self):
        lhs = typed(3, scalar("Int"))
        rhs = typed(5, scalar("Int"))
        assert self.coercion.result_type("and", lhs, rhs) == UNKNOWN
        assert self.coercion.result_type("or", lhs, rhs) == UNKNOWN

    def test_result_type_concat_returns_string(self):
        lhs = typed("a", scalar("String"))
        rhs = typed("b", scalar("String"))
        assert self.coercion.result_type("..", lhs, rhs) == scalar("String")
        assert self.coercion.result_type(".", lhs, rhs) == scalar("String")

    def test_result_type_unknown_op(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2, scalar("Int"))
        assert self.coercion.result_type("???", lhs, rhs) == UNKNOWN

    def test_result_type_int_minus_int(self):
        lhs = typed(5, scalar("Int"))
        rhs = typed(3, scalar("Int"))
        assert self.coercion.result_type("-", lhs, rhs) == scalar("Int")

    def test_result_type_int_times_float(self):
        lhs = typed(2, scalar("Int"))
        rhs = typed(3.0, scalar("Float"))
        assert self.coercion.result_type("*", lhs, rhs) == scalar("Float")

    def test_result_type_unknown_operand_types(self):
        lhs = typed(42, UNKNOWN)
        rhs = typed(3, UNKNOWN)
        assert self.coercion.result_type("+", lhs, rhs) == UNKNOWN


class TestJavaBinopCoercion:
    """JavaBinopCoercion: string concatenation coercion."""

    def setup_method(self):
        self.coercion = JavaBinopCoercion()

    # --- coerce: string + non-string ---

    def test_coerce_string_plus_int_stringifies_int(self):
        lhs = typed("int:", scalar("String"))
        rhs = typed(42, scalar("Int"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a.value == "int:"
        assert b.value == "42"
        assert b.type == scalar("String")

    def test_coerce_int_plus_string_stringifies_int(self):
        lhs = typed(42, scalar("Int"))
        rhs = typed(" items", scalar("String"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a.value == "42"
        assert a.type == scalar("String")
        assert b.value == " items"

    def test_coerce_string_plus_float_stringifies_float(self):
        lhs = typed("val:", scalar("String"))
        rhs = typed(3.14, scalar("Float"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a.value == "val:"
        assert b.value == "3.14"
        assert b.type == scalar("String")

    def test_coerce_string_plus_bool_stringifies_bool(self):
        lhs = typed("flag:", scalar("String"))
        rhs = typed(True, scalar("Bool"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a.value == "flag:"
        assert b.value == "true"
        assert b.type == scalar("String")

    def test_coerce_string_plus_string_no_change(self):
        lhs = typed("hello", scalar("String"))
        rhs = typed(" world", scalar("String"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a.value == "hello"
        assert b.value == " world"

    def test_coerce_non_plus_op_no_change(self):
        lhs = typed("hello", scalar("String"))
        rhs = typed(42, scalar("Int"))
        a, b = self.coercion.coerce("-", lhs, rhs)
        assert a.value == "hello"
        assert b.value == 42

    def test_coerce_int_plus_int_no_change(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2, scalar("Int"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a.value == 1
        assert b.value == 2

    # --- result_type: string concat ---

    def test_result_type_string_plus_int(self):
        lhs = typed("x", scalar("String"))
        rhs = typed(42, scalar("Int"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("String")

    def test_result_type_int_plus_string(self):
        lhs = typed(42, scalar("Int"))
        rhs = typed("x", scalar("String"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("String")

    def test_result_type_int_plus_int_delegates_to_default(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2, scalar("Int"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("Int")

    def test_result_type_comparison_delegates_to_default(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2, scalar("Int"))
        assert self.coercion.result_type("==", lhs, rhs) == scalar("Bool")


class TestJavaStringify:
    """Unit tests for _java_stringify boolean and non-boolean conversion."""

    def test_true_is_lowercase(self):
        assert _java_stringify(True) == "true"

    def test_false_is_lowercase(self):
        assert _java_stringify(False) == "false"

    def test_int_unchanged(self):
        assert _java_stringify(42) == "42"

    def test_float_unchanged(self):
        assert _java_stringify(3.14) == "3.14"

    def test_string_unchanged(self):
        assert _java_stringify("hello") == "hello"

    def test_zero_is_not_boolean(self):
        assert _java_stringify(0) == "0"

    def test_one_is_not_boolean(self):
        assert _java_stringify(1) == "1"

    def test_none_unchanged(self):
        assert _java_stringify(None) == "None"
