"""Integration tests for Ruby rescue_modifier -- end-to-end VM execution."""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _run_ruby(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.RUBY, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestRubyRescueModifierExecution:
    def test_rescue_modifier_no_error(self):
        """When the expression succeeds, rescue fallback is not used."""
        source = """\
x = 42 rescue 0
"""
        local_vars = _run_ruby(source)
        assert local_vars[VarName("x")] == 42

    def test_rescue_modifier_with_raise(self):
        """When the expression raises, rescue fallback should be used."""
        source = """\
x = (raise "boom") rescue 99
"""
        local_vars = _run_ruby(source)
        assert local_vars[VarName("x")] == 99
