"""Integration tests for C# P0 gaps -- end-to-end VM execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_csharp(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.CSHARP, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


class TestCSharpGotoExecution:
    def test_goto_skips_statements(self):
        """goto should jump past intermediate statements."""
        source = """\
int x = 1;
goto skip;
x = 99;
skip:
int y = 2;
"""
        local_vars = _run_csharp(source)
        assert local_vars["x"] == 1, "goto should skip x = 99"
        assert local_vars["y"] == 2


class TestCSharpLabeledStatementExecution:
    def test_labeled_statement_executes_body(self):
        """Statement after label should execute normally."""
        source = """\
int x = 10;
myLabel:
int y = x + 5;
"""
        local_vars = _run_csharp(source)
        assert local_vars["y"] == 15
