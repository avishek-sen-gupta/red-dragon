"""Integration tests for Rust unit_expression -- end-to-end execution.

Verifies that `()` (unit value) is lowered and executed without errors.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_rust(source: str, max_steps: int = 200):
    """Run a Rust program and return (vm, frame.local_vars)."""
    vm = run(source, language=Language.RUST, max_steps=max_steps)
    return vm, dict(vm.call_stack[0].local_vars)


class TestRustUnitExpressionExecution:
    def test_unit_expression_assigned(self):
        """let x = (); should execute without errors."""
        _, local_vars = _run_rust("let x = ();")
        assert "x" in local_vars

    def test_unit_expression_in_block(self):
        """Unit expression as last expression in a block."""
        _, local_vars = _run_rust("""\
let a = 42;
let x = ();
""")
        assert local_vars["a"] == 42
        assert "x" in local_vars
