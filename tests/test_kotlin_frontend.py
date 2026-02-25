"""Tests for KotlinFrontend -- tree-sitter Kotlin AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.kotlin import KotlinFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_kotlin(source: str) -> list[IRInstruction]:
    parser = get_parser("kotlin")
    tree = parser.parse(source.encode("utf-8"))
    frontend = KotlinFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestKotlinDeclarations:
    def test_val_declaration(self):
        instructions = _parse_kotlin("val x = 10")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_var_declaration(self):
        instructions = _parse_kotlin("var y = 5")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)

    def test_val_without_initializer(self):
        instructions = _parse_kotlin("val x: Int")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestKotlinFunctions:
    def test_function_declaration(self):
        instructions = _parse_kotlin("fun add(a: Int, b: Int): Int { return a + b }")
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
        instructions = _parse_kotlin("fun main() { add(1, 2) }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("add" in inst.operands for inst in calls)

    def test_return_via_jump_expression(self):
        instructions = _parse_kotlin("fun main() { return 42 }")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)


class TestKotlinControlFlow:
    def test_if_expression(self):
        instructions = _parse_kotlin("fun main() { val y = if (x > 0) 1 else 0 }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("if_true" in (inst.label or "") for inst in labels)

    def test_while_loop(self):
        instructions = _parse_kotlin("fun main() { while (x > 0) { x = x - 1 } }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("while" in (inst.label or "") for inst in labels)

    def test_when_expression(self):
        instructions = _parse_kotlin(
            "fun main() { val r = when (x) { 1 -> 10\n 2 -> 20\n else -> 0 } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("when" in (inst.label or "") for inst in labels)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("r" in inst.operands for inst in stores)


class TestKotlinClasses:
    def test_class_declaration(self):
        instructions = _parse_kotlin(
            'class Dog { fun bark(): String { return "woof" } }'
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)


class TestKotlinExpressions:
    def test_navigation_expression_member_access(self):
        instructions = _parse_kotlin("fun main() { val f = obj.name }")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_FIELD in opcodes
        fields = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("name" in str(inst.operands) for inst in fields)

    def test_additive_binary_op(self):
        instructions = _parse_kotlin("fun main() { val z = x + y }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_multiplicative_binary_op(self):
        instructions = _parse_kotlin("fun main() { val z = x * y }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("*" in inst.operands for inst in binops)

    def test_comparison_binary_op(self):
        instructions = _parse_kotlin("fun main() { val b = x > y }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any(">" in inst.operands for inst in binops)

    def test_string_literal(self):
        instructions = _parse_kotlin('fun main() { val s = "hello" }')
        consts = _find_all(instructions, Opcode.CONST)
        assert any('"hello"' in inst.operands for inst in consts)

    def test_null_literal(self):
        instructions = _parse_kotlin("fun main() { val n = null }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("null" in inst.operands for inst in consts)


class TestKotlinSpecial:
    def test_empty_program(self):
        instructions = _parse_kotlin("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_fallback_symbolic(self):
        instructions = _parse_kotlin("fun main() { @Deprecated fun old() {} }")
        opcodes = _opcodes(instructions)
        # Should produce at least some IR; annotation itself might be ignored
        assert len(instructions) > 1

    def test_method_call_via_navigation(self):
        instructions = _parse_kotlin("fun main() { obj.doSomething(1) }")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("doSomething" in str(inst.operands) for inst in calls)

    def test_lambda_literal(self):
        instructions = _parse_kotlin(
            "fun main() { val f = { a: Int, b: Int -> a + b } }"
        )
        consts = _find_all(instructions, Opcode.CONST)
        assert any("__lambda" in str(inst.operands) for inst in consts)
