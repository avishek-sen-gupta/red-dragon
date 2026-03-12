"""Integration tests: per-language slice/range execution.

Verifies that slice syntax produces correct concrete values
through the VM's slice builtin. Each language class is
independent — add/remove without affecting others.
"""

from __future__ import annotations

from tests.unit.rosetta.conftest import (
    execute_for_language,
    extract_answer,
    extract_array,
)


class TestPythonSliceBasic:
    """arr = [10, 20, 30, 40, 50]; answer = arr[1:3] => [20, 30]."""

    PROGRAM = """\
arr = [10, 20, 30, 40, 50]
result = arr[1:3]
answer = result[0] + result[1]
"""

    def test_slice_produces_correct_sum(self):
        vm, _stats = execute_for_language("python", self.PROGRAM)
        answer = extract_answer(vm, "python")
        assert answer == 50, f"expected 50, got {answer}"

    def test_zero_llm_calls(self):
        _vm, stats = execute_for_language("python", self.PROGRAM)
        assert stats.llm_calls == 0


class TestPythonSliceNoStart:
    """arr[:2] should return first 2 elements."""

    PROGRAM = """\
arr = [10, 20, 30, 40]
result = arr[:2]
answer = result[0] + result[1]
"""

    def test_slice_from_beginning(self):
        vm, _stats = execute_for_language("python", self.PROGRAM)
        answer = extract_answer(vm, "python")
        assert answer == 30, f"expected 30, got {answer}"


class TestPythonSliceNoStop:
    """arr[2:] should return from index 2 onward."""

    PROGRAM = """\
arr = [10, 20, 30, 40]
result = arr[2:]
answer = result[0] + result[1]
"""

    def test_slice_to_end(self):
        vm, _stats = execute_for_language("python", self.PROGRAM)
        answer = extract_answer(vm, "python")
        assert answer == 70, f"expected 70, got {answer}"


class TestPythonSliceWithStep:
    """arr[::2] should return every other element."""

    PROGRAM = """\
arr = [0, 1, 2, 3, 4, 5]
result = arr[::2]
answer = result[0] + result[1] + result[2]
"""

    def test_step_slice(self):
        vm, _stats = execute_for_language("python", self.PROGRAM)
        answer = extract_answer(vm, "python")
        assert answer == 6, f"expected 6 (0+2+4), got {answer}"

    def test_zero_llm_calls(self):
        _vm, stats = execute_for_language("python", self.PROGRAM)
        assert stats.llm_calls == 0


class TestPythonSliceNegativeStart:
    """arr[-2:] should return last 2 elements."""

    PROGRAM = """\
arr = [10, 20, 30, 40]
result = arr[-2:]
answer = result[0] + result[1]
"""

    def test_negative_start(self):
        vm, _stats = execute_for_language("python", self.PROGRAM)
        answer = extract_answer(vm, "python")
        assert answer == 70, f"expected 70, got {answer}"


# ── Go ────────────────────────────────────────────────────────


class TestGoSliceBasic:
    """arr[1:3] should return [20, 30]."""

    PROGRAM = """\
package main
func main() {
    arr := []int{10, 20, 30, 40, 50}
    result := arr[1:3]
    answer := result[0] + result[1]
}
"""

    def test_slice_produces_correct_sum(self):
        vm, _stats = execute_for_language("go", self.PROGRAM)
        answer = extract_answer(vm, "go")
        assert answer == 50, f"expected 50, got {answer}"

    def test_zero_llm_calls(self):
        _vm, stats = execute_for_language("go", self.PROGRAM)
        assert stats.llm_calls == 0


class TestGoSliceNoEnd:
    """arr[2:] should return from index 2 onward."""

    PROGRAM = """\
package main
func main() {
    arr := []int{10, 20, 30, 40}
    result := arr[2:]
    answer := result[0] + result[1]
}
"""

    def test_slice_to_end(self):
        vm, _stats = execute_for_language("go", self.PROGRAM)
        answer = extract_answer(vm, "go")
        assert answer == 70, f"expected 70, got {answer}"


class TestGoStringSlice:
    """s[0:2] on a string should return substring."""

    PROGRAM = """\
package main
func main() {
    s := "hello"
    t := s[0:2]
    answer := 1
}
"""

    def test_string_slice(self):
        vm, _stats = execute_for_language("go", self.PROGRAM)
        frame = vm.call_stack[0]
        t_val = frame.local_vars.get("t")
        assert t_val == "he", f"expected 'he', got {t_val}"


# ── Ruby ──────────────────────────────────────────────────────


class TestRubySliceInclusive:
    """arr[1..3] (inclusive) should return elements at indices 1, 2, 3."""

    PROGRAM = """\
arr = [10, 20, 30, 40, 50]
result = arr[1..3]
answer = result[0] + result[1] + result[2]
"""

    def test_inclusive_range_slice(self):
        vm, _stats = execute_for_language("ruby", self.PROGRAM)
        answer = extract_answer(vm, "ruby")
        assert answer == 90, f"expected 90 (20+30+40), got {answer}"

    def test_zero_llm_calls(self):
        _vm, stats = execute_for_language("ruby", self.PROGRAM)
        assert stats.llm_calls == 0


class TestRubySliceExclusive:
    """arr[1...3] (exclusive) should return elements at indices 1, 2."""

    PROGRAM = """\
arr = [10, 20, 30, 40, 50]
result = arr[1...3]
answer = result[0] + result[1]
"""

    def test_exclusive_range_slice(self):
        vm, _stats = execute_for_language("ruby", self.PROGRAM)
        answer = extract_answer(vm, "ruby")
        assert answer == 50, f"expected 50 (20+30), got {answer}"


class TestRubyPositionalSlice:
    """arr[1, 2] means 'start at index 1, take 2 elements'."""

    PROGRAM = """\
arr = [10, 20, 30, 40, 50]
result = arr[1, 2]
answer = result[0] + result[1]
"""

    def test_positional_slice(self):
        vm, _stats = execute_for_language("ruby", self.PROGRAM)
        answer = extract_answer(vm, "ruby")
        assert answer == 50, f"expected 50 (20+30), got {answer}"

    def test_zero_llm_calls(self):
        _vm, stats = execute_for_language("ruby", self.PROGRAM)
        assert stats.llm_calls == 0


# ── Rust ──────────────────────────────────────────────────────


class TestRustSliceExclusive:
    """arr[1..3] (exclusive) should return elements at indices 1, 2."""

    PROGRAM = """\
let arr = [10, 20, 30, 40, 50];
let result = arr[1..3];
let answer = result[0] + result[1];
"""

    def test_exclusive_range_slice(self):
        vm, _stats = execute_for_language("rust", self.PROGRAM)
        answer = extract_answer(vm, "rust")
        assert answer == 50, f"expected 50 (20+30), got {answer}"

    def test_zero_llm_calls(self):
        _vm, stats = execute_for_language("rust", self.PROGRAM)
        assert stats.llm_calls == 0


class TestRustSliceInclusive:
    """arr[1..=3] (inclusive) should return elements at indices 1, 2, 3."""

    PROGRAM = """\
let arr = [10, 20, 30, 40, 50];
let result = arr[1..=3];
let answer = result[0] + result[1] + result[2];
"""

    def test_inclusive_range_slice(self):
        vm, _stats = execute_for_language("rust", self.PROGRAM)
        answer = extract_answer(vm, "rust")
        assert answer == 90, f"expected 90 (20+30+40), got {answer}"
