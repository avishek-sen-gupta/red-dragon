"""Tests for TypeScriptFrontend — tree-sitter TypeScript AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.typescript import TypeScriptFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_ts(source: str) -> list[IRInstruction]:
    parser = get_parser("typescript")
    tree = parser.parse(source.encode("utf-8"))
    frontend = TypeScriptFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestTypeScriptSmoke:
    def test_empty_program(self):
        instructions = _parse_ts("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_number_literal(self):
        instructions = _parse_ts("42;")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)


class TestTypeScriptTypedBasics:
    def test_typed_variable_assignment(self):
        instructions = _parse_ts("let x: number = 10;")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_typed_arithmetic(self):
        instructions = _parse_ts("let y: number = x + 5;")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes

    def test_string_type_variable(self):
        instructions = _parse_ts('let name: string = "hello";')
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("name" in inst.operands for inst in stores)


class TestTypeScriptInterfaces:
    def test_interface_emits_symbolic(self):
        instructions = _parse_ts("interface Foo { bar: string; }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("interface:Foo" in str(inst.operands) for inst in symbolics)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Foo" in inst.operands for inst in stores)

    def test_interface_with_multiple_fields(self):
        instructions = _parse_ts("interface Point { x: number; y: number; }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("interface:Point" in str(inst.operands) for inst in symbolics)


class TestTypeScriptEnums:
    def test_enum_declaration(self):
        instructions = _parse_ts("enum Color { Red, Green, Blue }")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Color" in inst.operands for inst in stores)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("enum:Color" in str(inst.operands) for inst in new_objs)

    def test_enum_members_indexed(self):
        instructions = _parse_ts("enum Direction { Up, Down, Left, Right }")
        store_indices = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(store_indices) >= 4


class TestTypeScriptTypeFeatures:
    def test_type_alias_ignored(self):
        instructions = _parse_ts("type Alias = string;")
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC not in opcodes or all(
            "unsupported:" not in str(inst.operands)
            for inst in _find_all(instructions, Opcode.SYMBOLIC)
        )

    def test_as_expression(self):
        instructions = _parse_ts("const x = y as number;")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_non_null_assertion(self):
        instructions = _parse_ts("const x = y!;")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.STORE_VAR in opcodes


class TestTypeScriptFunctions:
    def test_typed_function_parameters(self):
        instructions = _parse_ts(
            "function add(a: number, b: number): number { return a + b; }"
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

    def test_arrow_function_with_types(self):
        instructions = _parse_ts("const f = (a: number, b: number): number => a + b;")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("f" in inst.operands for inst in stores)


class TestTypeScriptClasses:
    def test_class_with_typed_fields(self):
        instructions = _parse_ts(
            "class Dog { name: string; constructor(n: string) { this.name = n; } }"
        )
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)


class TestTypeScriptExport:
    def test_export_function(self):
        instructions = _parse_ts("export function foo() { return 1; }")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("foo" in inst.operands for inst in stores)

    def test_export_variable(self):
        instructions = _parse_ts("export const x = 42;")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestTypeScriptControlFlow:
    def test_if_else(self):
        instructions = _parse_ts("if (x > 5) { y = 1; } else { y = 0; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes

    def test_while_loop(self):
        instructions = _parse_ts("while (x > 0) { x--; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
