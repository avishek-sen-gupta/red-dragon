"""Integration tests for Ruby for-in loop execution.

Verifies that Ruby for-in loops correctly iterate over arrays through
the full parse → lower → execute pipeline.
"""

from __future__ import annotations

from tests.unit.rosetta.conftest import execute_for_language, extract_answer


class TestRubyForInExecution:
    def test_for_in_accumulates_sum(self):
        """for x in arr should iterate over array elements and sum them."""
        vm, stats = execute_for_language(
            "ruby",
            """\
arr = [10, 5, 3]
answer = 0
for x in arr
    answer = answer + x
end
""",
        )
        assert extract_answer(vm, "ruby") == 18
        assert stats.steps < 200

    def test_for_in_single_element(self):
        """for loop over single-element array."""
        vm, stats = execute_for_language(
            "ruby",
            """\
arr = [42]
answer = 0
for x in arr
    answer = answer + x
end
""",
        )
        assert extract_answer(vm, "ruby") == 42
        assert stats.steps < 200
