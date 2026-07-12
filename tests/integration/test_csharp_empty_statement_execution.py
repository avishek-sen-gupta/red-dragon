"""Integration test: C# empty_statement (bare `;`) through the full VM pipeline.

Verifies that empty statements do not interfere with program execution
and that the VM completes without errors.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.var_name import VarName
from tests.integration.exec_helpers import run_locals


def _run_csharp(source: str, max_steps: int = 500) -> dict:
    return run_locals(source, Language.CSHARP, max_steps)


class TestCSharpEmptyStatementExecution:
    def test_empty_statements_do_not_affect_execution(self):
        """Program with empty statements should execute identically to one without."""
        source = """\
int x = 10;
;
int y = x + 5;
;
"""
        vars_ = _run_csharp(source)
        assert vars_[VarName("x")] == 10
        assert vars_[VarName("y")] == 15

    def test_empty_statement_in_method(self):
        """Empty statement inside a method body should not affect VM execution."""
        source = """\
class C {
    int Compute(int a, int b) {
        ;
        int result = a + b;
        ;
        return result;
    }
}

C c = new C();
int r = c.Compute(3, 4);
"""
        vars_ = _run_csharp(source)
        assert vars_[VarName("r")] == 7
