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
    def test_interface_emits_new_object(self):
        instructions = _parse_ts("interface Foo { bar: string; }")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("interface:Foo" in str(inst.operands) for inst in new_objs)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Foo" in inst.operands for inst in stores)
        store_indexes = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(store_indexes) >= 1

    def test_interface_with_multiple_fields(self):
        instructions = _parse_ts("interface Point { x: number; y: number; }")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("interface:Point" in str(inst.operands) for inst in new_objs)
        store_indexes = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(store_indexes) >= 2


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


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialTypeScript:
    def test_typed_function_with_interface_param(self):
        source = """\
interface User { name: string; age: number; }
function greet(user: User): string {
    return "Hello " + user.name;
}
"""
        instructions = _parse_ts(source)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("interface:User" in str(inst.operands) for inst in new_objs)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("greet" in inst.operands for inst in stores)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_enum_with_conditional_logic(self):
        source = """\
enum Status { Active, Inactive, Pending }
const s: Status = Status.Active;
if (s === Status.Active) {
    x = 1;
} else {
    x = 0;
}
"""
        instructions = _parse_ts(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.BRANCH_IF in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Status" in inst.operands for inst in stores)
        assert any("s" in inst.operands for inst in stores)
        assert len(instructions) > 15

    def test_class_with_typed_methods(self):
        source = """\
class Stack {
    items: number[];
    constructor() {
        this.items = [];
    }
    push(val: number): void {
        this.items.push(val);
    }
    size(): number {
        return this.items.length;
    }
}
"""
        instructions = _parse_ts(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Stack" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("push" in inst.operands for inst in calls)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1
        assert len(instructions) > 20

    def test_arrow_with_type_annotations(self):
        source = """\
const add = (a: number, b: number): number => a + b;
const result: number = add(1, 2);
"""
        instructions = _parse_ts(source)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("add" in inst.operands for inst in stores)
        assert any("result" in inst.operands for inst in stores)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("add" in inst.operands for inst in calls)

    def test_for_of_with_type_assertion(self):
        source = """\
const items: any[] = [1, 2, 3];
let total: number = 0;
for (const item of items) {
    total = total + (item as number);
}
"""
        instructions = _parse_ts(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.NEW_ARRAY in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("total" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_export_function_with_logic(self):
        source = """\
export function clamp(val: number, min: number, max: number): number {
    if (val < min) {
        return min;
    }
    if (val > max) {
        return max;
    }
    return val;
}
"""
        instructions = _parse_ts(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 3
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("clamp" in inst.operands for inst in stores)

    def test_non_null_assertion_chain(self):
        source = """\
const name: string = obj!.user!.name;
const upper: string = name.toUpperCase();
"""
        instructions = _parse_ts(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("name" in inst.operands for inst in stores)
        assert any("upper" in inst.operands for inst in stores)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("toUpperCase" in inst.operands for inst in calls)

    def test_interface_and_implementing_class(self):
        source = """\
interface Shape { area(): number; }
class Circle {
    radius: number;
    constructor(r: number) {
        this.radius = r;
    }
    area(): number {
        return 3.14 * this.radius * this.radius;
    }
}
"""
        instructions = _parse_ts(source)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("interface:Shape" in str(inst.operands) for inst in new_objs)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Circle" in inst.operands for inst in stores)
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("radius" in inst.operands for inst in store_fields)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("*" in inst.operands for inst in binops)
        assert len(instructions) > 20


class TestTypeScriptDestructuring:
    def test_obj_destructure_ts(self):
        source = "const { name, age }: { name: string; age: number } = user;"
        instructions = _parse_ts(source)
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        field_names = [inst.operands[1] for inst in loads if len(inst.operands) > 1]
        assert "name" in field_names
        assert "age" in field_names

    def test_arr_destructure_ts(self):
        source = "const [first, second]: number[] = arr;"
        instructions = _parse_ts(source)
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_INDEX in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("first" in inst.operands for inst in stores)
        assert any("second" in inst.operands for inst in stores)


class TestTypeScriptAbstractClass:
    def test_abstract_class_basic(self):
        source = """\
abstract class Shape {
    abstract area(): number;
    describe(): string {
        return "I am a shape";
    }
}
"""
        instructions = _parse_ts(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Shape" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

    def test_abstract_class_with_constructor(self):
        source = """\
abstract class Animal {
    name: string;
    constructor(name: string) {
        this.name = name;
    }
    abstract speak(): string;
}
"""
        instructions = _parse_ts(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Animal" in inst.operands for inst in stores)
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("name" in inst.operands for inst in store_fields)

    def test_abstract_class_with_concrete_method(self):
        source = """\
abstract class Base {
    greet(): string {
        return "hello";
    }
}
"""
        instructions = _parse_ts(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Base" in inst.operands for inst in stores)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1
