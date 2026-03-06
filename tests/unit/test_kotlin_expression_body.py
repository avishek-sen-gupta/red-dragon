"""Tests for Kotlin expression-bodied function lowering.

Verifies that `fun f() = 42` emits RETURN with the expression value,
not a default nil return.
"""

from __future__ import annotations

from interpreter.frontends.kotlin import KotlinFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_kotlin(source: str) -> list[IRInstruction]:
    frontend = KotlinFrontend(TreeSitterParserFactory(), "kotlin")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


def _instructions_between_labels(
    instructions: list[IRInstruction], start_prefix: str, end_prefix: str
) -> list[IRInstruction]:
    """Extract instructions between a LABEL matching start_prefix and one matching end_prefix."""
    inside = False
    result = []
    for inst in instructions:
        if (
            inst.opcode == Opcode.LABEL
            and inst.label
            and inst.label.startswith(start_prefix)
        ):
            inside = True
            continue
        if (
            inside
            and inst.opcode == Opcode.LABEL
            and inst.label
            and inst.label.startswith(end_prefix)
        ):
            break
        if inside:
            result.append(inst)
    return result


class TestKotlinExpressionBodyLiteral:
    """fun f() = 42 should emit RETURN with the integer literal register."""

    SOURCE = "fun f() = 42"

    def test_return_carries_literal_value(self):
        instructions = _parse_kotlin(self.SOURCE)
        func_body = _instructions_between_labels(instructions, "func_f", "end_f")
        returns = [i for i in func_body if i.opcode == Opcode.RETURN]
        assert len(returns) >= 1, "expected at least one RETURN in function body"
        return_reg = returns[0].operands[0]
        consts = [
            i
            for i in func_body
            if i.opcode == Opcode.CONST and i.result_reg == return_reg
        ]
        assert len(consts) >= 1, "RETURN register should come from a CONST"
        assert "42" in consts[0].operands, "CONST should hold literal 42"

    def test_no_default_return_value(self):
        instructions = _parse_kotlin(self.SOURCE)
        func_body = _instructions_between_labels(instructions, "func_f", "end_f")
        returns = [i for i in func_body if i.opcode == Opcode.RETURN]
        assert len(returns) >= 1
        return_reg = returns[0].operands[0]
        # The first RETURN should NOT use the default nil register
        default_consts = [
            i
            for i in func_body
            if i.opcode == Opcode.CONST
            and i.result_reg == return_reg
            and "None" in i.operands
        ]
        assert len(default_consts) == 0, "RETURN should not use default None value"


class TestKotlinBlockBodyUnchanged:
    """fun f() { return 42 } should still work (no regression)."""

    SOURCE = "fun f() { return 42 }"

    def test_explicit_return_still_works(self):
        instructions = _parse_kotlin(self.SOURCE)
        func_body = _instructions_between_labels(instructions, "func_f", "end_f")
        returns = [i for i in func_body if i.opcode == Opcode.RETURN]
        assert len(returns) >= 1, "expected at least one RETURN in function body"
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in i.operands for i in consts), "should contain literal 42"
