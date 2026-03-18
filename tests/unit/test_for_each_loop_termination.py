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
        # answer = 2 + number of keys (2) = 4
        assert extract_answer(vm, "javascript") == 4
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
    def test_enhanced_for_terminates(self):
        vm, stats = execute_for_language(
            "java",
            """\
class M {
    static int[] arr = {10, 5, 3};
    static int answer = 0;
    static {
        for (int x : arr) {
            answer = answer + x;
        }
    }
}
""",
        )
        assert extract_answer(vm, "java") == 18
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
    def test_for_terminates(self):
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
        # Rust answer is inside fn main() — not extractable from frame 0
        assert stats.steps < 200


class TestGoRangeTermination:
    def test_range_terminates(self):
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
        # Go answer is inside func main() — not extractable from frame 0
        assert stats.steps < 200


class TestRubyForTermination:
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
    def test_generic_for_terminates(self):
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
        # Lua ipairs iteration produces symbolic values — verify termination only
        assert stats.steps < 200
