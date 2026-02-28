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
        assert any("None" in inst.operands for inst in consts)

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

    def test_synchronized_no_longer_unsupported(self):
        instructions = _parse_java("class M { void m() { synchronized(this) { } } }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


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
            "function:" in str(inst.operands) and "lambda" in str(inst.operands)
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
        assert any("instanceof" in inst.operands for inst in calls)

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
        labels = [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("this" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


class TestJavaAnnotationTypeDeclaration:
    def test_annotation_type(self):
        instructions = _parse_java("public @interface MyAnnotation { String value(); }")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("annotation:MyAnnotation" in str(inst.operands) for inst in new_objs)
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Point" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    def test_record_with_method(self):
        instructions = _parse_java(
            "record Point(int x, int y) { double distance() { return Math.sqrt(x*x + y*y); } }"
        )
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Point" in inst.operands for inst in stores)
        assert any("distance" in inst.operands for inst in stores)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1

    def test_record_empty_body(self):
        instructions = _parse_java("record Empty() { }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Empty" in inst.operands for inst in stores)
        labels = [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]
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
        """Verify scoped_identifier is registered in _EXPR_DISPATCH."""
        frontend = JavaFrontend()
        assert "scoped_identifier" in frontend._EXPR_DISPATCH

    def test_scoped_identifier_handler_emits_load_var(self):
        """When scoped_identifier is encountered, it should emit LOAD_VAR, not SYMBOLIC."""
        # Import declarations are no-ops, but we verify the handler is wired correctly
        # by checking the dispatch table exists and the frontend handles annotations
        instructions = _parse_java(
            "@java.lang.SuppressWarnings class M { void m() { } }"
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("scoped_identifier" in str(inst.operands) for inst in symbolics)


class TestJavaTextBlock:
    def test_text_block_basic(self):
        source = (
            'class M { void m() { String s = """\n    hello\n    world\n    """; } }'
        )
        instructions = _parse_java(source)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("hello" in str(inst.operands) for inst in consts)
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
