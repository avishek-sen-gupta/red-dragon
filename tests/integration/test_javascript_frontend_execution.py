"""Integration tests for JavaScript frontend execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_js(source: str, max_steps: int = 200):
    vm = run(source, language=Language.JAVASCRIPT, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


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
    """optional_chain (obj?.prop) should not produce SYMBOLIC and should execute."""

    def test_optional_chain_on_object(self):
        locals_ = _run_js("""
            let obj = { name: "Alice" };
            let result = obj?.name;
            """)
        assert locals_["result"] == "Alice"
