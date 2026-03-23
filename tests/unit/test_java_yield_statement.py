"""Unit tests for Java yield_statement in switch expressions (P0 gap)."""

from __future__ import annotations

from interpreter.frontends.java import JavaFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_java(source: str) -> list[IRInstruction]:
    frontend = JavaFrontend(TreeSitterParserFactory(), "java")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestJavaYieldStatement:
    """Java 14+ yield in switch expression block arms."""

    def test_yield_no_unsupported_symbolic(self):
        """yield_statement should not produce unsupported SYMBOLIC fallthrough."""
        source = """\
class M {
    int m(int x) {
        return switch (x) {
            case 1 -> { yield 10; }
            default -> { yield 0; }
        };
    }
}
"""
        instructions = _parse_java(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "unsupported:" in str(inst.operands) for inst in symbolics
        ), f"Found unsupported SYMBOLIC: {[s for s in symbolics if 'unsupported:' in str(s.operands)]}"

    def test_yield_stores_to_switch_result(self):
        """yield inside switch expression should STORE_VAR to __switch_result."""
        source = """\
class M {
    int m(int x) {
        return switch (x) {
            case 1 -> { yield 42; }
            default -> { yield 0; }
        };
    }
}
"""
        instructions = _parse_java(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any(
            "__switch_result" in str(inst.operands[0]) for inst in stores
        ), "yield should store to __switch_result variable"

    def test_yield_emits_branch_to_end(self):
        """yield should branch to switch end label after storing."""
        source = """\
class M {
    int m(int x) {
        return switch (x) {
            case 1 -> { yield 42; }
            default -> { yield 0; }
        };
    }
}
"""
        instructions = _parse_java(source)
        branches = _find_all(instructions, Opcode.BRANCH)
        assert any(
            "switch_end" in inst.label.value for inst in branches
        ), "yield should branch to switch_end"

    def test_yield_with_expression(self):
        """yield with a complex expression should lower the expression and store result."""
        source = """\
class M {
    int m(int x) {
        return switch (x) {
            case 1 -> { int y = x + 1; yield y * 2; }
            default -> { yield -1; }
        };
    }
}
"""
        instructions = _parse_java(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)
        # Should have BINOP for the expressions
        binops = _find_all(instructions, Opcode.BINOP)
        assert len(binops) >= 2, "Should have binops for x+1 and y*2"
