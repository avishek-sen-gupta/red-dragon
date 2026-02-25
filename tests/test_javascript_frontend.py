"""Tests for JavaScriptFrontend — tree-sitter JavaScript AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.javascript import JavaScriptFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_js(source: str) -> list[IRInstruction]:
    parser = get_parser("javascript")
    tree = parser.parse(source.encode("utf-8"))
    frontend = JavaScriptFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestJavaScriptSmoke:
    def test_empty_program(self):
        instructions = _parse_js("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_number_literal(self):
        instructions = _parse_js("42;")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)


class TestJavaScriptExpressions:
    def test_variable_assignment(self):
        instructions = _parse_js("let x = 10;")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_arithmetic_expression(self):
        instructions = _parse_js("let y = x + 5;")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.CONST in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_ternary_expression(self):
        instructions = _parse_js('let y = x > 0 ? "pos" : "neg";')
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.STORE_VAR in opcodes

    def test_template_literal(self):
        instructions = _parse_js("const s = `hello`;")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("`hello`" in inst.operands for inst in consts)


class TestJavaScriptControlFlow:
    def test_if_else(self):
        instructions = _parse_js("if (x > 5) { y = 1; } else { y = 0; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        assert Opcode.BRANCH in opcodes

    def test_while_loop(self):
        instructions = _parse_js("while (x > 0) { x--; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("while" in (inst.label or "") for inst in labels)

    def test_for_loop(self):
        instructions = _parse_js("for (let i = 0; i < 10; i++) { x = x + i; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("i" in inst.operands for inst in stores)

    def test_for_in_loop(self):
        instructions = _parse_js("for (let k in obj) { x = k; }")
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes
        assert Opcode.BRANCH_IF in opcodes


class TestJavaScriptFunctions:
    def test_function_declaration(self):
        instructions = _parse_js("function add(a, b) { return a + b; }")
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

    def test_function_call(self):
        instructions = _parse_js("add(1, 2);")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) >= 1
        assert "add" in calls[0].operands

    def test_arrow_function(self):
        instructions = _parse_js("const f = (a, b) => a + b;")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("f" in inst.operands for inst in stores)

    def test_method_call(self):
        instructions = _parse_js('console.log("hello");')
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1
        assert "log" in calls[0].operands


class TestJavaScriptClasses:
    def test_class_definition(self):
        instructions = _parse_js(
            'class Dog { constructor(n) { this.name = n; } bark() { return "woof"; } }'
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)


class TestJavaScriptLiterals:
    def test_object_literal(self):
        instructions = _parse_js("const obj = {a: 1, b: 2};")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes

    def test_array_literal(self):
        instructions = _parse_js("const arr = [1, 2, 3];")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.STORE_INDEX in opcodes


class TestJavaScriptSpecial:
    def test_throw_statement(self):
        instructions = _parse_js('throw new Error("fail");')
        opcodes = _opcodes(instructions)
        assert Opcode.THROW in opcodes

    def test_update_expression_decrement(self):
        instructions = _parse_js("x--;")
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("-" in inst.operands for inst in binops)

    def test_update_expression_increment(self):
        instructions = _parse_js("x++;")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_fallback_symbolic(self):
        instructions = _parse_js("debugger;")
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("unsupported:" in str(inst.operands) for inst in symbolics)
