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
        """Code with *args (splat argument) should not block execution."""
        source = """\
arr = [1, 2, 3]
def add(a, b, c)
  return a + b + c
end
answer = add(*arr)
"""
        locals_ = _run_ruby(source)
        assert locals_["answer"] == 6


class TestRubyHashSplatExecution:
    def test_hash_splat_does_not_block(self):
        """Code with **opts (hash splat argument) should not block execution."""
        source = """\
opts = {a: 1}
def greet(a)
  return 42
end
answer = greet(**opts)
"""
        locals_ = _run_ruby(source)
        assert locals_["answer"] == 42


class TestRubyBlockArgumentExecution:
    def test_block_arg_does_not_block(self):
        """Code with &block (block argument) should not block execution."""
        source = """\
my_proc = Proc.new { 99 }
def run_it(f)
  return 42
end
answer = run_it(&my_proc)
"""
        locals_ = _run_ruby(source)
        assert locals_["answer"] == 42


class TestRubyBeginEndBlockExecution:
    def test_code_after_begin_block_executes(self):
        """Code after BEGIN block should execute normally."""
        locals_ = _run_ruby("BEGIN { x = 1 }\ny = 42")
        assert locals_["y"] == 42

    def test_code_after_end_block_executes(self):
        """Code after END block should execute normally."""
        locals_ = _run_ruby("END { x = 1 }\ny = 42")
        assert locals_["y"] == 42
