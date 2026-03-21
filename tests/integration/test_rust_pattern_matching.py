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
    @pytest.mark.xfail(
        reason="Option.__init__ sig/label mismatch — LOAD_INDEX on Option object "
        "returns symbolic value instead of concrete",
        strict=True,
    )
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

    @pytest.mark.xfail(
        reason="Option LOAD_INDEX on Option object returns symbolic value — red-dragon-jpgb",
        strict=True,
    )
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
    @pytest.mark.xfail(
        reason="Tuple construction not yet supported in Rust frontend",
        strict=False,
    )
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
    @pytest.mark.xfail(
        reason="Struct pattern destructuring needs struct class fields accessible via LOAD_FIELD",
        strict=False,
    )
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
    @pytest.mark.xfail(
        reason="Depends on Some(v) destructuring (red-dragon-jpgb)",
        strict=False,
    )
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
    @pytest.mark.xfail(
        reason="ValuePattern LOAD_VAR/LOAD_FIELD lookup for enum variants not yet wired",
        strict=False,
    )
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
