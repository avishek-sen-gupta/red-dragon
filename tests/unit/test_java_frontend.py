"""Tests for JavaFrontend — tree-sitter Java AST to IR lowering."""

from __future__ import annotations

from interpreter.frontends.java import JavaFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import Opcode
from interpreter.instructions import InstructionBase
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder


def _parse_java(source: str) -> list[InstructionBase]:
    frontend = JavaFrontend(TreeSitterParserFactory(), "java")
    return frontend.lower(source.encode("utf-8"))


def _parse_java_with_types(
    source: str,
) -> tuple[list[InstructionBase], TypeEnvironmentBuilder]:
    frontend = JavaFrontend(TreeSitterParserFactory(), "java")
    instructions = frontend.lower(source.encode("utf-8"))
    return instructions, frontend.type_env_builder


def _opcodes(instructions: list[InstructionBase]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(
    instructions: list[InstructionBase], opcode: Opcode
) -> list[InstructionBase]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestJavaSmoke:
    def test_empty_program(self):
        instructions = _parse_java("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_class_wrapper(self):
        instructions = _parse_java("class M { }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("M" in inst.operands for inst in stores)


class TestJavaVariables:
    def test_local_variable_declaration(self):
        instructions = _parse_java("class M { void m() { int x = 10; } }")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.DECL_VAR in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_variable_without_initializer(self):
        instructions = _parse_java("class M { void m() { int x; } }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("None" in inst.operands for inst in consts)

    def test_assignment_expression(self):
        instructions = _parse_java("class M { void m() { int x; x = 5; } }")
        decls = _find_all(instructions, Opcode.DECL_VAR)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        x_decls = [inst for inst in decls if "x" in inst.operands]
        x_stores = [inst for inst in stores if "x" in inst.operands]
        assert len(x_decls) == 1
        assert len(x_stores) == 1


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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)
        # Cast is lowered as pass-through: d flows directly into x
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("d" in inst.operands for inst in loads)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

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
        assert len(calls) == 1
        assert any("println" in inst.operands for inst in calls)

    def test_standalone_method_call(self):
        instructions = _parse_java("class M { void m() { foo(1, 2); } }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) == 1
        assert "foo" in calls[0].operands

    def test_object_creation(self):
        instructions = _parse_java('class M { void m() { Dog d = new Dog("Rex"); } }')
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("Dog" in inst.operands for inst in calls)
        # Constructor argument "Rex" should be loaded as a CONST
        consts = _find_all(instructions, Opcode.CONST)
        assert any('"Rex"' in str(inst.operands) for inst in consts)
        # Result stored in variable d
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("d" in inst.operands for inst in stores)


class TestJavaControlFlow:
    def test_if_else(self):
        instructions = _parse_java(
            "class M { void m() { if (x > 5) { y = 1; } else { y = 0; } } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        assert Opcode.BRANCH in opcodes

    def test_nested_if_else_chain(self):
        instructions = _parse_java(
            'class M { void m() { if (x > 100) { grade = "A"; }'
            ' else if (x > 50) { grade = "B"; }'
            ' else { grade = "F"; } } }'
        )
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("grade" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert len(binops) >= 2

    def test_while_loop(self):
        instructions = _parse_java("class M { void m() { while (x > 0) { x--; } } }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any(inst.label.contains("while") for inst in labels)

    def test_c_style_for_loop(self):
        instructions = _parse_java(
            "class M { void m() { for (int i = 0; i < 10; i++) { x = x + i; } } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("i" in inst.operands for inst in stores)

    def test_enhanced_for_loop(self):
        instructions = _parse_java(
            "class M { void m() { int[] items = {1,2,3}; for (int x : items) { y = x; } } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LOAD_INDEX in opcodes

    def test_if_elseif_chain_all_branches_produce_ir(self):
        """All branches of if/else-if/else-if/else must produce IR."""
        instructions = _parse_java(
            "class M { void m() { if (x==1) { y=10; }"
            " else if (x==2) { y=20; }"
            " else if (x==3) { y=30; }"
            " else { y=40; } } }"
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
            target for inst in branch_ifs for target in inst.branch_targets
        }
        label_set = set(labels)
        assert branch_targets.issubset(
            label_set
        ), f"Unreachable targets: {branch_targets - label_set}"


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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)

    def test_interface_emits_class_block(self):
        """Interface lowered as CLASS block with method defs (not NEW_OBJECT)."""
        instructions = _parse_java("interface Runnable { void run(); }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            "class_" in str(c.operands) and "Runnable" in str(c.operands)
            for c in consts
        )
        labels = [
            str(inst.label) for inst in instructions if inst.opcode == Opcode.LABEL
        ]
        assert any("func_" in l and "run" in l for l in labels)

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

    def test_synchronized_no_longer_unsupported(self):
        instructions = _parse_java("class M { void m() { synchronized(this) { } } }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


def _labels_in_order(instructions: list[InstructionBase]) -> list[str]:
    return [str(inst.label) for inst in instructions if inst.opcode == Opcode.LABEL]


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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("result" in inst.operands for inst in stores)

    def test_interface_and_instanceof(self):
        source = """\
interface Shape {}
class Circle implements Shape {
    double radius;
    Circle(double r) { this.radius = r; }
    boolean check(Object o) { return o instanceof Shape; }
}
"""
        instructions = _parse_java(source)
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            "class_" in str(c.operands) and "Shape" in str(c.operands) for c in consts
        )
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Circle" in inst.operands for inst in stores)
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("radius" in inst.operands for inst in store_fields)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("isinstance" in inst.operands for inst in calls)

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
        labels = [str(i.label) for i in instructions if i.opcode == Opcode.LABEL]
        branches = [i.label for i in instructions if i.opcode == Opcode.BRANCH]
        # try/catch body and catch block are lowered with LABEL/BRANCH
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_end" in l for l in labels)
        assert Opcode.THROW in opcodes
        # No catch_clause: or finally_clause: SYMBOLIC placeholders
        symbolics = [i for i in instructions if i.opcode == Opcode.SYMBOLIC]
        assert not any("catch_clause:" in str(s.operands) for s in symbolics)
        assert len(instructions) > 10

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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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


class TestJavaMethodReference:
    def test_type_method_reference(self):
        instructions = _parse_java(
            "class M { void m() { Function f = String::valueOf; } }"
        )
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("valueOf" in inst.operands for inst in loads)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("method_reference" in str(inst.operands) for inst in symbolics)

    def test_this_method_reference(self):
        instructions = _parse_java(
            "class M { void m() { Runnable r = this::doStuff; } }"
        )
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("doStuff" in inst.operands for inst in loads)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("method_reference" in str(inst.operands) for inst in symbolics)

    def test_constructor_reference(self):
        instructions = _parse_java(
            "class M { void m() { Supplier s = ArrayList::new; } }"
        )
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("new" in inst.operands for inst in loads)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("method_reference" in str(inst.operands) for inst in symbolics)


class TestJavaClassLiteral:
    def test_class_literal(self):
        instructions = _parse_java("class M { void m() { Class c = String.class; } }")
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("class" in inst.operands for inst in loads)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("class_literal" in str(inst.operands) for inst in symbolics)

    def test_class_literal_in_expression(self):
        instructions = _parse_java(
            "class M { void m() { boolean b = Integer.class.equals(x.getClass()); } }"
        )
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("class" in inst.operands for inst in loads)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("class_literal" in str(inst.operands) for inst in symbolics)


class TestJavaLambdaExpression:
    def test_lambda_expression_body(self):
        instructions = _parse_java(
            'class M { void m() { Runnable r = () -> System.out.println("hi"); } }'
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("lambda_expression" in str(inst.operands) for inst in symbolics)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1

    def test_lambda_with_params_and_block(self):
        instructions = _parse_java(
            "class M { void m() { Comparator c = (a, b) -> { return a - b; }; } }"
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("a" in p for p in param_names)
        assert any("b" in p for p in param_names)
        assert not any("lambda_expression" in str(inst.operands) for inst in symbolics)
        assert Opcode.BINOP in _opcodes(instructions)

    def test_lambda_with_typed_params(self):
        instructions = _parse_java(
            "class M { void m() { BiFunction f = (int x, int y) -> x + y; } }"
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("x" in p for p in param_names)
        assert any("y" in p for p in param_names)
        assert not any("lambda_expression" in str(inst.operands) for inst in symbolics)

    def test_lambda_emits_func_ref(self):
        instructions = _parse_java(
            "class M { void m() { Runnable r = () -> doStuff(); } }"
        )
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            any(
                str(op).startswith("func_") and "lambda" in str(op)
                for op in inst.operands
            )
            for inst in consts
        )


class TestJavaInstanceof:
    def test_instanceof_expression(self):
        instructions = _parse_java(
            "class M { void m() { boolean b = obj instanceof String; } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.CALL_FUNCTION in opcodes
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("isinstance" in inst.operands for inst in calls)

    def test_instanceof_in_condition(self):
        instructions = _parse_java(
            "class M { void m() { if (x instanceof Number) { y = 1; } } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.CALL_FUNCTION in opcodes
        assert Opcode.BRANCH_IF in opcodes


class TestJavaSuperExpression:
    def test_super_field_access(self):
        instructions = _parse_java(
            "class M extends B { void m() { int x = super.field; } }"
        )
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("field" in inst.operands for inst in loads)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    def test_super_method_call(self):
        instructions = _parse_java(
            "class M extends B { void m() { super.doStuff(1); } }"
        )
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("doStuff" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


class TestJavaDoStatement:
    def test_do_while_basic(self):
        instructions = _parse_java(
            "class M { void m() { int x = 0; do { x = x + 1; } while (x < 10); } }"
        )
        labels = [
            str(inst.label) for inst in instructions if inst.opcode == Opcode.LABEL
        ]
        assert any("do_body" in l for l in labels)
        assert any("do_cond" in l for l in labels)
        assert any("do_end" in l for l in labels)
        assert Opcode.BRANCH_IF in _opcodes(instructions)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    def test_do_while_with_break(self):
        instructions = _parse_java(
            "class M { void m() { do { if (done) { break; } } while (true); } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes


class TestJavaAssertStatement:
    def test_assert_simple(self):
        instructions = _parse_java("class M { void m() { assert x > 0; } }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("assert" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    def test_assert_with_message(self):
        instructions = _parse_java(
            'class M { void m() { assert x > 0 : "x must be positive"; } }'
        )
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("assert" in inst.operands for inst in calls)
        assert_call = next(c for c in calls if "assert" in c.operands)
        assert len(assert_call.operands) >= 3  # "assert", cond_reg, msg_reg


class TestJavaLabeledStatement:
    def test_labeled_statement(self):
        instructions = _parse_java(
            "class M { void m() { outer: for (int i = 0; i < 5; i++) { x = i; } } }"
        )
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("i" in inst.operands for inst in stores)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


class TestJavaSynchronizedStatement:
    def test_synchronized_block(self):
        instructions = _parse_java(
            "class M { void m() { synchronized(lock) { x = 1; } } }"
        )
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    def test_synchronized_this(self):
        instructions = _parse_java(
            "class M { void m() { synchronized(this) { doStuff(); } } }"
        )
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("doStuff" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


class TestJavaStaticInitializer:
    def test_static_initializer_block(self):
        instructions = _parse_java("class M { static { x = 10; } }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    def test_static_initializer_with_method_call(self):
        instructions = _parse_java("class M { static { init(); } }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("init" in inst.operands for inst in calls)


class TestJavaExplicitConstructorInvocation:
    def test_super_constructor_call(self):
        instructions = _parse_java(
            "class M extends B { M(int x) { super(x); this.val = x; } }"
        )
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("super" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    def test_this_constructor_call(self):
        instructions = _parse_java("class M { M() { this(0); } M(int x) { } }")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("__init__" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


class TestJavaAnnotationTypeDeclaration:
    def test_annotation_type(self):
        instructions = _parse_java("public @interface MyAnnotation { String value(); }")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("annotation:MyAnnotation" in str(inst.operands) for inst in new_objs)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("MyAnnotation" in inst.operands for inst in stores)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    def test_annotation_type_with_members(self):
        instructions = _parse_java(
            "public @interface Config { String name(); int value(); }"
        )
        store_indexes = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(store_indexes) >= 2


class TestJavaRecordDeclaration:
    def test_record_basic(self):
        instructions = _parse_java("record Point(int x, int y) { }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Point" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    def test_record_with_method(self):
        instructions = _parse_java(
            "record Point(int x, int y) { double distance() { return Math.sqrt(x*x + y*y); } }"
        )
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Point" in inst.operands for inst in stores)
        assert any("distance" in inst.operands for inst in stores)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1

    def test_record_empty_body(self):
        instructions = _parse_java("record Empty() { }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Empty" in inst.operands for inst in stores)
        labels = [
            str(inst.label) for inst in instructions if inst.opcode == Opcode.LABEL
        ]
        assert any("class_Empty" in l for l in labels)
        assert any("end_class_Empty" in l for l in labels)


class TestJavaScopedIdentifier:
    def test_scoped_identifier_in_annotation(self):
        """Annotations use scoped_identifier for qualified names like java.lang.Override."""
        instructions = _parse_java("@java.lang.Override class M { }")
        # The annotation is lowered without producing SYMBOLIC for scoped_identifier
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("scoped_identifier" in str(inst.operands) for inst in symbolics)

    def test_scoped_identifier_dispatch_registered(self):
        """Verify scoped_identifier is registered in the expression dispatch table."""
        frontend = JavaFrontend(TreeSitterParserFactory(), "java")
        expr_dispatch = frontend._build_expr_dispatch()
        assert "scoped_identifier" in expr_dispatch


class TestJavaTextBlock:
    def test_text_block_basic(self):
        source = (
            'class M { void m() { String s = """\n    hello\n    world\n    """; } }'
        )
        instructions = _parse_java(source)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("hello" in str(inst.operands) for inst in consts)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("s" in inst.operands for inst in stores)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    def test_text_block_in_expression(self):
        source = 'class M { void m() { String s = """\n    SELECT *\n    FROM table\n    """.trim(); } }'
        instructions = _parse_java(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("trim" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    def test_text_block_assigned(self):
        source = (
            'class M { void m() { var json = """\n    {"key": "value"}\n    """; } }'
        )
        instructions = _parse_java(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("json" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("key" in str(inst.operands) for inst in consts)


class TestJavaSwitchExpression:
    def test_switch_expression_no_symbolic(self):
        source = 'class M { String m(int x) { return switch (x) { case 1 -> "one"; default -> "other"; }; } }'
        instructions = _parse_java(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("switch_expression" in str(inst.operands) for inst in symbolics)

    def test_switch_expression_returns_value(self):
        source = 'class M { String m(int x) { return switch (x) { case 1 -> "one"; default -> "other"; }; } }'
        instructions = _parse_java(source)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("__switch_result" in inst.operands[0] for inst in loads)


class TestJavaExpressionStatementInSwitch:
    def test_expression_statement_in_switch_expression(self):
        """expression_statement inside switch expression should not produce unsupported SYMBOLIC."""
        source = 'class M { String m(int day) { return switch (day) { case 1 -> "work"; default -> "rest"; }; } }'
        instructions = _parse_java(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_expression_statement_switch_multiple_cases(self):
        source = 'class M { String m(int x) { return switch (x) { case 1 -> "a"; case 2 -> "b"; default -> "c"; }; } }'
        instructions = _parse_java(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)


class TestJavaThrowStatementInSwitch:
    def test_throw_statement_in_switch_expression(self):
        """throw_statement inside switch expression should not produce unsupported SYMBOLIC."""
        source = """\
class M {
    String m(int x) {
        return switch (x) {
            case 1 -> "one";
            default -> throw new IllegalArgumentException("bad");
        };
    }
}
"""
        instructions = _parse_java(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)


class TestJavaGenericTypeSeeding:
    """Verify that Java generic types (List<String>, Map<K,V>) are extracted
    as parameterised bracket-notation strings in the TypeEnvironmentBuilder."""

    def test_local_var_list_of_string(self):
        """List<String> items = ... should seed var_types['items'] = 'List[String]'."""
        source = "class M { void m() { List<String> items = new ArrayList<>(); } }"
        _, builder = _parse_java_with_types(source)
        assert builder.var_types["items"] == "List[String]"

    def test_local_var_map_of_string_integer(self):
        """Map<String, Integer> m = ... should seed 'Map[String, Int]' (Integer normalised)."""
        source = "class M { void m() { Map<String, Integer> m = new HashMap<>(); } }"
        _, builder = _parse_java_with_types(source)
        assert builder.var_types["m"] == "Map[String, Int]"

    def test_nested_generic_type(self):
        """List<Map<String, Integer>> should produce 'List[Map[String, Int]]'."""
        source = "class M { void m() { List<Map<String, Integer>> x = null; } }"
        _, builder = _parse_java_with_types(source)
        assert builder.var_types["x"] == "List[Map[String, Int]]"

    def test_method_return_generic_type(self):
        """Method returning List<String> should seed func_return_types with 'List[String]'."""
        source = "class M { List<String> getNames() { return null; } }"
        _, builder = _parse_java_with_types(source)
        return_types = builder.func_return_types
        assert any(v == "List[String]" for v in return_types.values())

    def test_param_generic_type(self):
        """Parameter List<String> items should seed param type 'List[String]'."""
        source = "class M { void process(List<String> items) { } }"
        _, builder = _parse_java_with_types(source)
        param_types = builder.func_param_types
        assert any(
            any(ptype == "List[String]" for _, ptype in params)
            for params in param_types.values()
        )

    def test_field_generic_type(self):
        """Field List<String> names; should seed var_types['names'] = 'List[String]'."""
        source = "class M { List<String> names = new ArrayList<>(); }"
        _, builder = _parse_java_with_types(source)
        assert builder.var_types["names"] == "List[String]"

    def test_non_generic_type_unchanged(self):
        """Plain int x = 42; should still seed 'Int' (regression check)."""
        source = "class M { void m() { int x = 42; } }"
        _, builder = _parse_java_with_types(source)
        assert builder.var_types["x"] == "Int"


class TestJavaHexFloatingPointLiteral:
    def test_hex_float_no_symbolic(self):
        """0x1.0p10 should not produce SYMBOLIC fallthrough."""
        ir = _parse_java("class T { void f() { double x = 0x1.0p10; } }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "hex_floating_point_literal" in str(inst.operands) for inst in symbolics
        )

    def test_hex_float_emits_const(self):
        """Hex floating point literal should emit a CONST instruction."""
        ir = _parse_java("class T { void f() { double x = 0x1.0p10; } }")
        consts = _find_all(ir, Opcode.CONST)
        assert any("0x1.0p10" in str(inst.operands) for inst in consts)

    def test_hex_float_stored(self):
        """Hex float should be stored to a variable."""
        ir = _parse_java("class T { void f() { double x = 0x1.0p10; } }")
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestJavaInterfaceLowering:
    """Java interfaces should lower methods as function definitions, not just member enumeration."""

    INTERFACE_SOURCE = """\
interface Shape {
    double area();
    String name();
}
"""

    def test_interface_methods_produce_func_labels(self):
        """Interface method declarations should emit LABEL instructions for function defs."""
        ir = _parse_java(self.INTERFACE_SOURCE)
        labels = [str(inst.label) for inst in ir if inst.opcode == Opcode.LABEL]
        func_labels = [l for l in labels if "func_" in l]
        assert any(
            "area" in l for l in func_labels
        ), f"Expected a function label for 'area', got labels: {func_labels}"
        assert any(
            "name" in l for l in func_labels
        ), f"Expected a function label for 'name', got labels: {func_labels}"

    def test_interface_methods_seed_return_types(self):
        """Interface methods should seed return types into the type environment builder."""
        ir, type_builder = _parse_java_with_types(self.INTERFACE_SOURCE)
        func_return_types = type_builder.func_return_types
        area_entries = {k: v for k, v in func_return_types.items() if "area" in k}
        name_entries = {k: v for k, v in func_return_types.items() if "name" in k}
        assert (
            len(area_entries) >= 1
        ), f"Expected return type seeded for 'area', got: {func_return_types}"
        assert (
            len(name_entries) >= 1
        ), f"Expected return type seeded for 'name', got: {func_return_types}"

    def test_interface_stored_as_class_ref(self):
        """Interface should be stored as a class reference, not a NEW_OBJECT."""
        ir = _parse_java(self.INTERFACE_SOURCE)
        consts = _find_all(ir, Opcode.CONST)
        class_refs = [c for c in consts if "class_" in str(c.operands)]
        assert any(
            "Shape" in str(c.operands) for c in class_refs
        ), f"Expected class ref for Shape, got consts: {[c.operands for c in consts]}"
        # Should NOT use NEW_OBJECT for interfaces
        new_objs = _find_all(ir, Opcode.NEW_OBJECT)
        iface_objs = [n for n in new_objs if "interface:" in str(n.operands)]
        assert (
            len(iface_objs) == 0
        ), "Interface should not use NEW_OBJECT enumeration pattern"


class TestJavaTypePattern:
    def test_instanceof_binds_variable(self):
        """o instanceof String s should bind 's' to the matched value."""
        ir = _parse_java(
            "class M { void m(Object o) {"
            "  if (o instanceof String s) { System.out.println(s); }"
            "} }"
        )
        stores_s = [
            inst
            for inst in ir
            if inst.opcode in (Opcode.STORE_VAR, Opcode.DECL_VAR)
            and len(inst.operands) >= 1
            and str(inst.operands[0]) == "s"
        ]
        assert len(stores_s) >= 1, "instanceof type_pattern did not bind 's'"

    def test_switch_type_pattern_no_symbolic(self):
        """case String s -> ... should not produce SYMBOLIC unsupported:pattern."""
        ir = _parse_java(
            "class M { String m(Object o) {"
            '  return switch(o) { case String s -> s; default -> ""; };'
            "} }"
        )
        symbolics = [
            inst
            for inst in ir
            if inst.opcode == Opcode.SYMBOLIC
            and "unsupported" in str(inst.operands)
            and "pattern" in str(inst.operands)
        ]
        assert len(symbolics) == 0, f"type_pattern produced SYMBOLIC: {symbolics}"

    def test_switch_type_pattern_emits_isinstance(self):
        """case String s should emit an isinstance check."""
        ir = _parse_java(
            "class M { String m(Object o) {"
            '  return switch(o) { case String s -> s; default -> ""; };'
            "} }"
        )
        isinstance_calls = [
            inst
            for inst in ir
            if inst.opcode == Opcode.CALL_FUNCTION
            and len(inst.operands) >= 1
            and str(inst.operands[0]) == "isinstance"
        ]
        assert len(isinstance_calls) >= 1


class TestJavaRecordPatternInstanceof:
    def test_instanceof_record_pattern_binds_components(self):
        """o instanceof Point(int a, int b) should bind a and b."""
        ir = _parse_java(
            "class M { record Point(int x, int y) {}"
            "  void m(Object o) {"
            "    if (o instanceof Point(int a, int b)) {"
            "      System.out.println(a);"
            "    }"
            "  }"
            "}"
        )
        stores_a = [
            inst
            for inst in ir
            if inst.opcode in (Opcode.STORE_VAR, Opcode.DECL_VAR)
            and len(inst.operands) >= 1
            and str(inst.operands[0]) == "a"
        ]
        stores_b = [
            inst
            for inst in ir
            if inst.opcode in (Opcode.STORE_VAR, Opcode.DECL_VAR)
            and len(inst.operands) >= 1
            and str(inst.operands[0]) == "b"
        ]
        assert len(stores_a) >= 1, "record_pattern did not bind 'a'"
        assert len(stores_b) >= 1, "record_pattern did not bind 'b'"


class TestJavaStringLengthExecution:
    def test_string_length_returns_concrete(self):
        """s.length() on a concrete string should return a concrete int."""
        from interpreter.run import run
        from interpreter.types.typed_value import unwrap_locals

        vm = run(
            'class M { static int result = "hello".length(); }',
            language="java",
            max_steps=100,
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars["result"] == 5
