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
    def test_while_let_capture_always_matches(self):
        """while let n = expr with capture always matches — must break manually."""
        _, local_vars = _run_rust(
            """\
let mut counter = 3;
let mut sum = 0;
while let n = counter {
    if n == 0 { break; }
    sum = sum + n;
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

    def test_while_let_tuple_destructuring(self):
        """while let (a, b) = pair destructures tuple each iteration."""
        _, local_vars = _run_rust(
            """\
let mut pair = (1, 2);
let mut sum = 0;
while let Some(v) = if sum < 5 { Some(pair) } else { 0 } {
    let (a, b) = v;
    sum = sum + a + b;
    pair = (a + 1, b + 1);
}
""",
            max_steps=1000,
        )
        assert local_vars["sum"] == 8


class TestRustLetChain:
    def test_let_chain_both_match(self):
        """if let Some(x) = a && let Some(y) = b should bind both."""
        _, local_vars = _run_rust(
            """\
let a = Some(3);
let b = Some(4);
let r = if let Some(x) = a && let Some(y) = b { x + y } else { 0 };
""",
            max_steps=500,
        )
        assert local_vars["r"] == 7

    def test_let_chain_first_fails(self):
        """If first let condition fails, take else branch."""
        _, local_vars = _run_rust(
            """\
let a = 0;
let b = Some(4);
let r = if let Some(x) = a && let Some(y) = b { x + y } else { -1 };
""",
            max_steps=500,
        )
        assert local_vars["r"] == -1

    def test_let_chain_second_fails(self):
        """If second let condition fails, take else branch."""
        _, local_vars = _run_rust(
            """\
let a = Some(3);
let b = 0;
let r = if let Some(x) = a && let Some(y) = b { x + y } else { -1 };
""",
            max_steps=500,
        )
        assert local_vars["r"] == -1

    def test_let_chain_both_fail(self):
        """If both conditions fail, take else branch."""
        _, local_vars = _run_rust(
            """\
let a = 0;
let b = 0;
let r = if let Some(x) = a && let Some(y) = b { x + y } else { -1 };
""",
            max_steps=500,
        )
        assert local_vars["r"] == -1

    def test_let_chain_three_conditions(self):
        """Three-way let chain: all must match."""
        _, local_vars = _run_rust(
            """\
let a = Some(1);
let b = Some(2);
let c = Some(3);
let r = if let Some(x) = a && let Some(y) = b && let Some(z) = c { x + y + z } else { 0 };
""",
            max_steps=500,
        )
        assert local_vars["r"] == 6

    def test_let_chain_no_else(self):
        """Let chain with no else branch — result is body value when matched."""
        _, local_vars = _run_rust(
            """\
let a = Some(10);
let b = Some(20);
let r = 0;
if let Some(x) = a && let Some(y) = b {
    r = x + y;
}
""",
            max_steps=500,
        )
        assert local_vars["r"] == 30


class TestRustReferencePattern:
    def test_match_ref_capture(self):
        """match &x { &val => val + 1 } should dereference and bind val."""
        _, local_vars = _run_rust(
            """\
let x = 42;
let r = &x;
let result = match r {
    &val => val + 1,
    _ => 0,
};
""",
            max_steps=300,
        )
        assert local_vars["result"] == 43

    def test_if_let_ref_capture(self):
        """if let &val = &x should dereference and bind val."""
        _, local_vars = _run_rust(
            """\
let x = 10;
let r = &x;
let result = if let &val = r { val * 2 } else { 0 };
""",
            max_steps=300,
        )
        assert local_vars["result"] == 20

    def test_match_ref_literal(self):
        """match &x { &42 => 1, _ => 0 } should dereference and compare literal."""
        _, local_vars = _run_rust(
            """\
let x = 42;
let r = &x;
let result = match r {
    &42 => 1,
    _ => 0,
};
""",
            max_steps=300,
        )
        assert local_vars["result"] == 1

    def test_match_ref_wildcard(self):
        """match &x { &_ => 1 } should dereference and match wildcard."""
        _, local_vars = _run_rust(
            """\
let x = 99;
let r = &x;
let result = match r {
    &_ => 1,
};
""",
            max_steps=300,
        )
        assert local_vars["result"] == 1

    def test_match_ref_deref_in_body(self):
        """match &x { val => *val } should bind reference then deref in body."""
        _, local_vars = _run_rust(
            """\
let x = 5;
let r = &x;
let result = match r {
    val => *val,
};
""",
            max_steps=300,
        )
        assert local_vars["result"] == 5


class TestRustSlicePattern:
    def test_slice_destructure_all(self):
        """match [1,2,3] { [a, b, c] => a + b + c } should produce 6."""
        _, local_vars = _run_rust(
            """\
let arr = [1, 2, 3];
let r = match arr {
    [a, b, c] => a + b + c,
    _ => 0,
};
""",
            max_steps=500,
        )
        assert local_vars["r"] == 6

    def test_slice_first_with_rest(self):
        """match [1,2,3] { [first, ..] => first } should produce 1."""
        _, local_vars = _run_rust(
            """\
let arr = [1, 2, 3];
let r = match arr {
    [first, ..] => first,
    _ => 0,
};
""",
            max_steps=500,
        )
        assert local_vars["r"] == 1

    def test_slice_empty(self):
        """match [] { [] => 1, _ => 0 } should match empty array."""
        _, local_vars = _run_rust(
            """\
let arr: [i32; 0] = [];
let r = match arr {
    [] => 1,
    _ => 0,
};
""",
            max_steps=500,
        )
        assert local_vars["r"] == 1

    def test_slice_wildcards_and_capture(self):
        """match [1,2,3] { [_, _, third] => third } should produce 3."""
        _, local_vars = _run_rust(
            """\
let arr = [1, 2, 3];
let r = match arr {
    [_, _, third] => third,
    _ => 0,
};
""",
            max_steps=500,
        )
        assert local_vars["r"] == 3
