"""Tests for Scala expression-bodied function lowering.

Verifies that `def f() = 42` and `def getAge(): Int = this.age`
emit proper RETURN with the expression value, not default nil return.
"""

from __future__ import annotations

from interpreter.frontends.scala import ScalaFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_scala(source: str) -> list[IRInstruction]:
    frontend = ScalaFrontend(TreeSitterParserFactory(), "scala")
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


class TestScalaExpressionBodyLiteral:
    """def f() = 42 should emit RETURN with the integer literal register."""

    SOURCE = """\
object M {
  def f(): Int = 42
}
"""

    def test_return_carries_literal_value(self):
        instructions = _parse_scala(self.SOURCE)
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
        instructions = _parse_scala(self.SOURCE)
        func_body = _instructions_between_labels(instructions, "func_f", "end_f")
        default_consts = [
            i for i in func_body if i.opcode == Opcode.CONST and "()" in i.operands
        ]
        # There should be no default "()" return since expression body provides the value
        returns = [i for i in func_body if i.opcode == Opcode.RETURN]
        assert len(returns) >= 1
        # The first RETURN should NOT use the default "()" register
        return_reg = returns[0].operands[0]
        default_return_consts = [
            i for i in default_consts if i.result_reg == return_reg
        ]
        assert len(default_return_consts) == 0, "RETURN should not use default () value"


class TestScalaExpressionBodyFieldAccess:
    """def getAge(): Int = this.age should emit LOAD_FIELD, not LOAD_VAR."""

    SOURCE = """\
class Dog {
  var age: Int = 0
  def getAge(): Int = this.age
}
"""

    def test_load_field_emitted(self):
        instructions = _parse_scala(self.SOURCE)
        func_body = _instructions_between_labels(
            instructions, "func_getAge", "end_getAge"
        )
        load_fields = [i for i in func_body if i.opcode == Opcode.LOAD_FIELD]
        assert len(load_fields) >= 1, "expected LOAD_FIELD for this.age"
        assert any(
            "age" in i.operands for i in load_fields
        ), "LOAD_FIELD should reference 'age'"

    def test_return_carries_load_field_result(self):
        instructions = _parse_scala(self.SOURCE)
        func_body = _instructions_between_labels(
            instructions, "func_getAge", "end_getAge"
        )
        load_fields = [i for i in func_body if i.opcode == Opcode.LOAD_FIELD]
        returns = [i for i in func_body if i.opcode == Opcode.RETURN]
        assert len(load_fields) >= 1
        assert len(returns) >= 1
        # The RETURN should reference the LOAD_FIELD result register
        load_field_reg = load_fields[0].result_reg
        return_reg = returns[0].operands[0]
        assert (
            return_reg == load_field_reg
        ), f"RETURN should use LOAD_FIELD result {load_field_reg}, got {return_reg}"
