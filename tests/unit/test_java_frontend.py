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

    def test_interface_emits_new_object(self):
        instructions = _parse_java("interface Runnable { void run(); }")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("interface:Runnable" in str(inst.operands) for inst in new_objs)
        store_indexes = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(store_indexes) >= 1

    def test_enum_declaration(self):
        instructions = _parse_java("enum Color { RED, GREEN, BLUE }")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("enum:Color" in str(inst.operands) for inst in new_objs)
        stores = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(stores) >= 3
        consts = _find_all(instructions, Opcode.CONST)
        const_vals = [inst.operands[0] for inst in consts if inst.operands]
        assert "RED" in const_vals
        assert "GREEN" in const_vals
        assert "BLUE" in const_vals

    def test_enum_single_member(self):
        instructions = _parse_java("enum Status { ACTIVE }")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("enum:Status" in str(inst.operands) for inst in new_objs)
        stores = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(stores) >= 1


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


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialJava:
    def test_enhanced_for_with_conditional_accumulator(self):
        source = """\
class M {
    void m() {
        int[] nums = {1, 2, 3, 4, 5};
        int total = 0;
        for (int n : nums) {
            if (n > 2) {
                total = total + n;
            }
        }
    }
}
"""
        instructions = _parse_java(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LOAD_INDEX in opcodes
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("total" in inst.operands for inst in stores)
        assert len(instructions) > 20

    def test_method_chaining(self):
        source = """\
class M {
    void m() {
        String result = new StringBuilder()
            .append("hello")
            .append(" ")
            .append("world")
            .toString();
    }
}
"""
        instructions = _parse_java(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        assert method_names.count("append") >= 3
        assert "toString" in method_names
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)

    def test_interface_and_instanceof(self):
        source = """\
interface Shape {}
class Circle implements Shape {
    double radius;
    Circle(double r) { this.radius = r; }
}
"""
        instructions = _parse_java(source)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("interface:Shape" in str(inst.operands) for inst in new_objs)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Circle" in inst.operands for inst in stores)
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("radius" in inst.operands for inst in store_fields)

    def test_try_catch_with_throw(self):
        source = """\
class M {
    void m() {
        try {
            int result = riskyOp();
            System.out.println(result);
        } catch (Exception e) {
            throw new RuntimeException("failed: " + e.getMessage());
        }
    }
}
"""
        instructions = _parse_java(source)
        opcodes = _opcodes(instructions)
        labels = [i.label for i in instructions if i.opcode == Opcode.LABEL]
        branches = [i.label for i in instructions if i.opcode == Opcode.BRANCH]
        # try/catch body and catch block are lowered with LABEL/BRANCH
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_end" in l for l in labels)
        assert Opcode.THROW in opcodes
        # No catch_clause: or finally_clause: SYMBOLIC placeholders
        symbolics = [i for i in instructions if i.opcode == Opcode.SYMBOLIC]
        assert not any("catch_clause:" in str(s.operands) for s in symbolics)
        assert len(instructions) > 3

    def test_constructor_with_field_init(self):
        source = """\
class Dog {
    String name;
    int age;
    Dog(String n, int a) {
        this.name = n;
        this.age = a;
    }
    String describe() {
        return name + " is " + age;
    }
}
"""
        instructions = _parse_java(source)
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("name" in str(inst.operands) for inst in store_fields)
        assert any("age" in str(inst.operands) for inst in store_fields)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        assert len(instructions) > 20

    def test_nested_for_loops_with_array(self):
        source = """\
class M {
    void m() {
        int[][] grid = {{1,2},{3,4}};
        int sum = 0;
        for (int i = 0; i < 2; i++) {
            for (int j = 0; j < 2; j++) {
                sum = sum + grid[i][j];
            }
        }
    }
}
"""
        instructions = _parse_java(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("sum" in inst.operands for inst in stores)
        assert any("i" in inst.operands for inst in stores)
        assert any("j" in inst.operands for inst in stores)
        assert len(instructions) > 25

    def test_enum_usage(self):
        source = """\
enum Color { RED, GREEN, BLUE }
class M {
    void m() {
        if (c == Color.RED) {
            x = 1;
        } else {
            x = 0;
        }
    }
}
"""
        instructions = _parse_java(source)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("enum:Color" in str(inst.operands) for inst in new_objs)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes

    def test_while_with_method_calls(self):
        source = """\
class M {
    void m() {
        int count = 0;
        while (count < 10) {
            System.out.println(count);
            list.add(count);
            count = count + 1;
        }
    }
}
"""
        instructions = _parse_java(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        assert "println" in method_names
        assert "add" in method_names
        labels = _labels_in_order(instructions)
        assert any("while" in lbl for lbl in labels)
        assert len(instructions) > 20


class TestJavaArrayCreation:
    def test_array_creation_with_initializer(self):
        instructions = _parse_java(
            "class M { void m() { int[] a = new int[]{1, 2, 3}; } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        stores = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(stores) >= 3

    def test_array_creation_sized(self):
        instructions = _parse_java("class M { void m() { int[] a = new int[5]; } }")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes

    def test_array_initializer_bare(self):
        instructions = _parse_java("class M { void m() { int[] a = {1, 2, 3}; } }")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        stores = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(stores) >= 3


class TestJavaInstanceof:
    def test_instanceof_expression(self):
        instructions = _parse_java(
            "class M { void m() { boolean b = obj instanceof String; } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.CALL_FUNCTION in opcodes
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("instanceof" in inst.operands for inst in calls)

    def test_instanceof_in_condition(self):
        instructions = _parse_java(
            "class M { void m() { if (x instanceof Number) { y = 1; } } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.CALL_FUNCTION in opcodes
        assert Opcode.BRANCH_IF in opcodes
