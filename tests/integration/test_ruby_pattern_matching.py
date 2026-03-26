"""Integration tests for Ruby case/in pattern matching."""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _run_ruby(source: str, max_steps: int = 500):
    vm = run(source, language=Language.RUBY, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestLiteralMatch:
    def test_literal_int_match(self):
        local_vars = _run_ruby("""\
x = 2
r = case x
  in 1 then 10
  in 2 then 20
  else 0
end
""")
        assert local_vars[VarName("r")] == 20

    def test_else_fallback(self):
        local_vars = _run_ruby("""\
x = 99
r = case x
  in 1 then 10
  else 0
end
""")
        assert local_vars[VarName("r")] == 0


class TestWildcardMatch:
    def test_wildcard_catches_all(self):
        local_vars = _run_ruby("""\
x = 5
r = case x
  in _ then 42
end
""")
        assert local_vars[VarName("r")] == 42


class TestAlternativeMatch:
    def test_alternative_pattern(self):
        local_vars = _run_ruby("""\
x = 3
r = case x
  in 1 | 2 | 3 then 10
  else 0
end
""")
        assert local_vars[VarName("r")] == 10


class TestArrayDestructuring:
    def test_array_destructuring(self):
        local_vars = _run_ruby("""\
arr = [1, 2]
r = case arr
  in [a, b] then a + b
  else 0
end
""")
        assert local_vars[VarName("r")] == 3
