"""Unit tests for Java P1 lowering gap: hex_floating_point_literal."""

from __future__ import annotations

from interpreter.frontends.java import JavaFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_java(source: str) -> list[IRInstruction]:
    frontend = JavaFrontend(TreeSitterParserFactory(), "java")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestJavaHexFloatingPointLiteral:
    def test_hex_float_no_symbolic(self):
        """0x1.0p10 should not produce SYMBOLIC fallthrough."""
        ir = _parse_java("class T { void f() { double x = 0x1.0p10; } }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "hex_floating_point_literal" in str(inst.operands) for inst in symbolics
        )

    def test_hex_float_emits_const(self):
        """Hex floating point literal should emit a CONST instruction."""
        ir = _parse_java("class T { void f() { double x = 0x1.0p10; } }")
        consts = _find_all(ir, Opcode.CONST)
        assert any("0x1.0p10" in str(inst.operands) for inst in consts)

    def test_hex_float_stored(self):
        """Hex float should be stored to a variable."""
        ir = _parse_java("class T { void f() { double x = 0x1.0p10; } }")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
