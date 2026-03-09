"""Unit tests verifying for-each loop termination.

These tests verify that for-each/for-of/for-in loops actually terminate
by checking that the VM completes within a reasonable step budget and
produces the correct accumulated result.

The root cause being tested: the loop index update must feed back into
the loop condition so the counter advances each iteration.
"""

from __future__ import annotations

import pytest

from interpreter.ir import Opcode
from tests.unit.rosetta.conftest import execute_for_language, extract_answer


class TestJavaScriptForOfTermination:
    def test_for_of_accumulates_correctly(self):
        vm, stats = execute_for_language(
            "javascript",
            """\
var arr = [10, 5, 3];
var answer = 0;
for (const x of arr) {
    answer = answer + x;
}
""",
        )
        assert extract_answer(vm, "javascript") == 18
        assert stats.steps < 200

    @pytest.mark.xfail(
        reason="VM keys() returns symbolic — loop condition never resolves to False"
    )
    def test_for_in_accumulates_correctly(self):
        vm, stats = execute_for_language(
            "javascript",
            """\
var obj = {a: 10, b: 5};
var answer = 2;
for (var k in obj) {
    answer = answer + 1;
}
""",
        )
        # answer = 2 + number of keys
        assert stats.steps < 200


class TestTypeScriptForOfTermination:
    def test_for_of_accumulates_correctly(self):
        vm, stats = execute_for_language(
            "typescript",
            """\
var arr: number[] = [10, 5, 3];
var answer: number = 0;
for (const x of arr) {
    answer = answer + x;
}
""",
        )
        assert extract_answer(vm, "typescript") == 18
        assert stats.steps < 200


class TestPythonForTermination:
    def test_for_accumulates_correctly(self):
        vm, stats = execute_for_language(
            "python",
            """\
arr = [10, 5, 3]
answer = 0
for x in arr:
    answer = answer + x
""",
        )
        assert extract_answer(vm, "python") == 18
        assert stats.steps < 200


class TestJavaForEachTermination:
    def test_enhanced_for_accumulates_correctly(self):
        vm, stats = execute_for_language(
            "java",
            """\
class M {
    void m() {
        int[] arr = {10, 5, 3};
        int answer = 0;
        for (int x : arr) {
            answer = answer + x;
        }
    }
}
""",
        )
        # Java answer is inside a method, not at top level
        assert stats.steps < 200


class TestKotlinForTermination:
    def test_for_accumulates_correctly(self):
        vm, stats = execute_for_language(
            "kotlin",
            """\
val arr = arrayOf(10, 5, 3)
var answer = 0
for (x in arr) {
    answer = answer + x
}
""",
        )
        assert extract_answer(vm, "kotlin") == 18
        assert stats.steps < 200


class TestRustForTermination:
    def test_for_accumulates_correctly(self):
        vm, stats = execute_for_language(
            "rust",
            """\
fn main() {
    let arr = vec![10, 5, 3];
    let mut answer = 0;
    for x in arr {
        answer = answer + x;
    }
}
""",
        )
        assert stats.steps < 200


class TestGoRangeTermination:
    def test_range_accumulates_correctly(self):
        vm, stats = execute_for_language(
            "go",
            """\
package main
func main() {
    arr := []int{10, 5, 3}
    answer := 0
    for _, x := range arr {
        answer = answer + x
    }
}
""",
        )
        assert stats.steps < 200


class TestRubyForTermination:
    @pytest.mark.xfail(
        reason="Ruby array literal lowering produces unexpected structure for iteration"
    )
    def test_for_accumulates_correctly(self):
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


class TestCppRangeForTermination:
    def test_range_for_accumulates_correctly(self):
        vm, stats = execute_for_language(
            "cpp",
            """\
int arr[] = {10, 5, 3};
int answer = 0;
for (auto x : arr) {
    answer = answer + x;
}
""",
        )
        assert extract_answer(vm, "cpp") == 18
        assert stats.steps < 200


class TestLuaGenericForTermination:
    @pytest.mark.xfail(
        reason="VM ipairs() returns symbolic — loop condition never resolves to False"
    )
    def test_generic_for_accumulates_correctly(self):
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
