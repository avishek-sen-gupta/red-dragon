"""Integration tests for JavaScript frontend: meta_property."""

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
