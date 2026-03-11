"""Integration tests for P1 lowering gaps: Scala (2), Kotlin (1), C# (2)."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_scala(source: str, max_steps: int = 200):
    vm = run(source, language=Language.SCALA, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


def _run_kotlin(source: str, max_steps: int = 200):
    vm = run(source, language=Language.KOTLIN, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


def _run_csharp(source: str, max_steps: int = 200):
    vm = run(source, language=Language.CSHARP, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


# ── Scala: val_declaration ───────────────────────────────────────


class TestScalaValDeclarationExecution:
    def test_code_after_val_decl_executes(self):
        """Code after abstract val declaration should execute."""
        locals_ = _run_scala("val y = 42")
        assert locals_["y"] == 42


# ── Scala: alternative_pattern ───────────────────────────────────


class TestScalaAlternativePatternExecution:
    def test_alternative_pattern_match(self):
        """match with alternative pattern should execute."""
        locals_ = _run_scala("""\
val x = 1
val r = x match {
  case 1 | 2 => 10
  case _ => 0
}""")
        assert locals_["r"] == 10

    def test_alternative_pattern_no_match(self):
        """match with non-matching alternative should fall through to default."""
        locals_ = _run_scala("""\
val x = 5
val r = x match {
  case 1 | 2 => 10
  case _ => 0
}""")
        assert locals_["r"] == 0


# ── Kotlin: setter ───────────────────────────────────────────────


class TestKotlinSetterExecution:
    def test_code_after_class_with_setter_executes(self):
        """Code after class with property setter should execute."""
        locals_ = _run_kotlin("""\
class Foo {
  var x: Int = 0
    set(value) { field = value }
}
val y = 42""")
        assert locals_["y"] == 42


# ── C#: file_scoped_namespace_declaration ────────────────────────


class TestCSharpFileScopedNamespaceExecution:
    def test_class_in_file_scoped_ns_executes(self):
        """Class inside file-scoped namespace should be accessible."""
        locals_ = _run_csharp("""\
namespace Foo;
int x = 42;""")
        assert locals_["x"] == 42


# ── C#: range_expression ─────────────────────────────────────────


class TestCSharpRangeExpressionExecution:
    def test_range_does_not_block(self):
        """Code after range expression should execute."""
        locals_ = _run_csharp("var r = 0..5;\nvar x = 42;")
        assert locals_["x"] == 42
