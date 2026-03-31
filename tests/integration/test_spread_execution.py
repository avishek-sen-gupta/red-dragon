"""Integration tests for spread/splat argument unpacking across all 5 languages."""

from __future__ import annotations

import pytest

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint


def _run(source: str, language: Language, max_steps: int = 500) -> dict:
    vm = run(
        source,
        language=language,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestPythonSpread:
    def test_splat_unpacks_list_into_args(self):
        """Python *args should unpack list elements as individual arguments."""
        vars_ = _run(
            """\
def add(a, b, c):
    return a + b + c
arr = [1, 2, 3]
answer = add(*arr)
""",
            Language.PYTHON,
        )
        assert vars_[VarName("answer")] == 6


class TestJavaScriptSpread:
    def test_spread_unpacks_array_into_args(self):
        """JavaScript ...arr should unpack array elements as individual arguments."""
        vars_ = _run(
            """\
function add(a, b, c) { return a + b + c; }
var arr = [1, 2, 3];
var answer = add(...arr);
""",
            Language.JAVASCRIPT,
        )
        assert vars_[VarName("answer")] == 6


class TestRubySpread:
    def test_splat_unpacks_array_into_args(self):
        """Ruby *arr should unpack array elements as individual arguments."""
        vars_ = _run(
            """\
def add(a, b, c)
  return a + b + c
end
arr = [1, 2, 3]
answer = add(*arr)
""",
            Language.RUBY,
        )
        assert vars_[VarName("answer")] == 6


class TestPHPSpread:
    def test_splat_unpacks_array_into_args(self):
        """PHP ...$arr should unpack array elements as individual arguments."""
        vars_ = _run(
            """\
<?php
function add($a, $b, $c) { return $a + $b + $c; }
$arr = [1, 2, 3];
$answer = add(...$arr);
""",
            Language.PHP,
        )
        assert vars_[VarName("$answer")] == 6


class TestKotlinSpread:
    def test_spread_unpacks_array_into_args(self):
        """Kotlin *arr should unpack array elements as individual arguments."""
        vars_ = _run(
            """\
fun add(a: Int, b: Int, c: Int): Int { return a + b + c }
val arr = intArrayOf(1, 2, 3)
val answer = add(*arr)
""",
            Language.KOTLIN,
        )
        assert vars_[VarName("answer")] == 6
