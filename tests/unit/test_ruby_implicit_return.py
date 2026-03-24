"""Tests for Ruby implicit return lowering.

Verifies that a method whose last expression is a bare value
(e.g. `@age`, `5`) emits RETURN with that value's register,
not a default nil return.
"""

from __future__ import annotations

from interpreter.frontends.ruby import RubyFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_ruby(source: str) -> list[IRInstruction]:
    frontend = RubyFrontend(TreeSitterParserFactory(), "ruby")
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
            and inst.label.starts_with(start_prefix)
        ):
            inside = True
            continue
        if (
            inside
            and inst.opcode == Opcode.LABEL
            and inst.label
            and inst.label.starts_with(end_prefix)
        ):
            break
        if inside:
            result.append(inst)
    return result


class TestRubyImplicitReturnLiteral:
    """Method with bare literal as last expression should return it."""

    SOURCE = """\
def f
  5
end
"""

    def test_return_carries_literal(self):
        instructions = _parse_ruby(self.SOURCE)
        func_body = _instructions_between_labels(instructions, "func_f", "end_f")
        returns = [i for i in func_body if i.opcode == Opcode.RETURN]
        assert len(returns) >= 1, "expected at least one RETURN"
        return_reg = returns[0].operands[0]
        consts = [
            i
            for i in func_body
            if i.opcode == Opcode.CONST and str(i.result_reg) == return_reg
        ]
        assert len(consts) >= 1, "RETURN register should come from a CONST"
        assert "5" in consts[0].operands, "CONST should hold literal 5"


class TestRubyImplicitReturnInstanceVar:
    """Method with bare @age as last expression should return LOAD_FIELD result."""

    SOURCE = """\
class Dog
  def get_age
    @age
  end
end
"""

    def test_return_carries_load_field(self):
        instructions = _parse_ruby(self.SOURCE)
        func_body = _instructions_between_labels(
            instructions, "func_get_age", "end_get_age"
        )
        load_fields = [i for i in func_body if i.opcode == Opcode.LOAD_FIELD]
        returns = [i for i in func_body if i.opcode == Opcode.RETURN]
        assert len(load_fields) >= 1, "expected LOAD_FIELD for @age"
        assert len(returns) >= 1, "expected at least one RETURN"
        assert returns[0].operands[0] == str(
            load_fields[0].result_reg
        ), "RETURN should use LOAD_FIELD result register"


class TestRubyExplicitReturnUnchanged:
    """Method with explicit `return @age` should still work (no regression)."""

    SOURCE = """\
class Dog
  def get_age
    return @age
  end
end
"""

    def test_explicit_return_still_works(self):
        instructions = _parse_ruby(self.SOURCE)
        func_body = _instructions_between_labels(
            instructions, "func_get_age", "end_get_age"
        )
        returns = [i for i in func_body if i.opcode == Opcode.RETURN]
        assert len(returns) >= 1, "expected at least one RETURN"
        load_fields = [i for i in func_body if i.opcode == Opcode.LOAD_FIELD]
        assert len(load_fields) >= 1, "expected LOAD_FIELD for @age"
        assert returns[0].operands[0] == str(
            load_fields[0].result_reg
        ), "RETURN should reference the LOAD_FIELD result register for @age"


class TestRubyImplicitReturnAssignmentIsNil:
    """Method ending in assignment should still return nil (no implicit return for assignments)."""

    SOURCE = """\
def f
  x = 10
end
"""

    def test_assignment_returns_nil(self):
        instructions = _parse_ruby(self.SOURCE)
        func_body = _instructions_between_labels(instructions, "func_f", "end_f")
        returns = [i for i in func_body if i.opcode == Opcode.RETURN]
        assert len(returns) >= 1, "expected at least one RETURN"
        return_reg = returns[0].operands[0]
        # Assignment is a statement, so we should get the default nil return
        default_consts = [
            i
            for i in func_body
            if i.opcode == Opcode.CONST
            and str(i.result_reg) == return_reg
            and "None" in i.operands
        ]
        assert len(default_consts) >= 1, "assignment-ending method should return nil"
