"""Integration tests for Rust unit_expression -- end-to-end execution.

Verifies that `()` (unit value) is lowered and executed without errors.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.var_name import VarName


def _run_rust(source: str, max_steps: int = 200):
    """Run a Rust program and return (vm, frame.local_vars)."""
    vm = run(source, language=Language.RUST, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestRustUnitExpressionExecution:
    def test_unit_expression_assigned(self):
        """let x = (); should store the unit value."""
        _, local_vars = _run_rust("let x = ();")
        assert local_vars[VarName("x")] == "()"

    def test_unit_expression_in_block(self):
        """Unit expression as last expression in a block."""
        _, local_vars = _run_rust("""\
let a = 42;
let x = ();
""")
        assert local_vars[VarName("a")] == 42
        assert local_vars[VarName("x")] == "()"

    def test_unit_as_function_return(self):
        """Function returning () should return unit."""
        _, local_vars = _run_rust("""\
fn do_nothing() {
    ()
}
let x = do_nothing();
let y = 42;
""")
        assert local_vars[VarName("y")] == 42
        assert local_vars[VarName("x")] == "()"
