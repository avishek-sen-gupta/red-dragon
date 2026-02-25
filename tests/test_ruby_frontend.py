"""Tests for RubyFrontend — tree-sitter Ruby AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.ruby import RubyFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_ruby(source: str) -> list[IRInstruction]:
    parser = get_parser("ruby")
    tree = parser.parse(source.encode("utf-8"))
    frontend = RubyFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestRubySmoke:
    def test_empty_program(self):
        instructions = _parse_ruby("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_integer_literal(self):
        instructions = _parse_ruby("42")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)


class TestRubyVariables:
    def test_variable_assignment(self):
        instructions = _parse_ruby("x = 10")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_instance_variable_assignment(self):
        instructions = _parse_ruby("@name = 'hello'")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("@name" in inst.operands for inst in stores)

    def test_augmented_assignment(self):
        instructions = _parse_ruby("x += 1")
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestRubyExpressions:
    def test_arithmetic(self):
        instructions = _parse_ruby("y = x + 5")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_string_literal(self):
        instructions = _parse_ruby('s = "hello world"')
        consts = _find_all(instructions, Opcode.CONST)
        assert any('"hello world"' in inst.operands for inst in consts)


class TestRubyControlFlow:
    def test_if_elsif_else(self):
        source = """
if x > 10
  y = 1
elsif x > 5
  y = 2
else
  y = 0
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        assert Opcode.BRANCH in opcodes
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2

    def test_unless(self):
        source = """
unless x > 0
  y = -1
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.UNOP in opcodes
        assert Opcode.BRANCH_IF in opcodes
        unops = _find_all(instructions, Opcode.UNOP)
        assert any("!" in inst.operands for inst in unops)

    def test_while_loop(self):
        source = """
while x > 0
  x = x - 1
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("while" in (inst.label or "") for inst in labels)

    def test_until_loop(self):
        source = """
until x <= 0
  x = x - 1
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.UNOP in opcodes
        assert Opcode.BRANCH_IF in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("until" in (inst.label or "") for inst in labels)


class TestRubyMethods:
    def test_method_definition(self):
        source = """
def add(a, b)
  a + b
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("add" in inst.operands for inst in stores)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("a" in p for p in param_names)
        assert any("b" in p for p in param_names)

    def test_method_call_standalone(self):
        instructions = _parse_ruby("add(1, 2)")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) >= 1
        assert "add" in calls[0].operands

    def test_method_call_with_receiver(self):
        instructions = _parse_ruby("obj.bark")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1
        assert "bark" in calls[0].operands

    def test_method_call_with_receiver_and_args(self):
        instructions = _parse_ruby("obj.send(1, 2)")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1
        assert "send" in calls[0].operands

    def test_return_statement(self):
        source = """
def foo
  return 42
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes


class TestRubyClasses:
    def test_class_definition(self):
        source = """
class Dog
  def bark
    "woof"
  end
end
"""
        instructions = _parse_ruby(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

    def test_class_with_constructor(self):
        source = """
class Dog
  def initialize(name)
    @name = name
  end
end
"""
        instructions = _parse_ruby(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        assert any("@name" in inst.operands for inst in stores)


class TestRubySpecial:
    def test_array_literal(self):
        instructions = _parse_ruby("arr = [1, 2, 3]")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.STORE_INDEX in opcodes

    def test_hash_literal(self):
        instructions = _parse_ruby("h = {a: 1, b: 2}")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes

    def test_fallback_symbolic_for_unsupported(self):
        instructions = _parse_ruby("BEGIN { puts 'start' }")
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes
