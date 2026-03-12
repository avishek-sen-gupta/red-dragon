"""Integration tests for Rust frontend: raw_string_literal, negative_literal, foreign_mod_item, union_item, macro_definition, mut_pattern."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_rust(source: str, max_steps: int = 200):
    vm = run(source, language=Language.RUST, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestRustRawStringLiteralExecution:
    def test_raw_string_assigned(self):
        """let x = r\"hello\"; should execute without errors."""
        _, local_vars = _run_rust('let x = r"hello";')
        assert "x" in local_vars

    def test_raw_string_in_comparison(self):
        """Raw string should be usable in comparison without crashing."""
        _, local_vars = _run_rust("""\
let x = r"hello";
let y = r"hello";
let same = x == y;
""")
        assert local_vars["same"] is True

    def test_raw_string_with_hashes(self):
        """r#\"has quotes\"# should execute without errors."""
        _, local_vars = _run_rust("""\
let x = r#"has quotes"#;
let y = 42;
""")
        assert local_vars["y"] == 42


class TestRustNegativeLiteralExecution:
    def test_negative_literal_value(self):
        """let x: i32 = -1; should store -1."""
        _, local_vars = _run_rust("let x: i32 = -1;")
        assert local_vars["x"] == -1

    def test_negative_literal_in_arithmetic(self):
        """Negative literal should be usable in arithmetic."""
        _, local_vars = _run_rust("""\
let x: i32 = -5;
let y = x + 10;
""")
        assert local_vars["y"] == 5

    def test_negative_float_literal(self):
        """let x = -3.0; should store a negative float."""
        _, local_vars = _run_rust("let x: f64 = -3.0;")
        assert local_vars["x"] == -3.0

    def test_negative_literal_in_match_pattern(self):
        """match arm with -1 pattern should execute without errors."""
        _, local_vars = _run_rust(
            """\
let x = 5;
let r = match x {
    -1 => 10,
    5 => 50,
    _ => 0,
};
""",
            max_steps=300,
        )
        assert local_vars["r"] == 50

    def test_negative_literal_match_hits_negative(self):
        """match arm with -1 pattern should match when value is -1."""
        _, local_vars = _run_rust(
            """\
let x: i32 = -1;
let r = match x {
    -1 => 10,
    5 => 50,
    _ => 0,
};
""",
            max_steps=300,
        )
        assert local_vars["r"] == 10


class TestRustForeignModItemExecution:
    def test_code_after_extern_block_executes(self):
        """Code after extern block should execute normally."""
        _, locals_ = _run_rust('extern "C" { fn foo(); }\nlet x = 10;')
        assert locals_["x"] == 10


class TestRustUnionItemExecution:
    def test_code_after_union_executes(self):
        """Code after union definition should execute normally."""
        _, locals_ = _run_rust("union Foo { x: i32, y: f64 }\nlet a = 5;")
        assert locals_["a"] == 5


class TestRustMacroDefinitionExecution:
    def test_code_after_macro_def_executes(self):
        """Code after macro_rules! should execute normally."""
        _, locals_ = _run_rust("macro_rules! my_macro { () => {} }\nlet y = 99;")
        assert locals_["y"] == 99


class TestRustMutPatternExecution:
    def test_let_mut_stores_value(self):
        """let mut x = 42 should store 42 in x."""
        _, locals_ = _run_rust("let mut x = 42;")
        assert locals_["x"] == 42

    def test_let_mut_reassignment(self):
        """let mut x should allow reassignment."""
        _, locals_ = _run_rust("let mut x = 1;\nx = 2;")
        assert locals_["x"] == 2
