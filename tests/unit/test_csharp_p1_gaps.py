"""Unit tests for C# P1 lowering gaps: default_expression, sizeof_expression, checked_expression."""

from __future__ import annotations

from interpreter.frontends.csharp import CSharpFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_csharp(source: str) -> list[IRInstruction]:
    frontend = CSharpFrontend(TreeSitterParserFactory(), "csharp")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestCSharpDefaultExpression:
    def test_default_no_symbolic(self):
        """default should not produce SYMBOLIC fallthrough."""
        ir = _parse_csharp("int x = default;")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("default_expression" in str(inst.operands) for inst in symbolics)

    def test_default_emits_const(self):
        """default expression should emit a CONST."""
        ir = _parse_csharp("int x = default;")
        consts = _find_all(ir, Opcode.CONST)
        assert len(consts) >= 1

    def test_default_stored(self):
        """default expression should be stored to a variable."""
        ir = _parse_csharp("int x = default;")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestCSharpSizeofExpression:
    def test_sizeof_no_symbolic(self):
        """sizeof(int) should not produce SYMBOLIC fallthrough."""
        ir = _parse_csharp("int x = sizeof(int);")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("sizeof_expression" in str(inst.operands) for inst in symbolics)

    def test_sizeof_emits_const(self):
        """sizeof(int) should emit a CONST."""
        ir = _parse_csharp("int x = sizeof(int);")
        consts = _find_all(ir, Opcode.CONST)
        assert len(consts) >= 1


class TestCSharpCheckedExpression:
    def test_checked_no_symbolic(self):
        """checked(1 + 2) should not produce SYMBOLIC fallthrough."""
        ir = _parse_csharp("int x = checked(1 + 2);")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("checked_expression" in str(inst.operands) for inst in symbolics)

    def test_checked_lowers_inner_expr(self):
        """checked(1 + 2) should lower the inner expression (1 + 2)."""
        ir = _parse_csharp("int x = checked(1 + 2);")
        binops = _find_all(ir, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
