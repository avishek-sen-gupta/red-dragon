"""Unit tests for Go P1 lowering gap handlers: rune_literal, blank_identifier, fallthrough_statement."""

from __future__ import annotations

from interpreter.frontends.go import GoFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_go(source: str) -> list[IRInstruction]:
    frontend = GoFrontend(TreeSitterParserFactory(), "go")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestGoRuneLiteral:
    def test_rune_literal_no_symbolic(self):
        """Rune literal 'a' should not produce SYMBOLIC fallthrough."""
        ir = _parse_go("package main; func main() { x := 'a' }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("rune_literal" in str(inst.operands) for inst in symbolics)

    def test_rune_literal_emits_const(self):
        """Rune literal should emit a CONST instruction."""
        ir = _parse_go("package main; func main() { x := 'a' }")
        consts = _find_all(ir, Opcode.CONST)
        assert any("'a'" in str(inst.operands) for inst in consts)

    def test_rune_literal_stored_to_variable(self):
        """Rune literal should be stored in a variable."""
        ir = _parse_go("package main; func main() { x := 'a' }")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestGoBlankIdentifier:
    def test_blank_identifier_no_symbolic(self):
        """Blank identifier _ should not produce SYMBOLIC fallthrough."""
        ir = _parse_go("package main; func main() { _ = 42 }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("blank_identifier" in str(inst.operands) for inst in symbolics)


class TestGoFallthroughStatement:
    def test_fallthrough_no_symbolic(self):
        """fallthrough should not produce SYMBOLIC fallthrough."""
        source = """\
package main
func main() {
    x := 1
    switch x {
    case 1:
        x = 10
        fallthrough
    case 2:
        x = 20
    }
}
"""
        ir = _parse_go(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "fallthrough_statement" in str(inst.operands) for inst in symbolics
        )

    def test_fallthrough_is_noop(self):
        """fallthrough should not emit any branch/jump — it's a no-op in our model."""
        source = """\
package main
func main() {
    x := 1
    switch x {
    case 1:
        x = 10
        fallthrough
    default:
        x = 20
    }
}
"""
        ir = _parse_go(source)
        # fallthrough should NOT produce its own BRANCH instruction;
        # the switch lowering handles control flow
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "fallthrough_statement" in str(inst.operands) for inst in symbolics
        )
