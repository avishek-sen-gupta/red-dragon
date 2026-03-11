"""Integration tests for TypeScript frontend: type_assertion."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_ts(source: str, max_steps: int = 200):
    vm = run(source, language=Language.TYPESCRIPT, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


class TestTSTypeAssertionExecution:
    def test_type_assertion_passes_value_through(self):
        """<number>x should pass the value of x through."""
        locals_ = _run_ts("let x = 42;\nlet y = <number>x;")
        assert locals_["y"] == 42

    def test_type_assertion_string(self):
        """<string>val should pass string value through."""
        locals_ = _run_ts('let s = "hello";\nlet t = <string>s;')
        assert locals_["t"] == "hello"
