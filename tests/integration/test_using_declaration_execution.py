"""Integration tests: JS using_declaration lowered as const.

Verifies that `using x = expr` produces the same runtime result
as `const x = expr` — the variable gets the initializer's value
and is usable in subsequent expressions.

NOTE: Symbol.dispose() semantics are NOT implemented (see ADR-101).
"""

from __future__ import annotations

from tests.unit.rosetta.conftest import execute_for_language, extract_answer


class TestUsingDeclarationSimple:
    """using x = 42; answer = x => 42."""

    PROGRAM = """\
using x = 42;
let answer = x;
"""

    def test_using_assigns_value(self):
        vm, _stats = execute_for_language("javascript", self.PROGRAM)
        answer = extract_answer(vm, "javascript")
        assert answer == 42, f"expected 42, got {answer}"

    def test_zero_llm_calls(self):
        _vm, stats = execute_for_language("javascript", self.PROGRAM)
        assert stats.llm_calls == 0


class TestUsingDeclarationWithComputation:
    """using val = 10 + 20; answer = val * 2 => 60."""

    PROGRAM = """\
using val = 10 + 20;
let answer = val * 2;
"""

    def test_using_with_expression(self):
        vm, _stats = execute_for_language("javascript", self.PROGRAM)
        answer = extract_answer(vm, "javascript")
        assert answer == 60, f"expected 60, got {answer}"

    def test_zero_llm_calls(self):
        _vm, stats = execute_for_language("javascript", self.PROGRAM)
        assert stats.llm_calls == 0


class TestUsingDeclarationEquivalentToConst:
    """using and const should produce the same runtime result."""

    USING_PROGRAM = """\
using a = 5;
using b = 10;
let answer = a + b;
"""

    CONST_PROGRAM = """\
const a = 5;
const b = 10;
let answer = a + b;
"""

    def test_using_matches_const_result(self):
        vm_using, _ = execute_for_language("javascript", self.USING_PROGRAM)
        vm_const, _ = execute_for_language("javascript", self.CONST_PROGRAM)
        using_answer = extract_answer(vm_using, "javascript")
        const_answer = extract_answer(vm_const, "javascript")
        assert using_answer == const_answer == 15
