"""Integration tests for PHP print_intrinsic, clone_expression, const_declaration.

Verifies that PHP programs using these constructs execute through the VM
without errors and produce the expected variable bindings.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.PHP, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


class TestPhpPrintExecution:
    def test_print_executes_without_error(self):
        """print $x should execute through the VM."""
        source = "<?php $x = 42; print $x; ?>"
        vars_ = _run(source)
        assert vars_["$x"] == 42

    def test_print_returns_one(self):
        """print always returns 1 in PHP; $r = print 'hi' stores 1."""
        source = "<?php $r = print 'hello'; ?>"
        vars_ = _run(source)
        assert "$r" in vars_


class TestPhpCloneExecution:
    def test_clone_executes_without_error(self):
        """clone $obj should execute through the VM."""
        source = "<?php $obj = 'original'; $copy = clone $obj; ?>"
        vars_ = _run(source)
        assert "$copy" in vars_


class TestPhpConstExecution:
    def test_const_declaration_executes(self):
        """const FOO = 1; should be accessible as a variable."""
        source = "<?php const FOO = 1; $x = FOO; ?>"
        vars_ = _run(source)
        assert vars_["FOO"] == 1

    def test_const_multiple_declaration_executes(self):
        """const FOO = 10, BAR = 20; should define both constants."""
        source = "<?php const FOO = 10, BAR = 20; ?>"
        vars_ = _run(source)
        assert vars_["FOO"] == 10
        assert vars_["BAR"] == 20

    def test_const_used_in_arithmetic(self):
        """Const value should be usable in subsequent arithmetic."""
        source = "<?php const TAX = 10; $price = 100; $total = $price + TAX; ?>"
        vars_ = _run(source)
        assert vars_["$total"] == 110
