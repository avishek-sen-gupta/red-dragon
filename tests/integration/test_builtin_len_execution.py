"""Integration tests for _builtin_len with array length field.

Verifies that len() returns correct values when arrays have an explicit
'length' field (as created by arrayOf/intArrayOf), through the full
parse → lower → execute pipeline across multiple languages.
"""

from __future__ import annotations

from tests.unit.rosetta.conftest import execute_for_language, extract_answer


class TestKotlinArrayOfLenExecution:
    def test_for_loop_iterates_correct_count(self):
        """arrayOf(10, 5, 3) should iterate exactly 3 times."""
        vm, stats = execute_for_language(
            "kotlin",
            """\
val arr = arrayOf(10, 5, 3)
var answer = 0
for (x in arr) {
    answer = answer + 1
}
""",
        )
        assert extract_answer(vm, "kotlin") == 3
        assert stats.steps < 200

    def test_empty_arrayOf_no_iterations(self):
        """arrayOf() with no elements should not iterate."""
        vm, stats = execute_for_language(
            "kotlin",
            """\
val arr = arrayOf<Int>()
var answer = 42
for (x in arr) {
    answer = 0
}
""",
        )
        assert extract_answer(vm, "kotlin") == 42


class TestJavaScriptArrayLenExecution:
    def test_array_literal_iterates_correct_count(self):
        """JS array [10, 5, 3] should iterate exactly 3 times via for-of."""
        vm, stats = execute_for_language(
            "javascript",
            """\
var arr = [10, 5, 3];
var answer = 0;
for (const x of arr) {
    answer = answer + 1;
}
""",
        )
        assert extract_answer(vm, "javascript") == 3
        assert stats.steps < 200
