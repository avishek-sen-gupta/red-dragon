"""Tests for TypeScriptFrontend — tree-sitter TypeScript AST to IR lowering."""

from __future__ import annotations

from interpreter.frontends.typescript import TypeScriptFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


from interpreter.type_environment_builder import TypeEnvironmentBuilder


def _parse_ts(source: str) -> list[IRInstruction]:
    frontend = TypeScriptFrontend(TreeSitterParserFactory(), "typescript")
    return frontend.lower(source.encode("utf-8"))


def _parse_ts_with_types(
    source: str,
) -> tuple[list[IRInstruction], TypeEnvironmentBuilder]:
    frontend = TypeScriptFrontend(TreeSitterParserFactory(), "typescript")
    instructions = frontend.lower(source.encode("utf-8"))
    return instructions, frontend.type_env_builder


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
        assert Opcode.DECL_VAR in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_typed_arithmetic(self):
        instructions = _parse_ts("let y: number = x + 5;")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.DECL_VAR in opcodes

    def test_string_type_variable(self):
        instructions = _parse_ts('let name: string = "hello";')
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("name" in inst.operands for inst in stores)


class TestTypeScriptInterfaces:
    def test_interface_emits_class_block(self):
        """Interface lowered as CLASS block (not NEW_OBJECT)."""
        instructions = _parse_ts("interface Foo { bar: string; }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            "class_" in str(c.operands) and "Foo" in str(c.operands) for c in consts
        )
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Foo" in inst.operands for inst in stores)

    def test_interface_with_multiple_methods(self):
        instructions = _parse_ts("interface Point { getX(): number; getY(): number; }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            "class_" in str(c.operands) and "Point" in str(c.operands) for c in consts
        )
        labels = [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]
        func_labels = [l for l in labels if "func_" in l]
        assert any("getX" in l for l in func_labels)
        assert any("getY" in l for l in func_labels)


class TestTypeScriptEnums:
    def test_enum_declaration(self):
        instructions = _parse_ts("enum Color { Red, Green, Blue }")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Color" in inst.operands for inst in stores)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("enum:Color" in str(inst.operands) for inst in new_objs)

    def test_enum_members_indexed(self):
        instructions = _parse_ts("enum Direction { Up, Down, Left, Right }")
        store_indices = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(store_indices) == 4


class TestTypeScriptTypeFeatures:
    def test_type_alias_ignored(self):
        instructions = _parse_ts("type Alias = string;")
        # Type alias should produce only the entry label — no real instructions
        assert len(instructions) == 1
        assert instructions[0].opcode == Opcode.LABEL

    def test_as_expression(self):
        instructions = _parse_ts("const x = y as number;")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.DECL_VAR in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)
        # The `as` cast should be handled transparently — no unsupported SYMBOLIC
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "as_expression" in str(inst.operands) for inst in symbolics
        ), "as_expression should be handled, not emitted as unsupported SYMBOLIC"

    def test_non_null_assertion(self):
        instructions = _parse_ts("const x = y!;")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.DECL_VAR in opcodes
        # The `!` non-null assertion should be handled transparently — no unsupported SYMBOLIC
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "non_null" in str(inst.operands) for inst in symbolics
        ), "non_null_expression should be handled, not emitted as unsupported SYMBOLIC"


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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("f" in inst.operands for inst in stores)


class TestTypeScriptClasses:
    def test_class_with_typed_fields(self):
        instructions = _parse_ts(
            "class Dog { name: string; constructor(n: string) { this.name = n; } }"
        )
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)


