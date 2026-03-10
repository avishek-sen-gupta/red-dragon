"""Integration tests for Ruby rescue_modifier -- end-to-end VM execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_ruby(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.RUBY, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


class TestRubyRescueModifierExecution:
    def test_rescue_modifier_no_error(self):
        """When the expression succeeds, rescue fallback is not used."""
        source = """\
x = 42 rescue 0
"""
        local_vars = _run_ruby(source)
        assert local_vars["x"] == 42
