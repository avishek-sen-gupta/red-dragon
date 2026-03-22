"""Integration tests for JavaScript frontend execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _run_js(source: str, max_steps: int = 200):
    vm = run(source, language=Language.JAVASCRIPT, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestJSMetaPropertyExecution:
    def test_meta_property_does_not_block(self):
        """Code after new.target usage should execute."""
        locals_ = _run_js("let x = new.target;\nlet y = 42;")
        assert locals_["y"] == 42


class TestJSComputedPropertyNameExecution:
    """computed_property_name in object literals should evaluate the key expression."""

    def test_variable_as_computed_key(self):
        locals_ = _run_js("""
            let key = "name";
            let obj = { [key]: "Alice" };
            let result = obj["name"];
            """)
        assert locals_["result"] == "Alice"

    def test_expression_as_computed_key(self):
        locals_ = _run_js("""
            let obj = { ["a" + "b"]: 42 };
            let result = obj["ab"];
            """)
        assert locals_["result"] == 42

    def test_mixed_computed_and_static_keys(self):
        locals_ = _run_js("""
            let key = "dynamic";
            let obj = { static_key: 1, [key]: 2 };
            let a = obj["static_key"];
            let b = obj["dynamic"];
            """)
        assert locals_["a"] == 1
        assert locals_["b"] == 2


class TestJSOptionalChainExecution:
    """optional_chain (obj?.prop) short-circuits to None on null, accesses on non-null."""

    def test_optional_chain_on_object(self):
        locals_ = _run_js("""
            let obj = { name: "Alice" };
            let result = obj?.name;
            """)
        assert locals_["result"] == "Alice"

    def test_optional_chain_on_null_returns_none(self):
        locals_ = _run_js("""
            let obj = null;
            let result = obj?.name;
            """)
        assert locals_["result"] is None

    def test_optional_chain_nested_short_circuits(self):
        locals_ = _run_js("""
            let outer = { inner: { value: 42 } };
            let result = outer?.inner?.value;
            """)
        assert locals_["result"] == 42


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
        assert locals_["result"] == 42

    def test_anonymous_class_method_call(self):
        locals_ = _run_js("""
            const Adder = class {
                constructor(a) { this.a = a; }
                add(b) { return this.a + b; }
            };
            let obj = new Adder(10);
            let result = obj.add(5);
            """)
        assert locals_["result"] == 15

    def test_named_class_expression_execution(self):
        locals_ = _run_js("""
            const Foo = class MyClass {
                constructor(v) { this.v = v; }
            };
            let obj = new Foo(99);
            let result = obj.v;
            """)
        assert locals_["result"] == 99
