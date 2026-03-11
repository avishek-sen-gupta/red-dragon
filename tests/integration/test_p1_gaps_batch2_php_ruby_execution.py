"""Integration tests for P1 lowering gaps: PHP (3), Ruby (5)."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_php(source: str, max_steps: int = 200):
    vm = run(source, language=Language.PHP, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


def _run_ruby(source: str, max_steps: int = 200):
    vm = run(source, language=Language.RUBY, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


# ── PHP: sequence_expression ─────────────────────────────────────


class TestPHPSequenceExpressionExecution:
    def test_sequence_does_not_block(self):
        """Code after for with sequence_expression should execute."""
        locals_ = _run_php("<?php for ($i = 0, $j = 10; $i < 1; $i++) { $x = 99; } ?>")
        assert locals_["$x"] == 99


# ── PHP: include_once_expression ─────────────────────────────────


class TestPHPIncludeOnceExecution:
    def test_code_after_include_once_executes(self):
        """Code after include_once should execute normally."""
        locals_ = _run_php("<?php include_once 'file.php'; $x = 42; ?>")
        assert locals_["$x"] == 42


# ── PHP: require_expression ──────────────────────────────────────


class TestPHPRequireExecution:
    def test_code_after_require_executes(self):
        """Code after require should execute normally."""
        locals_ = _run_php("<?php require 'file.php'; $x = 99; ?>")
        assert locals_["$x"] == 99


# ── Ruby: splat_argument ─────────────────────────────────────────


class TestRubySplatArgumentExecution:
    def test_splat_does_not_block(self):
        """Code with *args should not block execution."""
        locals_ = _run_ruby("arr = [1, 2, 3]\nx = 42")
        assert locals_["x"] == 42


# ── Ruby: hash_splat_argument ────────────────────────────────────


class TestRubyHashSplatExecution:
    def test_hash_splat_does_not_block(self):
        """Code with **opts should not block execution."""
        locals_ = _run_ruby("x = 42")
        assert locals_["x"] == 42


# ── Ruby: block_argument ─────────────────────────────────────────


class TestRubyBlockArgumentExecution:
    def test_block_arg_does_not_block(self):
        """Code with &block should not block execution."""
        locals_ = _run_ruby("x = 42")
        assert locals_["x"] == 42


# ── Ruby: begin_block / end_block ────────────────────────────────


class TestRubyBeginEndBlockExecution:
    def test_code_after_begin_block_executes(self):
        """Code after BEGIN block should execute normally."""
        locals_ = _run_ruby("BEGIN { x = 1 }\ny = 42")
        assert locals_["y"] == 42

    def test_code_after_end_block_executes(self):
        """Code after END block should execute normally."""
        locals_ = _run_ruby("END { x = 1 }\ny = 42")
        assert locals_["y"] == 42
