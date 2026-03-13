"""Integration tests: rest pattern destructuring in JS/TS.

Verifies that array rest ([a, ...rest] = arr) and object rest
({a, ...rest} = obj) produce correct concrete values through
the VM's slice and object_rest builtins.
"""

from __future__ import annotations

import pytest

from interpreter.typed_value import unwrap
from tests.unit.rosetta.conftest import (
    execute_for_language,
    extract_answer,
    extract_array,
)


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

    def test_rest_contains_remaining(self):
        vm, _stats = execute_for_language("javascript", self.PROGRAM)
        rest = extract_array(vm, "rest", 2, "javascript")
        assert rest == [2, 3], f"expected rest=[2, 3], got {rest}"

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

    def test_rest_contains_remaining(self):
        vm, _stats = execute_for_language("javascript", self.PROGRAM)
        rest = extract_array(vm, "rest", 2, "javascript")
        assert rest == [30, 40], f"expected rest=[30, 40], got {rest}"


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


class TestObjectRestPattern:
    """const {a, ...rest} = {a: 1, b: 2, c: 3}; answer = a => 1."""

    PROGRAM = """\
let obj = {a: 1, b: 2, c: 3};
let {a, ...rest} = obj;
let answer = a;
"""

    def test_extracted_field(self):
        vm, stats = execute_for_language("javascript", self.PROGRAM)
        answer = extract_answer(vm, "javascript")
        assert answer == 1, f"expected a=1, got {answer}"

    def test_rest_contains_remaining_fields(self):
        vm, _stats = execute_for_language("javascript", self.PROGRAM)
        frame = vm.call_stack[0]
        rest_addr = unwrap(frame.local_vars["rest"])
        rest_obj = vm.heap[rest_addr]
        assert (
            rest_obj.fields["b"].value == 2
        ), f"expected b=2, got {rest_obj.fields.get('b')}"
        assert (
            rest_obj.fields["c"].value == 3
        ), f"expected c=3, got {rest_obj.fields.get('c')}"
        assert "a" not in rest_obj.fields, "rest should not contain excluded key 'a'"

    def test_zero_llm_calls_obj_rest(self):
        _vm, stats = execute_for_language("javascript", self.PROGRAM)
        assert stats.llm_calls == 0


class TestFunctionRestParameter:
    """function foo(a, ...rest) called with foo(1, 2, 3) => rest = [2, 3]."""

    PROGRAM = """\
function foo(a, ...rest) {
    return rest;
}
let result = foo(1, 2, 3);
let answer = 1;
"""

    def test_rest_is_array(self):
        vm, _stats = execute_for_language("javascript", self.PROGRAM)
        result = unwrap(vm.call_stack[0].local_vars.get("result"))
        assert result in vm.heap, f"expected heap address, got {result}"
        heap_obj = vm.heap[result]
        assert (
            heap_obj.fields["0"].value == 2
        ), f"expected rest[0]=2, got {heap_obj.fields}"
        assert (
            heap_obj.fields["1"].value == 3
        ), f"expected rest[1]=3, got {heap_obj.fields}"
        assert heap_obj.fields["length"].value == 2

    def test_zero_llm_calls(self):
        _vm, stats = execute_for_language("javascript", self.PROGRAM)
        assert stats.llm_calls == 0


class TestFunctionRestParameterComputation:
    """function sum(first, ...rest) computes first + rest[0] + rest[1]."""

    PROGRAM = """\
function sum(first, ...rest) {
    let total = first + rest[0] + rest[1];
    return total;
}
let answer = sum(10, 20, 30);
"""

    def test_sum_result(self):
        vm, _stats = execute_for_language("javascript", self.PROGRAM)
        answer = extract_answer(vm, "javascript")
        assert answer == 60, f"expected 60, got {answer}"

    def test_zero_llm_calls(self):
        _vm, stats = execute_for_language("javascript", self.PROGRAM)
        assert stats.llm_calls == 0