class TestTypeScriptExport:
    def test_export_function(self):
        instructions = _parse_ts("export function foo() { return 1; }")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("foo" in inst.operands for inst in stores)

    def test_export_variable(self):
        instructions = _parse_ts("export const x = 42;")
        stores = _find_all(instructions, Opcode.DECL_VAR)
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

    def test_if_elseif_chain_all_branches_produce_ir(self):
        """All branches of if/else-if/else-if/else must produce IR."""
        instructions = _parse_ts(
            "if (x===1) { y=10; }"
            " else if (x===2) { y=20; }"
            " else if (x===3) { y=30; }"
            " else { y=40; }"
        )
        consts = _find_all(instructions, Opcode.CONST)
        const_values = [op for inst in consts for op in inst.operands]
        assert "10" in const_values, "if-branch value missing"
        assert "20" in const_values, "first else-if-branch value missing"
        assert "30" in const_values, "second else-if-branch value missing"
        assert "40" in const_values, "else-branch value missing"

        branch_ifs = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branch_ifs) == 3

        labels = _labels_in_order(instructions)
        branch_targets = {
            target for inst in branch_ifs for target in inst.label.split(",")
        }
        label_set = set(labels)
        assert branch_targets.issubset(
            label_set
        ), f"Unreachable targets: {branch_targets - label_set}"


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
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            "class_" in str(c.operands) and "User" in str(c.operands) for c in consts
        )
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Stack" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("clamp" in inst.operands for inst in stores)

    def test_non_null_assertion_chain(self):
        # NOTE: The `!` (non-null assertion) operator is transparent at the IR level —
        # the TS frontend strips it via _lower_non_null_expr (x! → just lower x).
        # This test verifies the property chain lowers correctly; the `!` operators
        # cannot be observed in IR output.
        source = """\
const name: string = obj!.user!.name;
const upper: string = name.toUpperCase();
"""
        instructions = _parse_ts(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            "class_" in str(c.operands) and "Shape" in str(c.operands) for c in consts
        )
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Shape" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)

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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Base" in inst.operands for inst in stores)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1


