"""Tests for JavaFrontend — tree-sitter Java AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.java import JavaFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_java(source: str) -> list[IRInstruction]:
    parser = get_parser("java")
    tree = parser.parse(source.encode("utf-8"))
    frontend = JavaFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestJavaSmoke:
    def test_empty_program(self):
        instructions = _parse_java("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_class_wrapper(self):
        instructions = _parse_java("class M { }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("M" in inst.operands for inst in stores)


class TestJavaVariables:
    def test_local_variable_declaration(self):
        instructions = _parse_java("class M { void m() { int x = 10; } }")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_variable_without_initializer(self):
        instructions = _parse_java("class M { void m() { int x; } }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("null" in inst.operands for inst in consts)

    def test_assignment_expression(self):
        instructions = _parse_java("class M { void m() { int x; x = 5; } }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        x_stores = [inst for inst in stores if "x" in inst.operands]
        assert len(x_stores) >= 2


class TestJavaExpressions:
    def test_arithmetic(self):
        instructions = _parse_java("class M { void m() { int y = x + 5; } }")
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_cast_expression(self):
        instructions = _parse_java(
            "class M { void m() { double d = 3.14; int x = (int) d; } }"
        )
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_ternary_expression(self):
        instructions = _parse_java(
            'class M { void m() { String y = x > 0 ? "pos" : "neg"; } }'
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes


class TestJavaMethodCalls:
    def test_method_call_on_object(self):
        instructions = _parse_java(
            'class M { void m() { System.out.println("hello"); } }'
        )
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1
        assert any("println" in inst.operands for inst in calls)

    def test_standalone_method_call(self):
        instructions = _parse_java("class M { void m() { foo(1, 2); } }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) >= 1
        assert "foo" in calls[0].operands

    def test_object_creation(self):
        instructions = _parse_java('class M { void m() { Dog d = new Dog("Rex"); } }')
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("Dog" in inst.operands for inst in calls)


class TestJavaControlFlow:
    def test_if_else(self):
        instructions = _parse_java(
            "class M { void m() { if (x > 5) { y = 1; } else { y = 0; } } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        assert Opcode.BRANCH in opcodes

    def test_while_loop(self):
        instructions = _parse_java("class M { void m() { while (x > 0) { x--; } } }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("while" in (inst.label or "") for inst in labels)

    def test_c_style_for_loop(self):
        instructions = _parse_java(
            "class M { void m() { for (int i = 0; i < 10; i++) { x = x + i; } } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("i" in inst.operands for inst in stores)

    def test_enhanced_for_loop(self):
        instructions = _parse_java(
            "class M { void m() { int[] items = {1,2,3}; for (int x : items) { y = x; } } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LOAD_INDEX in opcodes


class TestJavaFunctions:
    def test_method_declaration_with_return(self):
        instructions = _parse_java(
            "class M { int add(int a, int b) { return a + b; } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        assert Opcode.BINOP in opcodes
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("a" in p for p in param_names)
        assert any("b" in p for p in param_names)

    def test_constructor(self):
        instructions = _parse_java(
            "class Dog { String name; Dog(String n) { this.name = n; } }"
        )
        stores = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("name" in inst.operands for inst in stores)


class TestJavaClasses:
    def test_class_definition(self):
        instructions = _parse_java("class Dog { void bark() { } }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

    def test_interface_emits_symbolic(self):
        instructions = _parse_java("interface Runnable { void run(); }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("interface:Runnable" in str(inst.operands) for inst in symbolics)

    def test_enum_emits_symbolic(self):
        instructions = _parse_java("enum Color { RED, GREEN, BLUE }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("enum:Color" in str(inst.operands) for inst in symbolics)


class TestJavaSpecial:
    def test_throw_statement(self):
        instructions = _parse_java(
            'class M { void m() { throw new RuntimeException("fail"); } }'
        )
        opcodes = _opcodes(instructions)
        assert Opcode.THROW in opcodes

    def test_fallback_symbolic_for_unsupported(self):
        instructions = _parse_java("class M { void m() { synchronized(this) { } } }")
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes
