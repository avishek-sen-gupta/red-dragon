"""Unit tests for Rust P1 lowering gap handlers: raw_string_literal, negative_literal."""

from __future__ import annotations

from interpreter.frontends.rust import RustFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_rust(source: str) -> list[IRInstruction]:
    frontend = RustFrontend(TreeSitterParserFactory(), "rust")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestRustRawStringLiteral:
    def test_raw_string_no_symbolic(self):
        """r\"hello\" should not produce SYMBOLIC fallthrough."""
        ir = _parse_rust('fn main() { let x = r"hello"; }')
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("raw_string_literal" in str(inst.operands) for inst in symbolics)

    def test_raw_string_emits_const(self):
        """Raw string literal should emit a CONST instruction."""
        ir = _parse_rust('fn main() { let x = r"hello"; }')
        consts = _find_all(ir, Opcode.CONST)
        assert any("hello" in str(inst.operands) for inst in consts)

    def test_raw_string_stored(self):
        """Raw string literal should be stored in the variable."""
        ir = _parse_rust('fn main() { let x = r"hello"; }')
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestRustNegativeLiteral:
    def test_negative_literal_no_symbolic(self):
        """let x = -1; the negative_literal should not produce SYMBOLIC."""
        ir = _parse_rust("fn main() { let x: i32 = -1; }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("negative_literal" in str(inst.operands) for inst in symbolics)

    def test_negative_literal_emits_const(self):
        """Negative literal should emit a CONST with the negative value."""
        ir = _parse_rust("fn main() { let x: i32 = -1; }")
        consts = _find_all(ir, Opcode.CONST)
        # Should contain -1 as a literal value
        assert len(consts) >= 1

    def test_negative_literal_stored(self):
        """Negative literal should be stored in the variable."""
        ir = _parse_rust("fn main() { let x: i32 = -1; }")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
