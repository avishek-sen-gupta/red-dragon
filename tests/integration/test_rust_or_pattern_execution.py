"""Integration tests for Rust or_pattern in match arms -- end-to-end execution.

Verifies that match arms using `|` (or_pattern) produce correct results
through the full parse -> lower -> execute pipeline.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_rust(source: str, max_steps: int = 300):
    """Run a Rust program and return (vm, frame.local_vars)."""
    vm = run(source, language=Language.RUST, max_steps=max_steps)
    return vm, dict(vm.call_stack[0].local_vars)


class TestRustOrPatternExecution:
    def test_or_pattern_matches_first_alternative(self):
        """match 1 { 1 | 2 => 10, _ => 0 } should produce 10."""
        _, local_vars = _run_rust("""\
let x = 1;
let r = match x {
    1 | 2 => 10,
    _ => 0,
};
""")
        assert local_vars["r"] == 10

    def test_or_pattern_matches_second_alternative(self):
        """match 2 { 1 | 2 => 10, _ => 0 } should produce 10."""
        _, local_vars = _run_rust("""\
let x = 2;
let r = match x {
    1 | 2 => 10,
    _ => 0,
};
""")
        assert local_vars["r"] == 10

    def test_or_pattern_falls_through_to_wildcard(self):
        """match 5 { 1 | 2 => 10, _ => 0 } should produce 0."""
        _, local_vars = _run_rust("""\
let x = 5;
let r = match x {
    1 | 2 => 10,
    _ => 0,
};
""")
        assert local_vars["r"] == 0

    def test_or_pattern_three_alternatives(self):
        """match 3 { 1 | 2 | 3 => 10, _ => 0 } should produce 10."""
        _, local_vars = _run_rust("""\
let x = 3;
let r = match x {
    1 | 2 | 3 => 10,
    _ => 0,
};
""")
        assert local_vars["r"] == 10

    def test_or_pattern_with_mixed_arms(self):
        """Or-pattern arm alongside normal arms."""
        _, local_vars = _run_rust("""\
let x = 2;
let r = match x {
    1 | 2 => 10,
    3 => 30,
    _ => 0,
};
""")
        assert local_vars["r"] == 10

    def test_or_pattern_normal_arm_still_works(self):
        """Normal arm after or-pattern arm should still match."""
        _, local_vars = _run_rust("""\
let x = 3;
let r = match x {
    1 | 2 => 10,
    3 => 30,
    _ => 0,
};
""")
        assert local_vars["r"] == 30
