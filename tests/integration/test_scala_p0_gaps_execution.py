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
        """Calling a function with explicit type argument foo[Int](x) should execute."""
        source = """\
object M {
    def identity(x: Int): Int = x
    val answer = identity[Int](42)
}
"""
        vm, stats = execute_for_language("scala", source)
        assert extract_answer(vm, "scala") == 42
        assert stats.llm_calls == 0


class TestScalaPostfixExpressionExecution:
    """Verify postfix expressions execute correctly through VM."""

    def test_postfix_as_val_assignment(self):
        """Postfix expression (x toString) lowers via CALL_METHOD and executes."""
        source = """\
object M {
    val x = 42
    val answer = x toString
}
"""
        vm, stats = execute_for_language("scala", source)
        # The VM executes the postfix call symbolically; verify it ran without error
        answer = extract_answer(vm, "scala")
        assert answer is not None
        assert stats.llm_calls == 0


class TestScalaStableTypeIdentifierExecution:
    """Verify stable_type_identifier in patterns executes correctly through VM."""

    def test_match_with_literal_after_stable_type_pattern(self):
        """Match with typed pattern (case i: Int) should execute using stable_type_identifier."""
        source = """\
object M {
    val x: Any = 42
    val answer = x match {
        case i: Int => 10
        case _ => 0
    }
}
"""
        vm, stats = execute_for_language("scala", source)
        assert extract_answer(vm, "scala") == 10
        assert stats.llm_calls == 0

    def test_match_wildcard_arm(self):
        """When no literal case matches, the wildcard arm should execute."""
        source = """\
object M {
    val x = 999
    val answer = x match {
        case 42 => 42
        case _ => 0
    }
}
"""
        vm, stats = execute_for_language("scala", source)
        assert extract_answer(vm, "scala") == 0
        assert stats.llm_calls == 0
