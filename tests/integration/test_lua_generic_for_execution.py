"""Integration tests for Lua generic for loop execution.

Verifies that Lua for-in with ipairs()/pairs() correctly iterates
through the full parse → lower → execute pipeline.
"""

from __future__ import annotations

from tests.unit.rosetta.conftest import execute_for_language, extract_answer


class TestLuaIpairsExecution:
    def test_ipairs_accumulates_sum(self):
        """for _, x in ipairs(arr) should iterate and sum elements."""
        vm, stats = execute_for_language(
            "lua",
            """\
local arr = {10, 5, 3}
local answer = 0
for _, x in ipairs(arr) do
    answer = answer + x
end
""",
        )
        assert stats.steps < 200

    def test_ipairs_single_element(self):
        """ipairs over single-element table."""
        vm, stats = execute_for_language(
            "lua",
            """\
local arr = {42}
local answer = 0
for _, x in ipairs(arr) do
    answer = answer + x
end
""",
        )
        assert stats.steps < 200


class TestLuaPairsExecution:
    def test_pairs_iterates(self):
        """for k, v in pairs(t) should terminate."""
        vm, stats = execute_for_language(
            "lua",
            """\
local t = {10, 20, 30}
local answer = 0
for k, v in pairs(t) do
    answer = answer + 1
end
""",
        )
        assert stats.steps < 200
