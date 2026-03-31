"""Integration tests for Ruby frontend: splat_argument, hash_splat_argument, block_argument, begin_block, end_block."""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint


def _run_ruby(source: str, max_steps: int = 200):
    vm = run(
        source,
        language=Language.RUBY,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
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
        assert locals_[VarName("answer")] == 6


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
        assert locals_[VarName("answer")] == 42


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
        assert locals_[VarName("answer")] == 42


class TestRubyBeginEndBlockExecution:
    def test_code_after_begin_block_executes(self):
        """Code after BEGIN block should execute normally."""
        locals_ = _run_ruby("BEGIN { x = 1 }\ny = 42")
        assert locals_[VarName("y")] == 42

    def test_code_after_end_block_executes(self):
        """Code after END block should execute normally."""
        locals_ = _run_ruby("END { x = 1 }\ny = 42")
        assert locals_[VarName("y")] == 42


class TestRubySingletonMethodDispatch:
    def test_class_method_returns_correct_value(self):
        """Util.square(5) on a def self.square method should return 25."""
        locals_ = _run_ruby(
            """\
class Util
  def self.square(x)
    x * x
  end
end
result = Util.square(5)
""",
            max_steps=500,
        )
        assert locals_[VarName("result")] == 25

    def test_class_method_with_multiple_args(self):
        """Class method with multiple arguments should dispatch correctly."""
        locals_ = _run_ruby(
            """\
class Math
  def self.add(a, b)
    a + b
  end
end
result = Math.add(3, 4)
""",
            max_steps=500,
        )
        assert locals_[VarName("result")] == 7

    def test_class_method_alongside_instance_method(self):
        """Class and instance methods on same class should both dispatch."""
        locals_ = _run_ruby(
            """\
class Calc
  def self.square(x)
    x * x
  end
  def initialize(val)
    @val = val
  end
  def double
    @val * 2
  end
end
sq = Calc.square(4)
c = Calc.new(3)
dbl = c.double
""",
            max_steps=500,
        )
        assert locals_[VarName("sq")] == 16
        assert locals_[VarName("dbl")] == 6
