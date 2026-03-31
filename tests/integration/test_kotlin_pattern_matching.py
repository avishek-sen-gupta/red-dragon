"""Integration tests for Kotlin when pattern matching — end-to-end execution."""

from __future__ import annotations

import pytest

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint


def _run_kotlin(source: str, max_steps: int = 500):
    """Run a Kotlin program and return frame.local_vars."""
    vm = run(
        source,
        language=Language.KOTLIN,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestKotlinWhenLiteralMatch:
    """when expression matching on integer literals."""

    def test_literal_match_hits_first_arm(self):
        """when(x) { 1 -> 10; else -> 0 } should return 10 when x == 1."""
        source = """\
val x = 1
val r = when(x) {
    1 -> 10
    else -> 0
}
"""
        local_vars = _run_kotlin(source)
        assert local_vars[VarName("r")] == 10

    def test_else_fallthrough_when_no_match(self):
        """when(x) { 1 -> 10; else -> 0 } should return 0 when x == 5."""
        source = """\
val x = 5
val r = when(x) {
    1 -> 10
    else -> 0
}
"""
        local_vars = _run_kotlin(source)
        assert local_vars[VarName("r")] == 0

    def test_multiple_literals_selects_correct_arm(self):
        """when(x) { 1 -> 10; 2 -> 20; else -> 0 } should return 20 when x == 2."""
        source = """\
val x = 2
val r = when(x) {
    1 -> 10
    2 -> 20
    else -> 0
}
"""
        local_vars = _run_kotlin(source)
        assert local_vars[VarName("r")] == 20

    def test_three_literal_arms_selects_third(self):
        """when(x) with three arms should return 30 when x == 3."""
        source = """\
val x = 3
val r = when(x) {
    1 -> 10
    2 -> 20
    3 -> 30
    else -> 0
}
"""
        local_vars = _run_kotlin(source)
        assert local_vars[VarName("r")] == 30


class TestKotlinWhenIsTypeMatch:
    """when expression using is Type checks."""

    def test_is_int_matches_integer_value(self):
        """when(x) { is Int -> 1; is String -> 2; else -> 0 } should return 1 when x is an Int."""
        source = """\
val x: Any = 42
val r = when(x) {
    is Int -> 1
    is String -> 2
    else -> 0
}
"""
        local_vars = _run_kotlin(source)
        assert local_vars[VarName("r")] == 1

    def test_is_int_no_match_falls_to_else(self):
        """when(x) { is Int -> 1; else -> 0 } should return 0 when x is a String."""
        source = """\
val x: Any = "hello"
val r = when(x) {
    is Int -> 1
    else -> 0
}
"""
        local_vars = _run_kotlin(source)
        assert local_vars[VarName("r")] == 0
