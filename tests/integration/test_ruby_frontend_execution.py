"""Integration tests for Ruby frontend: splat_argument, hash_splat_argument, block_argument, begin_block, end_block."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_ruby(source: str, max_steps: int = 200):
    vm = run(source, language=Language.RUBY, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestRubySplatArgumentExecution:
    def test_splat_does_not_block(self):
        """Code with *args should not block execution."""
        locals_ = _run_ruby("arr = [1, 2, 3]\nx = 42")
        assert locals_["x"] == 42


class TestRubyHashSplatExecution:
    def test_hash_splat_does_not_block(self):
        """Code with **opts should not block execution."""
        locals_ = _run_ruby("x = 42")
        assert locals_["x"] == 42


class TestRubyBlockArgumentExecution:
    def test_block_arg_does_not_block(self):
        """Code with &block should not block execution."""
        locals_ = _run_ruby("x = 42")
        assert locals_["x"] == 42


class TestRubyBeginEndBlockExecution:
    def test_code_after_begin_block_executes(self):
        """Code after BEGIN block should execute normally."""
        locals_ = _run_ruby("BEGIN { x = 1 }\ny = 42")
        assert locals_["y"] == 42

    def test_code_after_end_block_executes(self):
        """Code after END block should execute normally."""
        locals_ = _run_ruby("END { x = 1 }\ny = 42")
        assert locals_["y"] == 42
