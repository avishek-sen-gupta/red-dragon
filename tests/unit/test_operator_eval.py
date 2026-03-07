"""Tests for Operators.eval_binop and eval_unop — verifying UNCOMPUTABLE on type errors."""

from interpreter.vm import Operators
from interpreter.vm_types import SymbolicValue

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


class TestEvalBinopTypeErrors:
    """eval_binop returns UNCOMPUTABLE when operands have incompatible types."""

    def test_subtract_string_from_int(self):
        assert Operators.eval_binop("-", "hello", 3) is _UNCOMPUTABLE

    def test_add_string_and_int(self):
        assert Operators.eval_binop("+", "hello", 3) is _UNCOMPUTABLE

    def test_multiply_string_by_string(self):
        assert Operators.eval_binop("*", "a", "b") is _UNCOMPUTABLE

    def test_less_than_incompatible_types(self):
        assert Operators.eval_binop("<", "abc", 5) is _UNCOMPUTABLE

    def test_bitwise_and_on_strings(self):
        assert Operators.eval_binop("&", "x", "y") is _UNCOMPUTABLE

    def test_shift_on_float(self):
        assert Operators.eval_binop("<<", 1.5, 2) is _UNCOMPUTABLE

    def test_symbolic_lhs(self):
        sym = SymbolicValue(name="unknown")
        assert Operators.eval_binop("+", sym, 1) is _UNCOMPUTABLE

    def test_symbolic_rhs(self):
        sym = SymbolicValue(name="unknown")
        assert Operators.eval_binop("*", 5, sym) is _UNCOMPUTABLE


class TestEvalBinopUnknownOp:
    """eval_binop returns UNCOMPUTABLE for unrecognised operators."""

    def test_unknown_operator(self):
        assert Operators.eval_binop("???", 1, 2) is _UNCOMPUTABLE


class TestEvalBinopHappyPath:
    """eval_binop computes correct results for compatible operands."""

    def test_add_ints(self):
        assert Operators.eval_binop("+", 3, 4) == 7

    def test_divide_ints(self):
        assert Operators.eval_binop("/", 10, 3) == 10 / 3

    def test_divide_by_zero(self):
        assert Operators.eval_binop("/", 5, 0) is _UNCOMPUTABLE

    def test_floor_divide_by_zero(self):
        assert Operators.eval_binop("//", 5, 0) is _UNCOMPUTABLE

    def test_modulo(self):
        assert Operators.eval_binop("%", 10, 3) == 1

    def test_equality(self):
        assert Operators.eval_binop("==", 5, 5) is True

    def test_concatenation_dot_dot(self):
        assert Operators.eval_binop("..", "foo", "bar") == "foobar"

    def test_string_addition(self):
        assert Operators.eval_binop("+", "hello ", "world") == "hello world"


class TestEvalUnopTypeErrors:
    """eval_unop returns UNCOMPUTABLE when operand type is incompatible."""

    def test_negate_string(self):
        assert Operators.eval_unop("-", "hello") is _UNCOMPUTABLE

    def test_bitwise_not_string(self):
        assert Operators.eval_unop("~", "hello") is _UNCOMPUTABLE

    def test_length_of_int(self):
        assert Operators.eval_unop("#", 42) is _UNCOMPUTABLE

    def test_negate_symbolic(self):
        sym = SymbolicValue(name="unknown")
        assert Operators.eval_unop("-", sym) is _UNCOMPUTABLE

    def test_bitwise_not_symbolic(self):
        sym = SymbolicValue(name="unknown")
        assert Operators.eval_unop("~", sym) is _UNCOMPUTABLE


class TestEvalUnopUnknownOp:
    """eval_unop returns UNCOMPUTABLE for unrecognised operators."""

    def test_unknown_operator(self):
        assert Operators.eval_unop("???", 42) is _UNCOMPUTABLE


class TestEvalUnopHappyPath:
    """eval_unop computes correct results for compatible operands."""

    def test_negate_int(self):
        assert Operators.eval_unop("-", 5) == -5

    def test_positive_int(self):
        assert Operators.eval_unop("+", -3) == -3

    def test_not_true(self):
        assert Operators.eval_unop("not", True) is False

    def test_not_false(self):
        assert Operators.eval_unop("not", False) is True

    def test_bang_true(self):
        assert Operators.eval_unop("!", True) is False

    def test_bitwise_not_int(self):
        assert Operators.eval_unop("~", 0) == -1

    def test_length_of_list(self):
        assert Operators.eval_unop("#", [1, 2, 3]) == 3

    def test_double_bang_passthrough(self):
        assert Operators.eval_unop("!!", 42) == 42
