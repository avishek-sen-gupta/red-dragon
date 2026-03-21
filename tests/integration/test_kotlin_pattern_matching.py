"""Integration tests for Kotlin when pattern matching — end-to-end execution."""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_kotlin(source: str, max_steps: int = 500):
    """Run a Kotlin program and return frame.local_vars."""
    vm = run(source, language=Language.KOTLIN, max_steps=max_steps)
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
        assert local_vars["r"] == 10

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
        assert local_vars["r"] == 0

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
        assert local_vars["r"] == 20
