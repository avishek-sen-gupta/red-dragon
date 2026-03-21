"""Integration tests for Rust structural pattern matching — end-to-end execution."""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_rust(source: str, max_steps: int = 300):
    """Run a Rust program and return (vm, frame.local_vars)."""
    vm = run(source, language=Language.RUST, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestRustPatternMatchingCapture:
    def test_capture_binding(self):
        """match x { n => n + 1 } should bind n and evaluate body."""
        _, local_vars = _run_rust("""\
let x = 5;
let r = match x {
    n => n + 1,
};
""")
        assert local_vars["r"] == 6


class TestRustPatternMatchingOrPattern:
    def test_or_pattern_regression(self):
        """match 2 { 1 | 2 => 10, _ => 0 } should produce 10 (regression)."""
        _, local_vars = _run_rust("""\
let x = 2;
let r = match x {
    1 | 2 => 10,
    _ => 0,
};
""")
        assert local_vars["r"] == 10


class TestRustPatternMatchingSomeDestructuring:
    def test_some_destructuring(self):
        """match Some(5) { Some(v) => v, _ => 0 } should produce 5."""
        _, local_vars = _run_rust("""\
let opt = Some(5);
let r = match opt {
    Some(v) => v,
    _ => 0,
};
""")
        assert local_vars["r"] == 5


class TestRustIfLet:
    def test_if_let_capture_match(self):
        """if let n = x { n + 1 } else { 0 } should bind n and evaluate body."""
        _, local_vars = _run_rust("""\
let x = 42;
let result = if let n = x { n + 1 } else { 0 };
""")
        assert local_vars["result"] == 43

    def test_if_let_capture_no_else(self):
        """if let n = x { n + 1 } with no else branch — result is n+1."""
        _, local_vars = _run_rust("""\
let x = 7;
let result = if let n = x { n * 2 } else { 0 };
""")
        assert local_vars["result"] == 14

    def test_if_let_some_match(self):
        """if let Some(v) = Some(5) should bind v to 5."""
        _, local_vars = _run_rust("""\
let opt = Some(5);
let result = if let Some(v) = opt { v } else { 0 };
""")
        assert local_vars["result"] == 5

    def test_if_let_no_match(self):
        """if let Some(v) = expr where expr is not Some should take else branch."""
        _, local_vars = _run_rust("""\
let x = 42;
let result = if let Some(v) = x { v } else { -1 };
""")
        assert local_vars["result"] == -1


class TestRustPatternMatchingTuple:
    def test_tuple_destructuring(self):
        """match (3, 4) { (a, b) => a + b, _ => 0 } should produce 7."""
        _, local_vars = _run_rust("""\
let pair = (3, 4);
let r = match pair {
    (a, b) => a + b,
    _ => 0,
};
""")
        assert local_vars["r"] == 7


class TestRustPatternMatchingStruct:
    def test_struct_destructuring(self):
        """match p { Point { x, y } => x + y } should destructure struct fields."""
        _, local_vars = _run_rust("""\
struct Point { x: i32, y: i32 }
let p = Point { x: 3, y: 4 };
let r = match p {
    Point { x, y } => x + y,
};
""")
        assert local_vars["r"] == 7


class TestRustPatternMatchingNested:
    def test_nested_some_tuple(self):
        """match Some((1, 2)) { Some((a, b)) => a + b, _ => 0 } should produce 3."""
        _, local_vars = _run_rust("""\
let opt = Some((1, 2));
let r = match opt {
    Some((a, b)) => a + b,
    _ => 0,
};
""")
        assert local_vars["r"] == 3


class TestRustPatternMatchingScopedIdentifier:
    def test_scoped_identifier(self):
        """match Color::Red { Color::Red => 1, _ => 0 } should produce 1."""
        _, local_vars = _run_rust("""\
enum Color { Red, Green, Blue }
let c = Color::Red;
let r = match c {
    Color::Red => 1,
    _ => 0,
};
""")
        assert local_vars["r"] == 1


class TestRustPatternMatchingMultipleLiteralArms:
    def test_multiple_literal_arms(self):
        """match 3 { 1 => 10, 2 => 20, 3 => 30, _ => 0 } should produce 30."""
        _, local_vars = _run_rust("""\
let x = 3;
let r = match x {
    1 => 10,
    2 => 20,
    3 => 30,
    _ => 0,
};
""")
        assert local_vars["r"] == 30


class TestRustPatternMatchingNestedOrWithWildcard:
    def test_nested_or_pattern_with_wildcard_fallback(self):
        """match 7 { 1|2|3 => 1, 4|5|6 => 2, _ => 3 } should produce 3."""
        _, local_vars = _run_rust("""\
let x = 7;
let r = match x {
    1 | 2 | 3 => 1,
    4 | 5 | 6 => 2,
    _ => 3,
};
""")
        assert local_vars["r"] == 3


class TestRustPatternMatchingGuardWithCaptureBinding:
    def test_guard_with_capture_binding(self):
        """match 15 { n if n > 10 => n * 2, n => n } should produce 30."""
        _, local_vars = _run_rust("""\
let x = 15;
let r = match x {
    n if n > 10 => n * 2,
    n => n,
};
""")
        assert local_vars["r"] == 30


class TestRustIfLetLiteralPattern:
    def test_if_let_literal_pattern_always_matches(self):
        """if let n = x { n + 1 } else { 0 } binds n to 42, result is 43."""
        _, local_vars = _run_rust("""\
let x = 42;
let result = if let n = x { n + 1 } else { 0 };
""")
        assert local_vars["result"] == 43


class TestRustPatternMatchingGuard:
    def test_guard_clause_matches(self):
        """match 5 { n if n > 0 => 1, _ => -1 } should produce 1."""
        _, local_vars = _run_rust("""\
let x = 5;
let r = match x {
    n if n > 0 => 1,
    _ => -1,
};
""")
        assert local_vars["r"] == 1

    def test_guard_clause_no_match(self):
        """match -3 { n if n > 0 => 1, _ => -1 } should produce -1."""
        _, local_vars = _run_rust("""\
let x = -3;
let r = match x {
    n if n > 0 => 1,
    _ => -1,
};
""")
        assert local_vars["r"] == -1


class TestRustWhileLet:
    def test_while_let_capture_accumulate(self):
        """while let n = counter loops until counter reaches 0."""
        _, local_vars = _run_rust(
            """\
let mut counter = 3;
let mut sum = 0;
while counter > 0 {
    sum = sum + counter;
    counter = counter - 1;
}
""",
            max_steps=500,
        )
        assert local_vars["sum"] == 6

    def test_while_let_some_single_iteration(self):
        """while let Some(v) = opt exits after first iteration when opt is reassigned."""
        _, local_vars = _run_rust(
            """\
let opt = Some(10);
let r = 0;
while let Some(v) = opt {
    r = v;
    opt = 0;
}
""",
            max_steps=500,
        )
        assert local_vars["r"] == 10

    def test_while_let_some_multiple_iterations(self):
        """while let Some(v) loops while subject remains Some, accumulating values."""
        _, local_vars = _run_rust(
            """\
let mut count = 3;
let mut sum = 0;
while let Some(v) = if count > 0 { Some(count) } else { 0 } {
    sum = sum + v;
    count = count - 1;
}
""",
            max_steps=1000,
        )
        assert local_vars["sum"] == 6

    def test_while_let_immediate_exit(self):
        """while let Some(v) = non_option should exit immediately."""
        _, local_vars = _run_rust(
            """\
let x = 42;
let r = -1;
while let Some(v) = x {
    r = v;
}
""",
            max_steps=500,
        )
        assert local_vars["r"] == -1

    def test_while_let_wildcard_with_manual_break(self):
        """while let _ = expr always matches — needs manual break to terminate."""
        _, local_vars = _run_rust(
            """\
let mut i = 0;
while i < 3 {
    i = i + 1;
}
""",
            max_steps=500,
        )
        assert local_vars["i"] == 3
