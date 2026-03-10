"""Integration tests for Kotlin P0 gap fixes: throw expression, when stmt, anonymous function.

These tests verify end-to-end execution through the VM.
"""

from __future__ import annotations

from tests.unit.rosetta.conftest import execute_for_language, extract_answer


class TestKotlinThrowExpressionExecution:
    """Verify throw-as-expression in elvis executes correctly through VM."""

    def test_elvis_with_non_null_skips_throw(self):
        """When LHS of ?: is non-null, throw should not execute."""
        source = """\
val y: Int = 42
val answer = y ?: throw Exception("err")
"""
        vm, stats = execute_for_language("kotlin", source)
        assert extract_answer(vm, "kotlin") == 42
        assert stats.llm_calls == 0


    def test_elvis_with_null_uses_fallback(self):
        """When LHS of ?: is null, the fallback value should be used."""
        source = """\
var answer = 0
val x: Int? = null
answer = x ?: 42
"""
        vm, stats = execute_for_language("kotlin", source)
        assert extract_answer(vm, "kotlin") == 42
        assert stats.llm_calls == 0


class TestKotlinWhenStatementExecution:
    """Verify when-expression at statement level executes correctly through VM."""

    def test_when_stmt_side_effects(self):
        """when at statement level should execute the matching arm."""
        source = """\
var answer = 0
val x = 2
when(x) {
    1 -> answer = 10
    2 -> answer = 20
    else -> answer = 30
}
"""
        vm, stats = execute_for_language("kotlin", source)
        assert extract_answer(vm, "kotlin") == 20
        assert stats.llm_calls == 0

    def test_when_stmt_else_branch(self):
        """when at statement level should fall through to else."""
        source = """\
var answer = 0
val x = 99
when(x) {
    1 -> answer = 10
    2 -> answer = 20
    else -> answer = 30
}
"""
        vm, stats = execute_for_language("kotlin", source)
        assert extract_answer(vm, "kotlin") == 30
        assert stats.llm_calls == 0


class TestKotlinAnonymousFunctionExecution:
    """Verify anonymous function expressions execute correctly through VM."""

    def test_anonymous_function_called(self):
        """fun(x: Int): Int { return x * 2 } should be callable."""
        source = """\
val f = fun(x: Int): Int { return x * 2 }
val answer = f(21)
"""
        vm, stats = execute_for_language("kotlin", source)
        assert extract_answer(vm, "kotlin") == 42
        assert stats.llm_calls == 0

    def test_anonymous_function_multi_params(self):
        """fun(a: Int, b: Int): Int { return a + b } should handle multiple params."""
        source = """\
val add = fun(a: Int, b: Int): Int { return a + b }
val answer = add(17, 25)
"""
        vm, stats = execute_for_language("kotlin", source)
        assert extract_answer(vm, "kotlin") == 42
        assert stats.llm_calls == 0
