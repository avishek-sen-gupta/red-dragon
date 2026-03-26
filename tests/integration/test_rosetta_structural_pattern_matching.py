"""Cross-language Rosetta test: structural pattern matching produces identical results.

Algorithm: classify a number.
  x = 2 →  x == 1  → "one"
            x in {2, 3} → "small"
            otherwise   → "other"

Expected result for all 5 languages: result == "small"
"""

from __future__ import annotations

import pytest

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _run(source: str, language: Language, max_steps: int = 500) -> dict:
    vm = run(source, language=language, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestRosettaPatternMatchingClassifyNumber:
    """Same classify-number algorithm in 5 languages — all must produce 'small'."""

    def test_python(self):
        """Python match/case with or-pattern (2 | 3)."""
        source = """\
x = 2
result = ""
match x:
    case 1:
        result = "one"
    case 2 | 3:
        result = "small"
    case _:
        result = "other"
"""
        local_vars = _run(source, Language.PYTHON)
        assert local_vars[VarName("result")] == "small"

    def test_csharp(self):
        """C# switch expression with separate arms for 2 and 3."""
        source = """\
class M {
    static string Classify(int x) {
        return x switch {
            1 => "one",
            2 => "small",
            3 => "small",
            _ => "other"
        };
    }
    static string result = Classify(2);
}
"""
        local_vars = _run(source, Language.CSHARP, max_steps=1000)
        assert local_vars[VarName("result")] == "small"

    def test_rust(self):
        """Rust match with or-pattern (2 | 3)."""
        source = """\
let x = 2;
let result = match x {
    1 => "one",
    2 | 3 => "small",
    _ => "other",
};
"""
        local_vars = _run(source, Language.RUST)
        assert local_vars[VarName("result")] == "small"

    def test_scala(self):
        """Scala match with alternative pattern (2 | 3)."""
        source = """\
val x = 2
val result = x match {
  case 1 => "one"
  case 2 | 3 => "small"
  case _ => "other"
}"""
        local_vars = _run(source, Language.SCALA)
        assert local_vars[VarName("result")] == "small"

    def test_kotlin(self):
        """Kotlin when expression with separate arms for 2 and 3."""
        source = """\
val x = 2
val result = when(x) {
    1 -> "one"
    2 -> "small"
    3 -> "small"
    else -> "other"
}
"""
        local_vars = _run(source, Language.KOTLIN)
        assert local_vars[VarName("result")] == "small"

    def test_ruby(self):
        """Ruby case/in with separate arms for 2 and 3 (or-patterns not used)."""
        source = """\
x = 2
result = case x
  in 1 then "one"
  in 2 then "small"
  in 3 then "small"
  else "other"
end
"""
        local_vars = _run(source, Language.RUBY)
        assert local_vars[VarName("result")] == "small"
