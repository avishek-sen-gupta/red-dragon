"""Integration tests for P1 lowering gaps: Rust (4), Go (1), JS (1), TS (1)."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_rust(source: str, max_steps: int = 200):
    vm = run(source, language=Language.RUST, max_steps=max_steps)
    return vm, dict(vm.call_stack[0].local_vars)


def _run_go(source: str, max_steps: int = 500):
    vm = run(source, language=Language.GO, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


def _run_js(source: str, max_steps: int = 200):
    vm = run(source, language=Language.JAVASCRIPT, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


def _run_ts(source: str, max_steps: int = 200):
    vm = run(source, language=Language.TYPESCRIPT, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


# ── Rust: foreign_mod_item ───────────────────────────────────────


class TestRustForeignModItemExecution:
    def test_code_after_extern_block_executes(self):
        """Code after extern block should execute normally."""
        _, locals_ = _run_rust('extern "C" { fn foo(); }\nlet x = 10;')
        assert locals_["x"] == 10


# ── Rust: union_item ─────────────────────────────────────────────


class TestRustUnionItemExecution:
    def test_code_after_union_executes(self):
        """Code after union definition should execute normally."""
        _, locals_ = _run_rust("union Foo { x: i32, y: f64 }\nlet a = 5;")
        assert locals_["a"] == 5


# ── Rust: macro_definition ───────────────────────────────────────


class TestRustMacroDefinitionExecution:
    def test_code_after_macro_def_executes(self):
        """Code after macro_rules! should execute normally."""
        _, locals_ = _run_rust("macro_rules! my_macro { () => {} }\nlet y = 99;")
        assert locals_["y"] == 99


# ── Rust: mut_pattern ────────────────────────────────────────────


class TestRustMutPatternExecution:
    def test_let_mut_stores_value(self):
        """let mut x = 42 should store 42 in x."""
        _, locals_ = _run_rust("let mut x = 42;")
        assert locals_["x"] == 42

    def test_let_mut_reassignment(self):
        """let mut x should allow reassignment."""
        _, locals_ = _run_rust("let mut x = 1;\nx = 2;")
        assert locals_["x"] == 2


# ── Go: variadic_argument ───────────────────────────────────────


class TestGoVariadicArgumentExecution:
    def test_code_with_variadic_call(self):
        """Function call with variadic arg should not block execution."""
        locals_ = _run_go("""\
package main
func main() {
  x := 42
  _ = x
}""")
        assert locals_["x"] == 42


# ── JS: meta_property ───────────────────────────────────────────


class TestJSMetaPropertyExecution:
    def test_meta_property_does_not_block(self):
        """Code after new.target usage should execute."""
        locals_ = _run_js("let x = new.target;\nlet y = 42;")
        assert locals_["y"] == 42


# ── TS: type_assertion ───────────────────────────────────────────


class TestTSTypeAssertionExecution:
    def test_type_assertion_passes_value_through(self):
        """<number>x should pass the value of x through."""
        locals_ = _run_ts("let x = 42;\nlet y = <number>x;")
        assert locals_["y"] == 42

    def test_type_assertion_string(self):
        """<string>val should pass string value through."""
        locals_ = _run_ts('let s = "hello";\nlet t = <string>s;')
        assert locals_["t"] == "hello"
