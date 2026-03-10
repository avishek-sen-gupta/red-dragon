"""Integration tests for PHP P1 lowering gaps: error_suppression, exit, declare, unset.

Verifies end-to-end execution through the full parse -> lower -> execute pipeline.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_php(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.PHP, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


class TestPhpErrorSuppressionExecution:
    def test_error_suppression_executes(self):
        """@strlen('hello') should execute the inner call."""
        vars_ = _run_php("<?php $x = @strlen('hello'); $y = 42; ?>")
        assert vars_["$y"] == 42

    def test_error_suppression_result_stored(self):
        """@expr result should be stored in the variable."""
        vars_ = _run_php("<?php $x = @strlen('hello'); ?>")
        assert "$x" in vars_


class TestPhpExitStatementExecution:
    def test_exit_does_not_crash(self):
        """exit(0) should not crash the VM."""
        vars_ = _run_php("<?php $x = 42; exit(0); ?>")
        assert vars_["$x"] == 42


class TestPhpDeclareStatementExecution:
    def test_declare_does_not_crash(self):
        """declare(strict_types=1) should not crash the VM."""
        vars_ = _run_php("<?php declare(strict_types=1); $x = 42; ?>")
        assert vars_["$x"] == 42


class TestPhpUnsetStatementExecution:
    def test_unset_does_not_crash(self):
        """unset($x) should not crash the VM."""
        vars_ = _run_php("<?php $x = 42; unset($x); $y = 10; ?>")
        assert vars_["$y"] == 10

    def test_code_after_unset_executes(self):
        """Code after unset should execute normally."""
        vars_ = _run_php("<?php $a = 1; $b = 2; unset($a); $c = $b + 3; ?>")
        assert vars_["$c"] == 5
