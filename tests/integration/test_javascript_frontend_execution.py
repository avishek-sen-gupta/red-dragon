"""Integration tests for JavaScript frontend execution."""

from __future__ import annotations

import pytest

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint
from interpreter.frontends.javascript.features import JavaScriptFeature
from tests.covers import covers, FeatureStatus


def _run_js(source: str, max_steps: int = 200):
    vm = run(
        source,
        language=Language.JAVASCRIPT,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestJSComputedPropertyNameExecution:
    """computed_property_name in object literals should evaluate the key expression."""

    def test_variable_as_computed_key(self):
        locals_ = _run_js("""
            let key = "name";
            let obj = { [key]: "Alice" };
            let result = obj["name"];
            """)
        assert locals_[VarName("result")] == "Alice"

    def test_expression_as_computed_key(self):
        locals_ = _run_js("""
            let obj = { ["a" + "b"]: 42 };
            let result = obj["ab"];
            """)
        assert locals_[VarName("result")] == 42

    def test_mixed_computed_and_static_keys(self):
        locals_ = _run_js("""
            let key = "dynamic";
            let obj = { static_key: 1, [key]: 2 };
            let a = obj["static_key"];
            let b = obj["dynamic"];
            """)
        assert locals_[VarName("a")] == 1
        assert locals_[VarName("b")] == 2


class TestJSOptionalChainExecution:
    """optional_chain (obj?.prop) short-circuits to None on null, accesses on non-null."""

    def test_optional_chain_on_object(self):
        locals_ = _run_js("""
            let obj = { name: "Alice" };
            let result = obj?.name;
            """)
        assert locals_[VarName("result")] == "Alice"

    def test_optional_chain_on_null_returns_none(self):
        locals_ = _run_js("""
            let obj = null;
            let result = obj?.name;
            """)
        assert locals_[VarName("result")] is None

    def test_optional_chain_nested_short_circuits(self):
        locals_ = _run_js("""
            let outer = { inner: { value: 42 } };
            let result = outer?.inner?.value;
            """)
        assert locals_[VarName("result")] == 42


class TestJSAnonymousClassExpressionExecution:
    """Anonymous class expression should be instantiable and methods callable."""

    def test_anonymous_class_instantiation(self):
        locals_ = _run_js("""
            const Foo = class {
                constructor(x) { this.x = x; }
            };
            let obj = new Foo(42);
            let result = obj.x;
            """)
        assert locals_[VarName("result")] == 42

    def test_anonymous_class_method_call(self):
        locals_ = _run_js("""
            const Adder = class {
                constructor(a) { this.a = a; }
                add(b) { return this.a + b; }
            };
            let obj = new Adder(10);
            let result = obj.add(5);
            """)
        assert locals_[VarName("result")] == 15

    def test_named_class_expression_execution(self):
        locals_ = _run_js("""
            const Foo = class MyClass {
                constructor(v) { this.v = v; }
            };
            let obj = new Foo(99);
            let result = obj.v;
            """)
        assert locals_[VarName("result")] == 99


class TestJSIncrementDecrementExecution:
    @covers(JavaScriptFeature.INCREMENT_DECREMENT)
    def test_postfix_increment_mutates_variable(self):
        locals_ = _run_js("let x = 5; x++; let result = x;")
        assert locals_[VarName("result")] == 6

    @covers(JavaScriptFeature.INCREMENT_DECREMENT)
    def test_postfix_decrement_mutates_variable(self):
        locals_ = _run_js("let x = 5; x--; let result = x;")
        assert locals_[VarName("result")] == 4

    @covers(JavaScriptFeature.INCREMENT_DECREMENT)
    def test_prefix_increment_mutates_variable(self):
        locals_ = _run_js("let x = 10; ++x; let result = x;")
        assert locals_[VarName("result")] == 11

    @covers(JavaScriptFeature.INCREMENT_DECREMENT)
    def test_prefix_decrement_mutates_variable(self):
        locals_ = _run_js("let x = 10; --x; let result = x;")
        assert locals_[VarName("result")] == 9

    @covers(JavaScriptFeature.INCREMENT_DECREMENT)
    def test_increment_used_in_expression(self):
        locals_ = _run_js("let x = 3; let result = x + 1; x++; let after = x;")
        assert locals_[VarName("result")] == 4
        assert locals_[VarName("after")] == 4

    @covers(JavaScriptFeature.INCREMENT_DECREMENT)
    def test_postfix_increment_returns_original_value(self):
        locals_ = _run_js("let x = 5; let result = x++; let after = x;")
        assert locals_[VarName("result")] == 5
        assert locals_[VarName("after")] == 6

    @covers(JavaScriptFeature.INCREMENT_DECREMENT)
    def test_postfix_decrement_returns_original_value(self):
        locals_ = _run_js("let x = 5; let result = x--; let after = x;")
        assert locals_[VarName("result")] == 5
        assert locals_[VarName("after")] == 4

    @covers(JavaScriptFeature.INCREMENT_DECREMENT)
    def test_prefix_increment_returns_new_value(self):
        locals_ = _run_js("let x = 5; let result = ++x;")
        assert locals_[VarName("result")] == 6
        assert locals_[VarName("x")] == 6

    @covers(JavaScriptFeature.INCREMENT_DECREMENT)
    def test_prefix_decrement_returns_new_value(self):
        locals_ = _run_js("let x = 5; let result = --x;")
        assert locals_[VarName("result")] == 4
        assert locals_[VarName("x")] == 4


class TestJSSequenceExpressionExecution:
    @covers(JavaScriptFeature.SEQUENCE_EXPRESSION)
    def test_sequence_returns_last_value(self):
        locals_ = _run_js("let result = (1, 2, 3);")
        assert locals_[VarName("result")] == 3

    @covers(JavaScriptFeature.SEQUENCE_EXPRESSION)
    def test_sequence_evaluates_all_side_effects(self):
        locals_ = _run_js(
            "let a = 0; let b = 0; (a = 10, b = 20); let ra = a; let rb = b;"
        )
        assert locals_[VarName("ra")] == 10
        assert locals_[VarName("rb")] == 20

    @covers(JavaScriptFeature.SEQUENCE_EXPRESSION)
    def test_sequence_result_is_last_not_first(self):
        locals_ = _run_js(
            "let x = 0; let result = (x = 1, x = 2, x = 3); let final = x;"
        )
        assert locals_[VarName("result")] == 3
        assert locals_[VarName("final")] == 3


class TestJSWithStatementExecution:
    """with-statement scope extension: object fields shadow enclosing scope (red-dragon-d74s)."""

    @pytest.mark.xfail(
        reason="with-statement scope extension not implemented (red-dragon-d74s)"
    )
    @covers(JavaScriptFeature.WITH_STATEMENT, status=FeatureStatus.UNSUPPORTED)
    def test_with_statement_resolves_fields_from_object(self):
        locals_ = _run_js("""
            let x = 1;
            let obj = { x: 42 };
            with (obj) { let result = x; }
            """)
        assert locals_[VarName("result")] == 42
