"""Unit tests for P1 lowering gaps: Scala (2), Kotlin (1), C# (2)."""

from __future__ import annotations

from interpreter.frontends.scala import ScalaFrontend
from interpreter.frontends.kotlin import KotlinFrontend
from interpreter.frontends.csharp import CSharpFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


# ── Scala: val_declaration ───────────────────────────────────────


class TestScalaValDeclaration:
    def test_val_declaration_no_symbolic(self):
        """val x: Int (no body) should not produce SYMBOLIC."""
        frontend = ScalaFrontend(TreeSitterParserFactory(), "scala")
        ir = frontend.lower(b"trait Foo { val x: Int }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("val_declaration" in str(inst.operands) for inst in symbolics)

    def test_val_declaration_does_not_block(self):
        """Code after val declaration should be lowered."""
        frontend = ScalaFrontend(TreeSitterParserFactory(), "scala")
        ir = frontend.lower(b"trait Foo { val x: Int }\nval y = 42")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)


# ── Scala: alternative_pattern ───────────────────────────────────


class TestScalaAlternativePattern:
    def test_alternative_pattern_no_symbolic(self):
        """case A | B => should not produce SYMBOLIC."""
        frontend = ScalaFrontend(TreeSitterParserFactory(), "scala")
        code = b"""\
val x = 1
x match {
  case 1 | 2 => val r = 10
  case _ => val r = 0
}"""
        ir = frontend.lower(code)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "alternative_pattern" in str(inst.operands) for inst in symbolics
        )


# ── Kotlin: setter ───────────────────────────────────────────────


class TestKotlinSetter:
    def test_setter_no_symbolic(self):
        """Property setter should not produce SYMBOLIC."""
        frontend = KotlinFrontend(TreeSitterParserFactory(), "kotlin")
        code = b"""\
class Foo {
  var x: Int = 0
    set(value) { field = value }
}
val y = 42"""
        ir = frontend.lower(code)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("setter" in str(inst.operands) for inst in symbolics)

    def test_setter_does_not_block(self):
        """Code after class with setter should be lowered."""
        frontend = KotlinFrontend(TreeSitterParserFactory(), "kotlin")
        code = b"""\
class Foo {
  var x: Int = 0
    set(value) { field = value }
}
val y = 42"""
        ir = frontend.lower(code)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)


# ── C#: file_scoped_namespace_declaration ────────────────────────


class TestCSharpFileScopedNamespace:
    def test_file_scoped_ns_no_symbolic(self):
        """namespace Foo; should not produce SYMBOLIC."""
        frontend = CSharpFrontend(TreeSitterParserFactory(), "csharp")
        code = b"""\
namespace Foo;
class Bar {
  int x = 42;
}"""
        ir = frontend.lower(code)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "file_scoped_namespace_declaration" in str(inst.operands)
            for inst in symbolics
        )

    def test_file_scoped_ns_body_lowered(self):
        """Declarations inside file-scoped namespace should be lowered."""
        frontend = CSharpFrontend(TreeSitterParserFactory(), "csharp")
        code = b"""\
namespace Foo;
class Bar {
  int x = 42;
}"""
        ir = frontend.lower(code)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("Bar" in inst.operands for inst in stores)


# ── C#: range_expression ─────────────────────────────────────────


class TestCSharpRangeExpression:
    def test_range_no_symbolic(self):
        """0..5 should not produce SYMBOLIC."""
        frontend = CSharpFrontend(TreeSitterParserFactory(), "csharp")
        ir = frontend.lower(b"var r = 0..5;")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("range_expression" in str(inst.operands) for inst in symbolics)

    def test_range_produces_call(self):
        """0..5 should produce a CALL_FUNCTION for range."""
        frontend = CSharpFrontend(TreeSitterParserFactory(), "csharp")
        ir = frontend.lower(b"var r = 0..5;")
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("range" in inst.operands for inst in calls)
