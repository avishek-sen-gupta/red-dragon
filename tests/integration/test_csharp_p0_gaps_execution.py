"""Integration tests for C# P0 gaps -- end-to-end VM execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.var_name import VarName


def _run_csharp(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.CSHARP, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


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
        assert local_vars[VarName("x")] == 1, "goto should skip x = 99"
        assert local_vars[VarName("y")] == 2

    def test_goto_label_interaction(self):
        """goto should jump to a defined label and execute code after it."""
        source = """\
int x = 1;
goto done;
x = 99;
done:
int y = x + 10;
"""
        local_vars = _run_csharp(source)
        assert local_vars[VarName("x")] == 1, "goto should skip x = 99"
        assert local_vars[VarName("y")] == 11, "code after label should use original x"

    def test_goto_backward_jump(self):
        """goto can jump backward to create a loop-like construct."""
        source = """\
int x = 0;
start:
x = x + 1;
if (x < 3) goto start;
int y = x;
"""
        local_vars = _run_csharp(source)
        assert local_vars[VarName("y")] == 3


class TestCSharpLabeledStatementExecution:
    def test_labeled_statement_executes_body(self):
        """Statement after label should execute normally."""
        source = """\
int x = 10;
myLabel:
int y = x + 5;
"""
        local_vars = _run_csharp(source)
        assert local_vars[VarName("y")] == 15
