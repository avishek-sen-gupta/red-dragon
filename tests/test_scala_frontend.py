"""Tests for ScalaFrontend -- tree-sitter Scala AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.scala import ScalaFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_scala(source: str) -> list[IRInstruction]:
    parser = get_parser("scala")
    tree = parser.parse(source.encode("utf-8"))
    frontend = ScalaFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestScalaDeclarations:
    def test_val_definition(self):
        instructions = _parse_scala("object M { val x = 10 }")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_var_definition(self):
        instructions = _parse_scala("object M { var y = 5 }")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)

    def test_var_assignment(self):
        instructions = _parse_scala("object M { var y = 5; y = 10 }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("10" in inst.operands for inst in consts)


class TestScalaFunctions:
    def test_function_definition(self):
        instructions = _parse_scala("object M { def add(a: Int, b: Int): Int = a + b }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        assert Opcode.RETURN in opcodes
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("a" in p for p in param_names)
        assert any("b" in p for p in param_names)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("add" in inst.operands for inst in stores)

    def test_function_call(self):
        instructions = _parse_scala("object M { val r = add(1, 2) }")
        # The call should produce either CALL_FUNCTION or CALL_UNKNOWN
        all_calls = _find_all(instructions, Opcode.CALL_FUNCTION) + _find_all(
            instructions, Opcode.CALL_UNKNOWN
        )
        assert len(all_calls) >= 1

    def test_return_via_expression(self):
        instructions = _parse_scala("object M { def answer(): Int = { 42 } }")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        # The function body should contain the constant 42
        consts = _find_all(instructions, Opcode.CONST)
        const_values = [str(v) for inst in consts for v in inst.operands]
        assert any("42" in v for v in const_values)


class TestScalaControlFlow:
    def test_if_expression_value_producing(self):
        instructions = _parse_scala("object M { val y = if (x > 0) 1 else 0 }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("if_true" in (inst.label or "") for inst in labels)

    def test_while_loop(self):
        instructions = _parse_scala(
            "object M { var x = 10; while (x > 0) { x = x - 1 } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("while" in (inst.label or "") for inst in labels)

    def test_match_expression(self):
        instructions = _parse_scala(
            "object M { val r = x match { case 1 => 10; case _ => 0 } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes or Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("case" in (inst.label or "") for inst in labels)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("r" in inst.operands for inst in stores)


class TestScalaClasses:
    def test_class_definition(self):
        instructions = _parse_scala('class Dog { def bark(): String = "woof" }')
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

    def test_object_definition_singleton(self):
        instructions = _parse_scala("object Singleton { val x = 42 }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Singleton" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)


class TestScalaExpressions:
    def test_infix_expression_binary_op(self):
        instructions = _parse_scala("object M { val z = a + b }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_block_as_expression(self):
        instructions = _parse_scala("object M { val v = { val a = 1; a + 2 } }")
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("v" in inst.operands for inst in stores)

    def test_field_access(self):
        instructions = _parse_scala("object M { val f = obj.field }")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_FIELD in opcodes
        fields = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("field" in inst.operands for inst in fields)

    def test_string_literal(self):
        instructions = _parse_scala('object M { val s = "hello" }')
        consts = _find_all(instructions, Opcode.CONST)
        assert any('"hello"' in inst.operands for inst in consts)

    def test_boolean_literal(self):
        instructions = _parse_scala("object M { val b = true }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("true" in inst.operands for inst in consts)


class TestScalaSpecial:
    def test_empty_program(self):
        instructions = _parse_scala("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_fallback_symbolic(self):
        instructions = _parse_scala("object M { type Alias = List[Int] }")
        opcodes = _opcodes(instructions)
        # Type alias should produce at least a SYMBOLIC or be passthrough
        assert len(instructions) > 1

    def test_return_last_expression_in_block(self):
        instructions = _parse_scala(
            "object M { def compute(): Int = { val a = 1; val b = 2; a + b } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        assert Opcode.RETURN in opcodes

    def test_method_call(self):
        instructions = _parse_scala("object M { val r = obj.doSomething(1) }")
        # Should produce CALL_METHOD or at least some call-related opcode
        all_calls = (
            _find_all(instructions, Opcode.CALL_METHOD)
            + _find_all(instructions, Opcode.CALL_FUNCTION)
            + _find_all(instructions, Opcode.CALL_UNKNOWN)
        )
        assert len(all_calls) >= 1

    def test_null_literal(self):
        instructions = _parse_scala("object M { val n = null }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("null" in inst.operands for inst in consts)