class TestTypeScriptFieldDefinition:
    def test_public_field_no_symbolic(self):
        source = """\
class Foo {
    public name: string = "hello";
}
"""
        instructions = _parse_ts(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "public_field_definition" in str(inst.operands) for inst in symbolics
        )

    def test_public_field_store_var(self):
        source = """\
class Foo {
    public count: number = 42;
}
"""
        instructions = _parse_ts(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("count" in inst.operands for inst in stores)

    def test_public_field_no_value(self):
        source = """\
class Foo {
    public label: string;
}
"""
        instructions = _parse_ts(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("label" in inst.operands for inst in stores)


class TestTypeScriptAbstractMethodSignature:
    def test_abstract_method_signature_no_unsupported(self):
        """abstract method signature should not produce unsupported SYMBOLIC."""
        source = """\
abstract class Animal {
    abstract speak(): string;
}
"""
        instructions = _parse_ts(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_abstract_method_signature_with_params(self):
        source = """\
abstract class Shape {
    abstract area(scale: number): number;
}
"""
        instructions = _parse_ts(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)


class TestTypeScriptInternalModule:
    def test_internal_module_no_unsupported(self):
        """namespace (internal_module) should not produce unsupported SYMBOLIC."""
        source = """\
namespace Geometry {
    export function area(): number { return 0; }
}
"""
        instructions = _parse_ts(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_internal_module_lowers_body(self):
        source = """\
namespace Utils {
    export const PI = 3.14;
    export function double(x: number): number { return x * 2; }
}
"""
        instructions = _parse_ts(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("PI" in inst.operands for inst in stores)


class TestTSTypeAssertion:
    def test_type_assertion_no_symbolic(self):
        """<string>x should not produce SYMBOLIC fallthrough."""
        frontend = TypeScriptFrontend(TreeSitterParserFactory(), "typescript")
        ir = frontend.lower(b"let y = <string>x;")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("type_assertion" in str(inst.operands) for inst in symbolics)

    def test_type_assertion_lowers_inner_expr(self):
        """<string>x should produce a LOAD_VAR for x."""
        frontend = TypeScriptFrontend(TreeSitterParserFactory(), "typescript")
        ir = frontend.lower(b"let y = <string>x;")
        loads = _find_all(ir, Opcode.LOAD_VAR)
        assert any("x" in inst.operands for inst in loads)


class TestTypeScriptForLoopUpdate:
    """C-style for-loop update expression must be lowered correctly."""

    def test_for_loop_update_produces_correct_result(self):
        from tests.unit.rosetta.conftest import execute_for_language, extract_answer

        vm, stats = execute_for_language(
            "typescript",
            """\
let answer: number = 0;
for (let i: number = 0; i < 5; i = i + 1) {
    answer = answer + i;
}
""",
        )
        assert extract_answer(vm, "typescript") == 10
        assert stats.llm_calls == 0

    def test_for_loop_update_emits_store(self):
        ir = _parse_ts("""\
let x: number = 0;
for (let i: number = 0; i < 3; i = i + 1) {
    x = x + 1;
}
""")
        decls = _find_all(ir, Opcode.DECL_VAR)
        stores = _find_all(ir, Opcode.STORE_VAR)
        i_decls = [inst for inst in decls if inst.operands and inst.operands[0] == "i"]
        i_stores = [
            inst for inst in stores if inst.operands and inst.operands[0] == "i"
        ]
        assert (
            len(i_decls) >= 1
        ), f"Expected >= 1 DECL_VAR for 'i' (init), got {len(i_decls)}"
        assert (
            len(i_stores) >= 1
        ), f"Expected >= 1 STORE_VAR for 'i' (update), got {len(i_stores)}"


class TestTypeScriptInterfaceLowering:
    """TS interfaces should lower methods as function definitions with return types."""

    INTERFACE_SOURCE = """\
interface Shape {
    area(): number;
    name(): string;
}
"""

    def test_interface_methods_produce_func_labels(self):
        ir = _parse_ts(self.INTERFACE_SOURCE)
        labels = [inst.label for inst in ir if inst.opcode == Opcode.LABEL]
        func_labels = [l for l in labels if "func_" in l]
        assert any(
            "area" in l for l in func_labels
        ), f"Expected function label for 'area', got: {func_labels}"
        assert any(
            "name" in l for l in func_labels
        ), f"Expected function label for 'name', got: {func_labels}"

    def test_interface_methods_seed_return_types(self):
        ir, type_builder = _parse_ts_with_types(self.INTERFACE_SOURCE)
        func_return_types = type_builder.func_return_types
        area_entries = {k: v for k, v in func_return_types.items() if "area" in k}
        name_entries = {k: v for k, v in func_return_types.items() if "name" in k}
        assert (
            len(area_entries) >= 1
        ), f"Expected return type for 'area', got: {func_return_types}"
        assert (
            len(name_entries) >= 1
        ), f"Expected return type for 'name', got: {func_return_types}"

    def test_interface_stored_as_class_ref(self):
        ir = _parse_ts(self.INTERFACE_SOURCE)
        consts = _find_all(ir, Opcode.CONST)
        class_refs = [c for c in consts if "class_" in str(c.operands)]
        assert any(
            "Shape" in str(c.operands) for c in class_refs
        ), f"Expected class ref for Shape, got: {[c.operands for c in consts]}"

    def test_interface_property_signature(self):
        """Property signatures in interfaces should produce STORE_VAR with type seeding."""
        ir = _parse_ts("interface Logger { level: string; }")
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("Logger" in inst.operands for inst in stores)
        assert any(
            "level" in inst.operands for inst in stores
        ), f"Expected STORE_VAR for 'level', got: {[s.operands for s in stores]}"


class TestTypeScriptInterfacePropertySignatures:
    """TS interface property_signature lowering seeds type info (ADR-101)."""

    INTERFACE_WITH_PROPS = """\
interface Config {
    name: string;
    readonly id: number;
    optional?: boolean;
    compute(): number;
}
"""

    def test_property_signature_emits_store_var(self):
        """Each property_signature should emit STORE_VAR inside the class block."""
        ir = _parse_ts(self.INTERFACE_WITH_PROPS)
        stores = _find_all(ir, Opcode.DECL_VAR)
        store_names = [s.operands[0] for s in stores if s.operands]
        assert (
            "name" in store_names
        ), f"Expected STORE_VAR for 'name', got: {store_names}"
        assert "id" in store_names, f"Expected STORE_VAR for 'id', got: {store_names}"
        assert (
            "optional" in store_names
        ), f"Expected STORE_VAR for 'optional', got: {store_names}"

    def test_property_signature_seeds_var_type(self):
        """Property signatures should seed var types for inference chain walk."""
        ir, type_builder = _parse_ts_with_types(self.INTERFACE_WITH_PROPS)
        var_types = type_builder.var_types
        name_types = {k: v for k, v in var_types.items() if k == "name"}
        id_types = {k: v for k, v in var_types.items() if k == "id"}
        assert len(name_types) >= 1, f"Expected var type for 'name', got: {var_types}"
        assert len(id_types) >= 1, f"Expected var type for 'id', got: {var_types}"

    def test_property_signature_no_symbolic(self):
        """Property signatures should not produce SYMBOLIC unsupported markers."""
        ir = _parse_ts(self.INTERFACE_WITH_PROPS)
        symbolics = [
            s
            for s in ir
            if s.opcode == Opcode.SYMBOLIC and "property_signature" in str(s.operands)
        ]
        assert (
            len(symbolics) == 0
        ), f"property_signature should not produce SYMBOLIC, got: {symbolics}"

    def test_method_and_property_coexist(self):
        """Interface with both methods and properties should lower both."""
        ir = _parse_ts(self.INTERFACE_WITH_PROPS)
        stores = _find_all(ir, Opcode.DECL_VAR)
        store_names = [s.operands[0] for s in stores if s.operands]
        # compute() is a method_signature → lowered as function
        assert (
            "compute" in store_names
        ), f"Expected method 'compute', got: {store_names}"
        # name is a property_signature → lowered as STORE_VAR
        assert "name" in store_names, f"Expected property 'name', got: {store_names}"


class TestFunctionSignature:
    """function_signature (overload declarations) should emit no IR."""

    def test_overload_signatures_no_symbolic(self):
        ir = _parse_ts("""
            function add(a: number, b: number): number;
            function add(a: string, b: string): string;
            function add(a: any, b: any): any { return a + b; }
            """)
        symbolics = [
            s
            for s in ir
            if s.opcode == Opcode.SYMBOLIC and "function_signature" in str(s.operands)
        ]
        assert (
            len(symbolics) == 0
        ), f"function_signature should not produce SYMBOLIC: {symbolics}"

    def test_overload_implementation_still_lowered(self):
        ir = _parse_ts("""
            function greet(name: string): string;
            function greet(name: string, greeting: string): string;
            function greet(name: any, greeting?: any): any { return name; }
            """)
        stores = _find_all(ir, Opcode.DECL_VAR)
        store_names = [s.operands[0] for s in stores if s.operands]
        assert (
            "greet" in store_names
        ), f"Expected implementation 'greet' lowered, got: {store_names}"


class TestAmbientDeclaration:
    """ambient_declaration (declare ...) should emit no IR."""

    def test_declare_const_no_symbolic(self):
        ir = _parse_ts("declare const DEBUG: boolean;")
        symbolics = [
            s
            for s in ir
            if s.opcode == Opcode.SYMBOLIC and "ambient_declaration" in str(s.operands)
        ]
        assert (
            len(symbolics) == 0
        ), f"ambient_declaration should not produce SYMBOLIC: {symbolics}"

    def test_declare_function_no_symbolic(self):
        ir = _parse_ts("declare function log(msg: string): void;")
        symbolics = [
            s
            for s in ir
            if s.opcode == Opcode.SYMBOLIC and "ambient_declaration" in str(s.operands)
        ]
        assert (
            len(symbolics) == 0
        ), f"ambient_declaration should not produce SYMBOLIC: {symbolics}"

    def test_declare_module_no_symbolic(self):
        ir = _parse_ts("declare module 'lodash' { export function foo(): void; }")
        symbolics = [
            s
            for s in ir
            if s.opcode == Opcode.SYMBOLIC and "ambient_declaration" in str(s.operands)
        ]
        assert (
            len(symbolics) == 0
        ), f"ambient_declaration should not produce SYMBOLIC: {symbolics}"


class TestInstantiationExpression:
    """instantiation_expression: fn<Type> should lower the function ref, discard type args."""

    def test_simple_identifier(self):
        ir = _parse_ts("""
            function identity(x: any): any { return x; }
            const strId = identity<string>;
            """)
        symbolics = [
            s
            for s in ir
            if s.opcode == Opcode.SYMBOLIC
            and "instantiation_expression" in str(s.operands)
        ]
        assert (
            len(symbolics) == 0
        ), f"instantiation_expression should not produce SYMBOLIC: {symbolics}"
        stores = _find_all(ir, Opcode.DECL_VAR)
        store_names = [s.operands[0] for s in stores if s.operands]
        assert "strId" in store_names, f"Expected 'strId' binding, got: {store_names}"

    def test_loads_function_ref(self):
        ir = _parse_ts("""
            function identity(x: any): any { return x; }
            const f = identity<number>;
            """)
        loads = _find_all(ir, Opcode.LOAD_VAR)
        load_names = [l.operands[0] for l in loads if l.operands]
        assert (
            "identity" in load_names
        ), f"Expected LOAD_VAR for 'identity', got: {load_names}"

    def test_member_expression(self):
        ir = _parse_ts("""
            const obj = { method: function(x: any): any { return x; } };
            const f = obj.method<string>;
            """)
        symbolics = [
            s
            for s in ir
            if s.opcode == Opcode.SYMBOLIC
            and "instantiation_expression" in str(s.operands)
        ]
        assert (
            len(symbolics) == 0
        ), f"instantiation_expression should not produce SYMBOLIC: {symbolics}"
