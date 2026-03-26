"""Integration test: C# empty_statement (bare `;`) through the full VM pipeline.

Verifies that empty statements do not interfere with program execution
and that the VM completes without errors.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.var_name import VarName


def _run_csharp(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.CSHARP, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


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
