"""Tests for CppFrontend -- tree-sitter C++ AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.cpp import CppFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_cpp(source: str) -> list[IRInstruction]:
    parser = get_parser("cpp")
    tree = parser.parse(source.encode("utf-8"))
    frontend = CppFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestCppDeclarations:
    def test_int_declaration(self):
        instructions = _parse_cpp("int x = 10;")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_declaration_without_initializer(self):
        instructions = _parse_cpp("int x;")
        opcodes = _opcodes(instructions)
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestCppFunctions:
    def test_function_definition(self):
        instructions = _parse_cpp("int add(int a, int b) { return a + b; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("add" in inst.operands for inst in stores)

    def test_function_call(self):
        instructions = _parse_cpp("int main() { add(1, 2); }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("add" in inst.operands for inst in calls)

    def test_return_statement(self):
        instructions = _parse_cpp("int main() { return 42; }")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)


class TestCppControlFlow:
    def test_if_else_with_condition_clause(self):
        instructions = _parse_cpp(
            "int main() { if (x > 5) { y = 1; } else { y = 0; } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("if_true" in (inst.label or "") for inst in labels)

    def test_while_with_condition_clause(self):
        instructions = _parse_cpp("int main() { while (x > 0) { x--; } }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("while" in (inst.label or "") for inst in labels)

    def test_c_style_for_loop(self):
        instructions = _parse_cpp(
            "int main() { for (int i = 0; i < 10; i++) { x = x + i; } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("i" in inst.operands for inst in stores)


class TestCppClasses:
    def test_class_with_methods(self):
        instructions = _parse_cpp("class Dog { public: void bark() { return; } };")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

    def test_namespace_transparent(self):
        instructions = _parse_cpp("namespace myns { int x = 10; }")
        opcodes = _opcodes(instructions)
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestCppExpressions:
    def test_new_expression(self):
        instructions = _parse_cpp('int main() { Dog* d = new Dog("Rex"); }')
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("Dog" in inst.operands for inst in calls)

    def test_delete_expression(self):
        instructions = _parse_cpp("int main() { delete ptr; }")
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("delete:" in str(inst.operands) for inst in symbolics)

    def test_lambda_expression(self):
        instructions = _parse_cpp(
            "int main() { auto f = [](int a, int b) { return a + b; }; }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        assert Opcode.BINOP in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any("__lambda" in str(inst.operands) for inst in consts)

    def test_template_declaration(self):
        instructions = _parse_cpp(
            "template <typename T> T identity(T val) { return val; }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("identity" in inst.operands for inst in stores)


class TestCppSpecial:
    def test_empty_program(self):
        instructions = _parse_cpp("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_fallback_symbolic(self):
        instructions = _parse_cpp('int main() { asm volatile("nop"); }')
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes

    def test_string_literal(self):
        instructions = _parse_cpp('int main() { const char* s = "hello"; }')
        consts = _find_all(instructions, Opcode.CONST)
        assert any('"hello"' in inst.operands for inst in consts)

    def test_binary_expression(self):
        instructions = _parse_cpp("int main() { int z = x + y; }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
