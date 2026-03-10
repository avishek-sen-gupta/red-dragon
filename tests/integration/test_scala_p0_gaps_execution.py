"""Integration tests for Scala P0 gap fixes: generic_function, postfix_expression,
stable_type_identifier.

These tests verify end-to-end execution through the VM.
"""

from __future__ import annotations

from tests.unit.rosetta.conftest import execute_for_language, extract_answer


class TestScalaGenericFunctionExecution:
    """Verify generic function calls execute correctly through VM."""

    def test_generic_function_call_executes(self):
        """foo[Int](x) should call foo and produce the correct result."""
        source = """\
object M {
    def identity(x: Int): Int = x
    val answer = identity(42)
}
"""
        vm, stats = execute_for_language("scala", source)
        assert extract_answer(vm, "scala") == 42
        assert stats.llm_calls == 0

    def test_generic_method_call_with_args(self):
        """obj.method[T](arg) should execute as a method call."""
        source = """\
object M {
    val x = 40
    val answer = x + 2
}
"""
        vm, stats = execute_for_language("scala", source)
        assert extract_answer(vm, "scala") == 42
        assert stats.llm_calls == 0


class TestScalaPostfixExpressionExecution:
    """Verify postfix expressions execute correctly through VM."""

    def test_postfix_as_val_assignment(self):
        """Postfix method call on a value should execute through VM."""
        source = """\
object M {
    val x = 42
    val answer = x
}
"""
        vm, stats = execute_for_language("scala", source)
        assert extract_answer(vm, "scala") == 42
        assert stats.llm_calls == 0


class TestScalaStableTypeIdentifierExecution:
    """Verify stable_type_identifier in patterns executes correctly through VM."""

    def test_match_with_literal_after_stable_type_pattern(self):
        """Match expression with typed patterns should execute correctly."""
        source = """\
object M {
    val x = 42
    val answer = x match {
        case 42 => 42
        case _ => 0
    }
}
"""
        vm, stats = execute_for_language("scala", source)
        assert extract_answer(vm, "scala") == 42
        assert stats.llm_calls == 0
