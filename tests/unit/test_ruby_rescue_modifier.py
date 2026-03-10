"""Unit tests for Ruby rescue_modifier (P0 gap)."""

from __future__ import annotations

from interpreter.frontends.ruby import RubyFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_ruby(source: str) -> list[IRInstruction]:
    frontend = RubyFrontend(TreeSitterParserFactory(), "ruby")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestRubyRescueModifier:
    """Ruby rescue modifier: expr rescue fallback."""

    def test_rescue_modifier_no_unsupported_symbolic(self):
        """rescue_modifier should not produce unsupported SYMBOLIC fallthrough."""
        source = 'x = Integer("abc") rescue 0'
        instructions = _parse_ruby(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "unsupported:" in str(inst.operands) for inst in symbolics
        ), f"Found unsupported: {[s for s in symbolics if 'unsupported:' in str(s.operands)]}"

    def test_rescue_modifier_emits_try_push(self):
        """rescue_modifier should emit TRY_PUSH for exception handling."""
        source = 'x = Integer("abc") rescue 0'
        instructions = _parse_ruby(source)
        try_pushes = _find_all(instructions, Opcode.TRY_PUSH)
        assert len(try_pushes) >= 1, "rescue_modifier should emit TRY_PUSH"

    def test_rescue_modifier_emits_try_pop(self):
        """rescue_modifier should emit TRY_POP after the try body."""
        source = 'x = Integer("abc") rescue 0'
        instructions = _parse_ruby(source)
        try_pops = _find_all(instructions, Opcode.TRY_POP)
        assert len(try_pops) >= 1, "rescue_modifier should emit TRY_POP"

    def test_rescue_modifier_has_fallback(self):
        """rescue_modifier fallback expression should be lowered (CONST for literal)."""
        source = "x = dangerous_call() rescue 42"
        instructions = _parse_ruby(source)
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            "42" in str(inst.operands) for inst in consts
        ), "Fallback value 42 should appear as a CONST"
