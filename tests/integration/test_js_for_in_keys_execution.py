"""Integration tests for JS for-in loop with keys() builtin.

Verifies that for-in over objects correctly iterates over field names
through the full parse → lower → execute pipeline.
"""

from __future__ import annotations

from tests.unit.rosetta.conftest import execute_for_language, extract_answer


class TestJSForInExecution:
    def test_for_in_counts_keys(self):
        """for (var k in obj) should iterate over object keys."""
        vm, stats = execute_for_language(
            "javascript",
            """\
var obj = {a: 10, b: 5};
var answer = 0;
for (var k in obj) {
    answer = answer + 1;
}
""",
        )
        assert extract_answer(vm, "javascript") == 2
        assert stats.steps < 200

    def test_for_in_three_keys(self):
        """for-in over a 3-key object should iterate 3 times."""
        vm, stats = execute_for_language(
            "javascript",
            """\
var obj = {x: 1, y: 2, z: 3};
var answer = 0;
for (var k in obj) {
    answer = answer + 1;
}
""",
        )
        assert extract_answer(vm, "javascript") == 3
        assert stats.steps < 200

    def test_for_in_empty_object(self):
        """for-in over empty object should not iterate."""
        vm, stats = execute_for_language(
            "javascript",
            """\
var obj = {};
var answer = 42;
for (var k in obj) {
    answer = 0;
}
""",
        )
        assert extract_answer(vm, "javascript") == 42

    def test_for_in_single_key(self):
        """for-in over a 1-key object should iterate once."""
        vm, stats = execute_for_language(
            "javascript",
            """\
var obj = {solo: 99};
var answer = 0;
for (var k in obj) {
    answer = answer + 1;
}
""",
        )
        assert extract_answer(vm, "javascript") == 1
        assert stats.steps < 200
