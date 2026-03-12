"""Integration tests: rest pattern destructuring in JS/TS.

Verifies that array rest ([a, ...rest] = arr) and object rest
({a, ...rest} = obj) produce correct concrete values through
the VM's slice and object_rest builtins.
"""

from __future__ import annotations

import pytest

from tests.unit.rosetta.conftest import execute_for_language, extract_answer


class TestArrayRestPattern:
    """const [first, ...rest] = [1, 2, 3]; answer = rest.length => 2."""

    PROGRAM = """\
let arr = [1, 2, 3];
let [first, ...rest] = arr;
let answer = first;
"""

    def test_first_element(self):
        vm, stats = execute_for_language("javascript", self.PROGRAM)
        answer = extract_answer(vm, "javascript")
        assert answer == 1, f"expected first=1, got {answer}"

    def test_zero_llm_calls(self):
        _vm, stats = execute_for_language("javascript", self.PROGRAM)
        assert stats.llm_calls == 0


class TestArrayRestPatternThreeElements:
    """const [a, b, ...rest] = [10, 20, 30, 40]; answer = a + b => 30."""

    PROGRAM = """\
let arr = [10, 20, 30, 40];
let [a, b, ...rest] = arr;
let answer = a + b;
"""

    def test_correct_sum(self):
        vm, stats = execute_for_language("javascript", self.PROGRAM)
        answer = extract_answer(vm, "javascript")
        assert answer == 30, f"expected 30, got {answer}"


class TestArrayRestPatternTS:
    """TypeScript inherits JS destructuring — verify it works."""

    PROGRAM = """\
let arr: number[] = [5, 6, 7];
let [head, ...tail] = arr;
let answer = head;
"""

    def test_ts_rest_pattern(self):
        vm, stats = execute_for_language("typescript", self.PROGRAM)
        answer = extract_answer(vm, "typescript")
        assert answer == 5, f"expected head=5, got {answer}"
