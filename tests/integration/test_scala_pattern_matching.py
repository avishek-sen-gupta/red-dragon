"""Integration tests for Scala structural pattern matching -- end-to-end execution."""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_scala(source: str, max_steps: int = 500):
    """Run a Scala program and return frame.local_vars."""
    vm = run(source, language=Language.SCALA, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestScalaCaptureBinding:
    def test_capture_binds_and_returns(self):
        """Capture pattern binds subject and body uses it."""
        locals_ = _run_scala("""\
val x = 5
val r = x match {
  case n => n + 1
}""")
        assert locals_["r"] == 6


class TestScalaAlternativePatternADT:
    def test_alternative_matches_second(self):
        """Alternative pattern 1 | 2 should match when subject is 2."""
        locals_ = _run_scala("""\
val x = 2
val r = x match {
  case 1 | 2 => 10
  case _ => 0
}""")
        assert locals_["r"] == 10


class TestScalaGuardMatch:
    def test_guard_positive(self):
        """Guard `if n > 0` should match when subject is positive."""
        locals_ = _run_scala("""\
val x = 5
val r = x match {
  case n if n > 0 => 1
  case _ => -1
}""")
        assert locals_["r"] == 1

    def test_guard_negative(self):
        """Guard `if n > 0` should NOT match when subject is negative."""
        locals_ = _run_scala("""\
val x = -3
val r = x match {
  case n if n > 0 => 1
  case _ => -1
}""")
        assert locals_["r"] == -1


class TestScalaTupleDestructuring:
    def test_tuple_destructuring(self):
        """Tuple destructuring (a, b) => a + b."""
        locals_ = _run_scala("""\
val pair = (3, 4)
val r = pair match {
  case (a, b) => a + b
}""")
        assert locals_["r"] == 7


class TestScalaCaseClassPattern:
    @pytest.mark.xfail(
        reason="Case class isinstance not yet wired for Scala match", strict=False
    )
    def test_case_class_match(self):
        """Case class pattern matching with field extraction."""
        locals_ = _run_scala("""\
case class Box(value: Int)
val b = new Box(42)
val r = b match {
  case Box(v) => v + 1
}""")
        assert locals_["r"] == 43


class TestScalaTypedPattern:
    def test_typed_pattern(self):
        """Typed pattern `case i: Int => i + 1`."""
        locals_ = _run_scala("""\
val x: Any = 5
val r = x match {
  case i: Int => i + 1
  case _ => 0
}""")
        assert locals_["r"] == 6


class TestScalaTypedPatternWithGuard:
    def test_typed_pattern_with_guard(self):
        """Typed pattern combined with a guard: `case i: Int if i > 10 => i * 2`."""
        locals_ = _run_scala("""\
val x: Any = 15
val r = x match {
  case i: Int if i > 10 => i * 2
  case i: Int => i
  case _ => 0
}""")
        assert locals_["r"] == 30


class TestScalaMultipleAlternativePatterns:
    def test_multiple_alternatives_third_arm(self):
        """Three-arm alternative pattern; subject 7 falls through to wildcard arm."""
        locals_ = _run_scala("""\
val x = 7
val r = x match {
  case 1 | 2 | 3 => 1
  case 4 | 5 | 6 => 2
  case _ => 3
}""")
        assert locals_["r"] == 3


class TestScalaWildcardInTuple:
    def test_wildcard_in_tuple(self):
        """Wildcard `_` in tuple position discards first element, binds second."""
        locals_ = _run_scala("""\
val pair = (3, 4)
val r = pair match {
  case (_, b) => b
}""")
        assert locals_["r"] == 4
