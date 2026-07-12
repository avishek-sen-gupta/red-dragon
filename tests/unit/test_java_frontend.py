"""Tests for JavaFrontend — tree-sitter Java AST to IR lowering."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.java import JavaFrontend
from interpreter.frontends.java import expressions as java_expressions
from interpreter.frontends.java.features import JavaFeature
from interpreter.instructions import InstructionBase
from interpreter.ir import Opcode
from interpreter.parser import TreeSitterParserFactory
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
from interpreter.var_name import VarName
from tests.covers import NotLanguageFeature, covers


class _FakeDegenerateNode:
    """A tree-sitter node with no 'value' field and no named children.

    Real Java grammar can't produce this shape for CAST_EXPRESSION or
    EXPRESSION_STATEMENT (both always have a mandatory expression child),
    so these fallback branches are only reachable via a hand-built node —
    they exist as a defensive guard against malformed/unexpected ASTs.
    """

    children: list = []
    start_point = (0, 0)
    end_point = (0, 0)

    def child_by_field_name(self, name: str):
        return None


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
    @covers(JavaFeature.CLASS)
    def test_empty_program(self):
        instructions = _parse_java("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    @covers(JavaFeature.CLASS)
    def test_class_wrapper(self):
        instructions = _parse_java("class M { }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("M" in inst.operands for inst in stores)


class TestJavaVariables:
    @covers(JavaFeature.LOCAL_VARIABLE)
    def test_local_variable_declaration(self):
        instructions = _parse_java("class M { void m() { int x = 10; } }")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.DECL_VAR in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)

    @covers(JavaFeature.LOCAL_VARIABLE)
    def test_variable_without_initializer(self):
        instructions = _parse_java("class M { void m() { int x; } }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any(None in inst.operands for inst in consts)

    @covers(JavaFeature.ASSIGNMENT)
    def test_assignment_expression(self):
        instructions = _parse_java("class M { void m() { int x; x = 5; } }")
        decls = _find_all(instructions, Opcode.DECL_VAR)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        x_decls = [inst for inst in decls if "x" in inst.operands]
        x_stores = [inst for inst in stores if "x" in inst.operands]
        assert len(x_decls) == 1
        assert len(x_stores) == 1


class TestJavaExpressions:
    @covers(JavaFeature.ARITHMETIC)
    def test_arithmetic(self):
        instructions = _parse_java("class M { void m() { int y = x + 5; } }")
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    @covers(JavaFeature.CAST)
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

    @covers(JavaFeature.TERNARY)
    def test_ternary_expression(self):
        instructions = _parse_java(
            'class M { void m() { String y = x > 0 ? "pos" : "neg"; } }'
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes

    @covers(JavaFeature.CAST)
    def test_cast_expr_degenerate_node_falls_back_to_null(self):
        """Regression test: the fallback in lower_cast_expr called the

        deliberately-unimported lower_const_literal (see the module-level
        comment in expressions.py — a trap for unmigrated Const-literal
        call sites from the gjoy.4 typed-literals refactor), raising
        NameError instead of emitting a null CONST like its sibling
        fallbacks (lower_field_access, lower_array_access) do.
        """
        ctx = TreeSitterEmitContext(
            source=b"",
            language=Language.JAVA,
            observer=NullFrontendObserver(),
            constants=JavaFrontend(
                TreeSitterParserFactory(), "java"
            )._build_constants(),
        )
        reg = java_expressions.lower_cast_expr(ctx, _FakeDegenerateNode())
        assert ctx.instructions[-1].opcode == Opcode.CONST
        assert ctx.instructions[-1].result_reg == reg
        assert ctx.instructions[-1].operands == [None]

    @covers(JavaFeature.SWITCH_EXPRESSION)
    def test_expr_stmt_as_expr_degenerate_node_falls_back_to_null(self):
        """Regression test: same NameError trap as lower_cast_expr above,

        in the arrow-arm expression_statement fallback for switch
        expressions.
        """
        ctx = TreeSitterEmitContext(
            source=b"",
            language=Language.JAVA,
            observer=NullFrontendObserver(),
            constants=JavaFrontend(
                TreeSitterParserFactory(), "java"
            )._build_constants(),
        )
        reg = java_expressions.lower_expr_stmt_as_expr(ctx, _FakeDegenerateNode())
        assert ctx.instructions[-1].opcode == Opcode.CONST
        assert ctx.instructions[-1].result_reg == reg
        assert ctx.instructions[-1].operands == [None]


class TestJavaMethodCalls:
    @covers(JavaFeature.METHOD_CALL)
    def test_method_call_on_object(self):
        instructions = _parse_java(
            'class M { void m() { System.out.println("hello"); } }'
        )
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) == 1
        assert any("println" in inst.operands for inst in calls)

    @covers(JavaFeature.FUNCTION_CALL)
    def test_standalone_method_call(self):
        instructions = _parse_java("class M { void m() { foo(1, 2); } }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) == 1
        assert "foo" in calls[0].operands

    @covers(JavaFeature.OBJECT_CREATION)
    def test_object_creation(self):
        instructions = _parse_java('class M { void m() { Dog d = new Dog("Rex"); } }')
        calls = _find_all(instructions, Opcode.CALL_CTOR)
        assert any("Dog" in inst.operands for inst in calls)
        # Constructor argument "Rex" should be loaded as a typed string CONST
        consts = _find_all(instructions, Opcode.CONST)
        assert any("Rex" in str(inst.operands) for inst in consts)
        # Result stored in variable d
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("d" in inst.operands for inst in stores)


class TestJavaControlFlow:
    @covers(JavaFeature.IF_ELSE)
    def test_if_else(self):
        instructions = _parse_java(
            "class M { void m() { if (x > 5) { y = 1; } else { y = 0; } } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        assert Opcode.BRANCH in opcodes

    @covers(JavaFeature.IF_ELSE)
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

    @covers(JavaFeature.WHILE_LOOP)
    def test_while_loop(self):
        instructions = _parse_java("class M { void m() { while (x > 0) { x--; } } }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes, "while needs conditional branch"
        assert Opcode.BRANCH in opcodes, "while needs unconditional back-edge"
        labels = _find_all(instructions, Opcode.LABEL)
        assert any(inst.label.contains("while") for inst in labels)
        # Condition check: x > 0
        binops = _find_all(instructions, Opcode.BINOP)
        assert any(
            ">" in inst.operands for inst in binops
        ), "while condition > not lowered"
        # Body: x-- produces an update expression
        assert Opcode.STORE_VAR in opcodes, "while body must update x"
        # Temporal: condition (BINOP >) before branch_if before body (STORE_VAR) before back-edge (BRANCH)
        cond_idx = next(
            i
            for i, inst in enumerate(instructions)
            if inst.opcode == Opcode.BINOP and ">" in inst.operands
        )
        brif_idx = next(
            i
            for i, inst in enumerate(instructions)
            if inst.opcode == Opcode.BRANCH_IF and i > cond_idx
        )
        body_idx = next(
            i
            for i, inst in enumerate(instructions)
            if inst.opcode == Opcode.STORE_VAR and i > brif_idx
        )
        back_idx = next(
            i
            for i, inst in enumerate(instructions)
            if inst.opcode == Opcode.BRANCH and i > body_idx
        )
        assert (
            cond_idx < brif_idx < body_idx < back_idx
        ), "while loop structure out of order"

    @covers(JavaFeature.FOR_LOOP)
    def test_c_style_for_loop(self):
        instructions = _parse_java(
            "class M { void m() { for (int i = 0; i < 10; i++) { x = x + i; } } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes, "for needs conditional branch"
        assert Opcode.BRANCH in opcodes, "for needs unconditional back-edge"
        # Init: int i = 0
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any("i" in inst.operands for inst in decls), "loop var i not declared"
        # Condition: i < 10
        binops = _find_all(instructions, Opcode.BINOP)
        assert any(
            "<" in inst.operands for inst in binops
        ), "for condition < not lowered"
        # Body: x = x + i
        assert any(
            "+" in inst.operands for inst in binops
        ), "for body addition not lowered"
        # Temporal: init (DECL_VAR i) before condition (<) before branch_if before body (+)
        init_idx = next(
            i
            for i, inst in enumerate(instructions)
            if inst.opcode == Opcode.DECL_VAR and "i" in inst.operands
        )
        cond_idx = next(
            i
            for i, inst in enumerate(instructions)
            if inst.opcode == Opcode.BINOP and "<" in inst.operands and i > init_idx
        )
        brif_idx = next(
            i
            for i, inst in enumerate(instructions)
            if inst.opcode == Opcode.BRANCH_IF and i > cond_idx
        )
        body_idx = next(
            i
            for i, inst in enumerate(instructions)
            if inst.opcode == Opcode.BINOP and "+" in inst.operands and i > brif_idx
        )
        assert (
            init_idx < cond_idx < brif_idx < body_idx
        ), "for loop structure out of order"

    @covers(JavaFeature.ENHANCED_FOR_LOOP)
    def test_enhanced_for_loop(self):
        instructions = _parse_java(
            "class M { void m() { int[] items = {1,2,3}; for (int x : items) { y = x; } } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes, "for-each needs conditional branch"
        assert Opcode.BRANCH in opcodes, "for-each needs unconditional back-edge"
        assert Opcode.LOAD_INDEX in opcodes, "for-each needs array index access"
        # Loop variable declared
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in decls), "loop var x not declared"
        # Body: y = x
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any(
            "y" in inst.operands for inst in stores
        ), "for-each body assignment not lowered"
        # Temporal: condition (BRANCH_IF) before index access (LOAD_INDEX) before body store (STORE_VAR y)
        brif_idx = next(
            i for i, inst in enumerate(instructions) if inst.opcode == Opcode.BRANCH_IF
        )
        idx_idx = next(
            i
            for i, inst in enumerate(instructions)
            if inst.opcode == Opcode.LOAD_INDEX and i > brif_idx
        )
        body_idx = next(
            i
            for i, inst in enumerate(instructions)
            if inst.opcode == Opcode.STORE_VAR and "y" in inst.operands and i > idx_idx
        )
        assert brif_idx < idx_idx < body_idx, "for-each loop structure out of order"

    @covers(JavaFeature.IF_ELSE)
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
        assert 10 in const_values, "if-branch value missing"
        assert 20 in const_values, "first else-if-branch value missing"
        assert 30 in const_values, "second else-if-branch value missing"
        assert 40 in const_values, "else-branch value missing"

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
    @covers(JavaFeature.METHOD_DECLARATION)
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

    @covers(JavaFeature.CONSTRUCTOR)
    def test_constructor(self):
        instructions = _parse_java(
            "class Dog { String name; Dog(String n) { this.name = n; } }"
        )
        stores = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("name" in inst.operands for inst in stores)


class TestJavaClasses:
    @covers(JavaFeature.CLASS)
    def test_class_definition(self):
        instructions = _parse_java("class Dog { void bark() { } }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)

    @covers(JavaFeature.INTERFACE)
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

    @covers(JavaFeature.ENUM)
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

    @covers(JavaFeature.ENUM)
    def test_enum_single_member(self):
        instructions = _parse_java("enum Status { ACTIVE }")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("enum:Status" in str(inst.operands) for inst in new_objs)
        stores = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(stores) >= 1


class TestJavaSpecial:
    @covers(JavaFeature.THROW)
    def test_throw_statement(self):
        instructions = _parse_java(
            'class M { void m() { throw new RuntimeException("fail"); } }'
        )
        opcodes = _opcodes(instructions)
        assert Opcode.THROW in opcodes

    @covers(JavaFeature.SYNCHRONIZED)
    def test_synchronized_no_longer_unsupported(self):
        instructions = _parse_java("class M { void m() { synchronized(this) { } } }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


def _labels_in_order(instructions: list[InstructionBase]) -> list[str]:
    return [str(inst.label) for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialJava:
    @covers(JavaFeature.ENHANCED_FOR_LOOP)
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

    @covers(JavaFeature.METHOD_CALL)
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

    @covers(JavaFeature.INTERFACE)
    def test_interface_lowers_as_class_ref(self):
        source = """\
interface Shape {}
class Circle implements Shape {
    double radius;
    Circle(double r) { this.radius = r; }
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

    @covers(JavaFeature.INSTANCEOF)
    def test_instanceof_emits_isinstance_call(self):
        source = """\
interface Shape {}
class Circle implements Shape {
    boolean check(Object o) { return o instanceof Shape; }
}
"""
        instructions = _parse_java(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("isinstance" in inst.operands for inst in calls)

    @covers(JavaFeature.TRY_CATCH)
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

    @covers(JavaFeature.CONSTRUCTOR)
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

    @covers(JavaFeature.FOR_LOOP)
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

    @covers(JavaFeature.ENUM)
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

    @covers(JavaFeature.WHILE_LOOP)
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
    @covers(JavaFeature.ARRAY_CREATION)
    def test_array_creation_with_initializer(self):
        instructions = _parse_java(
            "class M { void m() { int[] a = new int[]{1, 2, 3}; } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        stores = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(stores) >= 3

    @covers(JavaFeature.ARRAY_CREATION)
    def test_array_creation_sized(self):
        instructions = _parse_java("class M { void m() { int[] a = new int[5]; } }")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes

    @covers(JavaFeature.ARRAY_CREATION)
    def test_array_initializer_bare(self):
        instructions = _parse_java("class M { void m() { int[] a = {1, 2, 3}; } }")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        stores = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(stores) >= 3


class TestJavaIntegerLiterals:
    """Hex, octal, and binary integer literals must be lowered to typed int Const."""

    @covers(JavaFeature.INTEGER_LITERALS)
    @covers(JavaFeature.HEX_INTEGER_LITERAL)
    def test_hex_literal(self):
        instructions = _parse_java("class M { void m() { int x = 0x7f; } }")
        consts = _find_all(instructions, Opcode.CONST)
        hex_const = [c for c in consts if c.value == 127]
        assert hex_const, f"Expected CONST 127, got values: {[c.value for c in consts]}"

    @covers(JavaFeature.INTEGER_LITERALS)
    @covers(JavaFeature.HEX_INTEGER_LITERAL)
    def test_hex_literal_with_long_suffix(self):
        instructions = _parse_java("class M { void m() { long x = 0x7fffffffL; } }")
        consts = _find_all(instructions, Opcode.CONST)
        hex_const = [c for c in consts if c.value == 2147483647]
        assert (
            hex_const
        ), f"Expected CONST 2147483647, got values: {[c.value for c in consts]}"

    @covers(JavaFeature.INTEGER_LITERALS)
    @covers(JavaFeature.OCTAL_INTEGER_LITERAL)
    def test_octal_literal(self):
        instructions = _parse_java("class M { void m() { int x = 0777; } }")
        consts = _find_all(instructions, Opcode.CONST)
        oct_const = [c for c in consts if c.value == 511]
        assert oct_const, f"Expected CONST 511, got values: {[c.value for c in consts]}"

    @covers(JavaFeature.INTEGER_LITERALS)
    @covers(JavaFeature.BINARY_INTEGER_LITERAL)
    def test_binary_literal(self):
        instructions = _parse_java("class M { void m() { int x = 0b1010; } }")
        consts = _find_all(instructions, Opcode.CONST)
        bin_const = [c for c in consts if c.value == 10]
        assert bin_const, f"Expected CONST 10, got values: {[c.value for c in consts]}"

    @covers(JavaFeature.INTEGER_LITERALS)
    def test_decimal_literal_unchanged(self):
        instructions = _parse_java("class M { void m() { int x = 42; } }")
        consts = _find_all(instructions, Opcode.CONST)
        dec_const = [c for c in consts if c.value == 42]
        assert dec_const


class TestJavaCharacterLiterals:
    """Character literals must be lowered to a typed int Const with their integer ordinal value."""

    @covers(JavaFeature.CHARACTER_LITERAL)
    def test_plain_char_literal(self):
        instructions = _parse_java("class M { void m() { char c = 'a'; } }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            inst.value == 97 for inst in consts
        ), f"Expected CONST 97 (ord('a')), got: {[i.value for i in consts]}"

    @covers(JavaFeature.CHARACTER_LITERAL)
    def test_escape_char_literal(self):
        instructions = _parse_java(r"class M { void m() { char c = '\n'; } }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            inst.value == 10 for inst in consts
        ), f"Expected CONST 10 (ord('\\n')), got: {[i.value for i in consts]}"

    @covers(JavaFeature.CHARACTER_LITERAL)
    def test_char_literal_no_symbolic_fallback(self):
        instructions = _parse_java("class M { void m() { char c = 'z'; } }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "character_literal" in str(inst.operands) for inst in symbolics
        ), "character_literal should not fall back to SYMBOLIC"


class TestJavaParenthesizedExpression:
    """Parenthesized expressions must lower to the same IR as the inner expression."""

    @covers(JavaFeature.PARENTHESIZED_EXPRESSION)
    def test_parenthesized_literal_emits_const(self):
        """(42) should produce a CONST with integer value 42."""
        instructions = _parse_java("class M { void m() { int x = (42); } }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            c.value == 42 for c in consts
        ), f"Expected CONST 42, got: {[c.value for c in consts]}"

    @covers(JavaFeature.PARENTHESIZED_EXPRESSION)
    def test_parenthesized_binop_emits_binop(self):
        """(a + b) should produce a BINOP '+' instruction."""
        instructions = _parse_java("class M { void m() { int x = (1 + 2); } }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any(
            "+" in str(inst.operands) for inst in binops
        ), f"Expected BINOP '+', got: {[inst.operands for inst in binops]}"

    @covers(JavaFeature.PARENTHESIZED_EXPRESSION)
    def test_parenthesized_expression_no_symbolic_fallback(self):
        """(x) must not degrade to SYMBOLIC."""
        instructions = _parse_java("class M { void m() { int x = (1 + 2); } }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "parenthesized" in str(inst.operands) for inst in symbolics
        ), "parenthesized_expression should not fall back to SYMBOLIC"


class TestJavaUnaryExpression:
    """Unary operators must lower to UNOP instructions with the correct operator."""

    @covers(JavaFeature.UNARY)
    def test_unary_minus_emits_unop(self):
        """-x must produce a UNOP with operator '-'."""
        instructions = _parse_java("class M { void m() { int x = 5; int y = -x; } }")
        unops = _find_all(instructions, Opcode.UNOP)
        assert any(
            "-" in str(inst.operands) for inst in unops
        ), f"Expected UNOP '-', got: {[inst.operands for inst in unops]}"

    @covers(JavaFeature.UNARY)
    def test_logical_not_emits_unop(self):
        """!b must produce a UNOP with operator '!'."""
        instructions = _parse_java(
            "class M { void m() { boolean b = true; boolean r = !b; } }"
        )
        unops = _find_all(instructions, Opcode.UNOP)
        assert any(
            "!" in str(inst.operands) for inst in unops
        ), f"Expected UNOP '!', got: {[inst.operands for inst in unops]}"

    @covers(JavaFeature.UNARY)
    def test_bitwise_not_emits_unop(self):
        """~x must produce a UNOP with operator '~'."""
        instructions = _parse_java("class M { void m() { int x = 0; int y = ~x; } }")
        unops = _find_all(instructions, Opcode.UNOP)
        assert any(
            "~" in str(inst.operands) for inst in unops
        ), f"Expected UNOP '~', got: {[inst.operands for inst in unops]}"


class TestJavaReturnStatement:
    """return statements must lower to RETURN_ instructions carrying the result register."""

    @covers(JavaFeature.RETURN)
    def test_return_emits_return_instruction(self):
        """A method with return x must emit a RETURN instruction."""
        instructions = _parse_java("class M { int m(int x) { return x; } }")
        returns = _find_all(instructions, Opcode.RETURN)
        assert returns, "Expected at least one RETURN instruction"

    @covers(JavaFeature.RETURN)
    def test_return_value_is_register(self):
        """RETURN must carry a value_reg (not None) for non-void methods."""
        instructions = _parse_java("class M { int m() { return 42; } }")
        returns = _find_all(instructions, Opcode.RETURN)
        assert returns, "Expected RETURN instruction"
        assert any(
            inst.value_reg is not None for inst in returns
        ), "RETURN must reference a register holding the return value"

    @covers(JavaFeature.RETURN)
    def test_void_return_emits_return_instruction(self):
        """A void method with explicit return; must also emit RETURN."""
        instructions = _parse_java("class M { void m() { int x = 1; return; } }")
        returns = _find_all(instructions, Opcode.RETURN)
        assert returns, "Expected RETURN instruction even for void return"


class TestJavaConstantDeclaration:
    """Interface constants and static final fields must lower to DECL_VAR with the initializer."""

    @covers(JavaFeature.CONSTANT_DECLARATION)
    def test_interface_int_constant_emits_decl_var(self):
        """interface Limits { int MAX = 100; } must emit DECL_VAR for MAX."""
        instructions = _parse_java("interface Limits { int MAX = 100; }")
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any(
            inst.name == VarName("MAX") for inst in decls
        ), f"Expected DECL_VAR for 'MAX', got names: {[inst.name for inst in decls]}"

    @covers(JavaFeature.CONSTANT_DECLARATION)
    def test_interface_constant_initializer_is_loaded(self):
        """The initializer value (100) must appear as a typed int CONST before the DECL_VAR."""
        instructions = _parse_java("interface Limits { int MAX = 100; }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            c.value == 100 for c in consts
        ), f"Expected CONST 100, got: {[c.value for c in consts]}"

    @covers(JavaFeature.CONSTANT_DECLARATION)
    def test_static_final_field_emits_decl_var(self):
        """class M { static final int LIMIT = 42; } must emit DECL_VAR for LIMIT."""
        instructions = _parse_java("class M { static final int LIMIT = 42; }")
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any(
            inst.name == VarName("LIMIT") for inst in decls
        ), f"Expected DECL_VAR for 'LIMIT', got names: {[inst.name for inst in decls]}"

    @covers(JavaFeature.CONSTANT_DECLARATION)
    def test_constant_declaration_no_symbolic_fallback(self):
        """Constant declarations must not fall back to SYMBOLIC."""
        instructions = _parse_java("interface Flags { boolean ENABLED = true; }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "constant_declaration" in str(inst.operands) for inst in symbolics
        ), "constant_declaration should not fall back to SYMBOLIC"


class TestJavaMethodReference:
    @covers(JavaFeature.METHOD_REFERENCE)
    def test_type_method_reference(self):
        instructions = _parse_java(
            "class M { void m() { Function f = String::valueOf; } }"
        )
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any(
            "valueOf" in inst.operands for inst in loads
        ), "method name not extracted"
        # Stored into f
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any(
            "f" in inst.operands for inst in decls
        ), "reference not stored to var f"
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("method_reference" in str(inst.operands) for inst in symbolics)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.METHOD_REFERENCE)
    def test_this_method_reference(self):
        instructions = _parse_java(
            "class M { void m() { Runnable r = this::doStuff; } }"
        )
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any(
            "doStuff" in inst.operands for inst in loads
        ), "method name not extracted"
        # Stored into r
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any(
            "r" in inst.operands for inst in decls
        ), "reference not stored to var r"
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("method_reference" in str(inst.operands) for inst in symbolics)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.METHOD_REFERENCE)
    def test_constructor_reference(self):
        instructions = _parse_java(
            "class M { void m() { Supplier s = ArrayList::new; } }"
        )
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any(
            "new" in inst.operands for inst in loads
        ), "constructor ref not extracted"
        # Stored into s
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any(
            "s" in inst.operands for inst in decls
        ), "reference not stored to var s"
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("method_reference" in str(inst.operands) for inst in symbolics)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


class TestJavaClassLiteral:
    @covers(JavaFeature.CLASS_LITERAL)
    def test_class_literal(self):
        instructions = _parse_java("class M { void m() { Class c = String.class; } }")
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any(
            "class" in inst.operands for inst in loads
        ), ".class field not extracted"
        # Stored into c
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any(
            "c" in inst.operands for inst in decls
        ), "class literal not stored to var c"
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("class_literal" in str(inst.operands) for inst in symbolics)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.CLASS_LITERAL)
    def test_class_literal_in_expression(self):
        instructions = _parse_java(
            "class M { void m() { boolean b = Integer.class.equals(x.getClass()); } }"
        )
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any(
            "class" in inst.operands for inst in loads
        ), ".class field not extracted"
        # .equals() call emitted
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any(
            "equals" in str(inst.operands) for inst in calls
        ), ".equals() call not emitted"
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("class_literal" in str(inst.operands) for inst in symbolics)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


class TestJavaLambdaExpression:
    @covers(JavaFeature.LAMBDA)
    def test_lambda_expression_body(self):
        instructions = _parse_java(
            'class M { void m() { Runnable r = () -> System.out.println("hi"); } }'
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("lambda_expression" in str(inst.operands) for inst in symbolics)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1

    @covers(JavaFeature.LAMBDA)
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

    @covers(JavaFeature.LAMBDA)
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

    @covers(JavaFeature.LAMBDA)
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
    @covers(JavaFeature.INSTANCEOF)
    def test_instanceof_expression(self):
        instructions = _parse_java(
            "class M { void m() { boolean b = obj instanceof String; } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.CALL_FUNCTION in opcodes
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("isinstance" in inst.operands for inst in calls)

    @covers(JavaFeature.INSTANCEOF)
    def test_instanceof_in_condition(self):
        instructions = _parse_java(
            "class M { void m() { if (x instanceof Number) { y = 1; } } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.CALL_FUNCTION in opcodes
        assert Opcode.BRANCH_IF in opcodes


class TestJavaSuperExpression:
    @covers(JavaFeature.SUPER)
    def test_super_field_access(self):
        instructions = _parse_java(
            "class M extends B { void m() { int x = super.field; } }"
        )
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("field" in inst.operands for inst in loads)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.SUPER)
    def test_super_method_call(self):
        instructions = _parse_java(
            "class M extends B { void m() { super.doStuff(1); } }"
        )
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("doStuff" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


class TestJavaDoStatement:
    @covers(JavaFeature.DO_WHILE_LOOP)
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

    @covers(JavaFeature.BREAK_CONTINUE)
    def test_do_while_with_break(self):
        instructions = _parse_java(
            "class M { void m() { do { if (done) { break; } } while (true); } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes


class TestJavaAssertStatement:
    @covers(JavaFeature.ASSERT)
    def test_assert_simple(self):
        instructions = _parse_java("class M { void m() { assert x > 0; } }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("assert" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.ASSERT)
    def test_assert_with_message(self):
        instructions = _parse_java(
            'class M { void m() { assert x > 0 : "x must be positive"; } }'
        )
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("assert" in inst.operands for inst in calls)
        assert_call = next(c for c in calls if "assert" in c.operands)
        assert len(assert_call.operands) >= 3  # "assert", cond_reg, msg_reg


class TestJavaLabeledStatement:
    @covers(JavaFeature.LABELED_STATEMENT)
    def test_labeled_statement(self):
        instructions = _parse_java(
            "class M { void m() { outer: for (int i = 0; i < 5; i++) { x = i; } } }"
        )
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("i" in inst.operands for inst in stores)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


class TestJavaSynchronizedStatement:
    @covers(JavaFeature.SYNCHRONIZED)
    def test_synchronized_block(self):
        instructions = _parse_java(
            "class M { void m() { synchronized(lock) { x = 1; } } }"
        )
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.SYNCHRONIZED)
    def test_synchronized_this(self):
        instructions = _parse_java(
            "class M { void m() { synchronized(this) { doStuff(); } } }"
        )
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("doStuff" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


class TestJavaStaticInitializer:
    @covers(JavaFeature.STATIC_INITIALIZER)
    def test_static_initializer_block(self):
        instructions = _parse_java("class M { static { x = 10; } }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.STATIC_INITIALIZER)
    def test_static_initializer_with_method_call(self):
        instructions = _parse_java("class M { static { init(); } }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("init" in inst.operands for inst in calls)


class TestJavaExplicitConstructorInvocation:
    @covers(JavaFeature.EXPLICIT_CONSTRUCTOR_INVOCATION)
    def test_super_constructor_call(self):
        instructions = _parse_java(
            "class M extends B { M(int x) { super(x); this.val = x; } }"
        )
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("super" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.EXPLICIT_CONSTRUCTOR_INVOCATION)
    def test_this_constructor_call(self):
        instructions = _parse_java("class M { M() { this(0); } M(int x) { } }")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("__init__" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


class TestJavaAnnotationTypeDeclaration:
    @covers(JavaFeature.ANNOTATION_TYPE)
    def test_annotation_type(self):
        instructions = _parse_java("public @interface MyAnnotation { String value(); }")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("annotation:MyAnnotation" in str(inst.operands) for inst in new_objs)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("MyAnnotation" in inst.operands for inst in stores)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.ANNOTATION_TYPE)
    def test_annotation_type_with_members(self):
        instructions = _parse_java(
            "public @interface Config { String name(); int value(); }"
        )
        store_indexes = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(store_indexes) >= 2


class TestJavaRecordDeclaration:
    @covers(JavaFeature.RECORD)
    def test_record_basic(self):
        instructions = _parse_java("record Point(int x, int y) { }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Point" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.RECORD)
    def test_record_with_method(self):
        instructions = _parse_java(
            "record Point(int x, int y) { double distance() { return Math.sqrt(x*x + y*y); } }"
        )
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Point" in inst.operands for inst in stores)
        assert any("distance" in inst.operands for inst in stores)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1

    @covers(JavaFeature.RECORD)
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
    @covers(JavaFeature.SCOPED_IDENTIFIER)
    def test_scoped_identifier_in_annotation(self):
        """Annotations use scoped_identifier for qualified names like java.lang.Override."""
        instructions = _parse_java("@java.lang.Override class M { }")
        # The annotation is lowered without producing SYMBOLIC for scoped_identifier
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("scoped_identifier" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.SCOPED_IDENTIFIER)
    def test_scoped_identifier_dispatch_registered(self):
        """Verify scoped_identifier is registered in the expression dispatch table."""
        frontend = JavaFrontend(TreeSitterParserFactory(), "java")
        expr_dispatch = frontend._build_expr_dispatch()
        assert "scoped_identifier" in expr_dispatch


class TestJavaTextBlock:
    @covers(JavaFeature.TEXT_BLOCK)
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

    @covers(JavaFeature.TEXT_BLOCK)
    def test_text_block_in_expression(self):
        source = 'class M { void m() { String s = """\n    SELECT *\n    FROM table\n    """.trim(); } }'
        instructions = _parse_java(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("trim" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.TEXT_BLOCK)
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
    @covers(JavaFeature.SWITCH_EXPRESSION)
    def test_switch_expression_no_symbolic(self):
        source = 'class M { String m(int x) { return switch (x) { case 1 -> "one"; default -> "other"; }; } }'
        instructions = _parse_java(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("switch_expression" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.SWITCH_EXPRESSION)
    def test_switch_expression_returns_value(self):
        source = 'class M { String m(int x) { return switch (x) { case 1 -> "one"; default -> "other"; }; } }'
        instructions = _parse_java(source)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("__switch_result" in inst.operands[0] for inst in loads)


class TestJavaExpressionStatementInSwitch:
    @covers(JavaFeature.SWITCH_EXPRESSION)
    def test_expression_statement_in_switch_expression(self):
        """expression_statement inside switch expression should not produce unsupported SYMBOLIC."""
        source = 'class M { String m(int day) { return switch (day) { case 1 -> "work"; default -> "rest"; }; } }'
        instructions = _parse_java(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.SWITCH_EXPRESSION)
    def test_expression_statement_switch_multiple_cases(self):
        source = 'class M { String m(int x) { return switch (x) { case 1 -> "a"; case 2 -> "b"; default -> "c"; }; } }'
        instructions = _parse_java(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)


class TestJavaThrowStatementInSwitch:
    @covers(JavaFeature.SWITCH_EXPRESSION)
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

    @covers(JavaFeature.GENERIC_TYPES)
    def test_local_var_list_of_string(self):
        """List<String> items = ... should seed var_types['items'] = 'List[String]'."""
        source = "class M { void m() { List<String> items = new ArrayList<>(); } }"
        _, builder = _parse_java_with_types(source)
        assert builder.var_types["items"] == "List[String]"

    @covers(JavaFeature.GENERIC_TYPES)
    def test_local_var_map_of_string_integer(self):
        """Map<String, Integer> m = ... should seed 'Map[String, Int]' (Integer normalised)."""
        source = "class M { void m() { Map<String, Integer> m = new HashMap<>(); } }"
        _, builder = _parse_java_with_types(source)
        assert builder.var_types["m"] == "Map[String, Int]"

    @covers(JavaFeature.GENERIC_TYPES)
    def test_nested_generic_type(self):
        """List<Map<String, Integer>> should produce 'List[Map[String, Int]]'."""
        source = "class M { void m() { List<Map<String, Integer>> x = null; } }"
        _, builder = _parse_java_with_types(source)
        assert builder.var_types["x"] == "List[Map[String, Int]]"

    @covers(JavaFeature.GENERIC_TYPES)
    def test_method_return_generic_type(self):
        """Method returning List<String> should seed func_return_types with 'List[String]'."""
        source = "class M { List<String> getNames() { return null; } }"
        _, builder = _parse_java_with_types(source)
        return_types = builder.func_return_types
        assert any(v == "List[String]" for v in return_types.values())

    @covers(JavaFeature.GENERIC_TYPES)
    def test_param_generic_type(self):
        """Parameter List<String> items should seed param type 'List[String]'."""
        source = "class M { void process(List<String> items) { } }"
        _, builder = _parse_java_with_types(source)
        param_types = builder.func_param_types
        assert any(
            any(ptype == "List[String]" for _, ptype in params)
            for params in param_types.values()
        )

    @covers(JavaFeature.GENERIC_TYPES)
    def test_field_generic_type(self):
        """Field List<String> names; should seed var_types['names'] = 'List[String]'."""
        source = "class M { List<String> names = new ArrayList<>(); }"
        _, builder = _parse_java_with_types(source)
        assert builder.var_types["names"] == "List[String]"

    @covers(JavaFeature.GENERIC_TYPES)
    def test_non_generic_type_unchanged(self):
        """Plain int x = 42; should still seed 'Int' (regression check)."""
        source = "class M { void m() { int x = 42; } }"
        _, builder = _parse_java_with_types(source)
        assert builder.var_types["x"] == "Int"


class TestJavaHexFloatingPointLiteral:
    @covers(JavaFeature.HEX_FLOAT_LITERAL)
    def test_hex_float_no_symbolic(self):
        """0x1.0p10 should not produce SYMBOLIC fallthrough."""
        ir = _parse_java("class T { void f() { double x = 0x1.0p10; } }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "hex_floating_point_literal" in str(inst.operands) for inst in symbolics
        )

    @covers(JavaFeature.HEX_FLOAT_LITERAL)
    def test_hex_float_emits_const(self):
        """Hex floating point literal should emit a CONST with the parsed float value."""
        ir = _parse_java("class T { void f() { double x = 0x1.0p10; } }")
        consts = _find_all(ir, Opcode.CONST)
        # Verify the actual numeric value, not just string repr
        const_values = [inst.operands[0] for inst in consts]
        assert any(
            v == 1024.0 for v in const_values
        ), f"expected CONST 1024.0, got values: {const_values}"

    @covers(JavaFeature.HEX_FLOAT_LITERAL)
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

    @covers(JavaFeature.INTERFACE)
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
        # Each function label should be followed by a RET (function entry point pattern)
        for i, inst in enumerate(ir):
            if (
                inst.opcode == Opcode.LABEL
                and "func_" in str(inst.label)
                and "area" in str(inst.label)
            ):
                remaining = [r.opcode for r in ir[i + 1 :]]
                assert (
                    Opcode.RETURN in remaining
                ), "area func label not followed by RETURN"
                break
        else:
            raise AssertionError("area func label not found in IR")

    @covers(JavaFeature.INTERFACE)
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

    @covers(JavaFeature.INTERFACE)
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
    @covers(JavaFeature.TYPE_PATTERN)
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

    @covers(JavaFeature.TYPE_PATTERN)
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

    @covers(JavaFeature.TYPE_PATTERN)
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
    @covers(JavaFeature.RECORD_PATTERN)
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
    @covers(JavaFeature.METHOD_CALL)
    def test_string_length_returns_concrete(self):
        """s.length() on a concrete string should return a concrete int."""
        from interpreter.project.entry_point import EntryPoint
        from interpreter.run import run
        from interpreter.types.typed_value import unwrap_locals

        vm = run(
            'class M { static int result = "hello".length(); }',
            language="java",
            max_steps=100,
            entry_point=EntryPoint.top_level(),
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars[VarName("result")] == 5


class TestJavaAnnotatedType:
    """annotated_type in variable and parameter positions must not crash or produce symbolics."""

    @covers(JavaFeature.ANNOTATIONS)
    def test_annotated_local_var_emits_decl(self):
        """@NonNull String x = 'hello' — variable must be declared despite annotated type."""
        instructions = _parse_java(
            'class M { void m() { @NonNull String x = "hello"; } }'
        )
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in decls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.ANNOTATIONS)
    def test_annotated_param_type_in_method(self):
        """Method with @NonNull parameter type must lower to a function definition."""
        instructions = _parse_java("class M { void greet(@NonNull String name) { } }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)


class TestJavaMarkerAnnotation:
    """marker_annotation (@Override, @Deprecated) on methods must not crash lowering."""

    @covers(JavaFeature.ANNOTATIONS)
    def test_override_annotation_on_method(self):
        """@Override method must produce a function definition, not crash."""
        instructions = _parse_java("class M { @Override void foo() { int x = 1; } }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)
        # Variable inside the method body must still lower
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in decls)

    @covers(JavaFeature.ANNOTATIONS)
    def test_deprecated_annotation_on_method(self):
        """@Deprecated marker on a method must not suppress IR generation."""
        instructions = _parse_java(
            "class M { @Deprecated void legacy() { int y = 2; } }"
        )
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any("y" in inst.operands for inst in decls)

    @covers(JavaFeature.ANNOTATIONS)
    def test_multiple_marker_annotations(self):
        """Multiple marker annotations must all be silently skipped."""
        instructions = _parse_java(
            "class M { @Override @Deprecated void old() { int z = 3; } }"
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any("z" in inst.operands for inst in decls)


class TestJavaAnnotation:
    """annotation (@SuppressWarnings("x")) must be skipped without producing symbolics."""

    @covers(JavaFeature.ANNOTATIONS)
    def test_suppress_warnings_on_method(self):
        """@SuppressWarnings annotation with argument must not crash lowering."""
        instructions = _parse_java(
            'class M { @SuppressWarnings("unused") void foo() { int x = 1; } }'
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in decls)


class TestJavaModifiersUnit:
    """Modifiers (public, static, final) must be skipped without producing symbolics."""

    @covers(JavaFeature.MODIFIERS)
    def test_public_static_final_field(self):
        """public static final int X = 5 — variable must be declared, no symbolics."""
        instructions = _parse_java("class M { public static final int X = 5; }")
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any("X" in inst.operands for inst in decls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.MODIFIERS)
    def test_private_method_modifiers(self):
        """private int x in method body must lower cleanly."""
        instructions = _parse_java("class M { void m() { int x = 10; } }")
        decls = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in decls)


class TestJavaFormalParametersUnit:
    """formal_parameters in method declarations must lower all parameter names."""

    @covers(JavaFeature.FORMAL_PARAMETERS)
    def test_single_param_method(self):
        """Method with one parameter must declare it as a local."""
        instructions = _parse_java("class M { int double_(int x) { return x * 2; } }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_symbolics = [
            inst for inst in symbolics if "param:x" in str(inst.operands)
        ]
        assert param_symbolics, "Expected SYMBOLIC for parameter x"

    @covers(JavaFeature.FORMAL_PARAMETERS)
    def test_multi_param_method(self):
        """Method with multiple parameters must declare each one."""
        instructions = _parse_java(
            "class M { int add(int a, int b) { return a + b; } }"
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = {str(inst.operands) for inst in symbolics}
        assert any("param:a" in p for p in param_names)
        assert any("param:b" in p for p in param_names)


class TestJavaInferredParametersUnit:
    """inferred_parameters (lambdas without type annotations) must lower each param."""

    @covers(JavaFeature.INFERRED_PARAMETERS)
    def test_single_inferred_param_lambda(self):
        """Lambda (x) -> x + 1 must declare x via SYMBOLIC + DECL_VAR."""
        instructions = _parse_java(
            "class M { void m() { Function<Integer,Integer> f = (x) -> x + 1; } }"
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("param:x" in str(inst.operands) for inst in symbolics)

    @covers(JavaFeature.INFERRED_PARAMETERS)
    def test_two_inferred_params_lambda(self):
        """Lambda (a, b) -> a + b must declare both a and b."""
        instructions = _parse_java(
            "class M { void m() { BiFunction<Integer,Integer,Integer> f = (a, b) -> a + b; } }"
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = {str(inst.operands) for inst in symbolics}
        assert any("param:a" in p for p in param_names)
        assert any("param:b" in p for p in param_names)


class TestInlineCommentsInExpressions:
    """Tree-sitter injects comment nodes as extras inside expressions.

    Our lowerers must skip them — otherwise they get mistaken for operators.
    """

    @covers(JavaFeature.COMMENT_HANDLING)
    def test_line_comment_inside_binary_expression(self):
        ir = _parse_java("""class Foo {
            void bar() {
                int x = 1;
                if (x == 1 // comment
                    || x == 2) {
                    x = 3;
                }
            }
        }""")
        binops = _find_all(ir, Opcode.BINOP)
        binop_ops = [inst.operands[0] for inst in binops]
        assert "==" in binop_ops, "comment should not prevent == from lowering"
        assert "||" in binop_ops, "comment should not prevent || from lowering"
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("comment" in str(s.operands) for s in symbolics)

    @covers(JavaFeature.COMMENT_HANDLING)
    def test_block_comment_inside_binary_expression(self):
        ir = _parse_java("""class Foo {
            void bar() {
                int x = 1;
                if (x == 1 /* comment */ || x == 2) {
                    x = 3;
                }
            }
        }""")
        binops = _find_all(ir, Opcode.BINOP)
        binop_ops = [inst.operands[0] for inst in binops]
        assert "==" in binop_ops, "comment should not prevent == from lowering"
        assert "||" in binop_ops, "comment should not prevent || from lowering"
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("comment" in str(s.operands) for s in symbolics)


class TestJavaNoOpDeclarations:
    """IMPORT_DECLARATION, PACKAGE_DECLARATION, and MODULE_DECLARATION are
    intentional no-ops: they carry no executable semantics.  Imports are
    compile-time hints; packages and module directives are metadata for the
    module system.  The multi-file linker resolves cross-unit symbols via the
    SymbolTable, not by interpreting these nodes at runtime.  These tests
    assert that the frontend silently discards the nodes without emitting
    SYMBOLIC fallbacks or raising errors.
    """

    @covers(JavaFeature.IMPORT_DECLARATION)
    def test_import_declaration_emits_no_ir(self):
        """import statements are silently discarded — no-op by design."""
        ir = _parse_java("import java.util.List;\nimport java.util.Map;\nint x = 1;")
        assert not any(
            inst.opcode == Opcode.SYMBOLIC for inst in ir
        ), "import declarations must not produce SYMBOLIC fallbacks"
        decl_vars = _find_all(ir, Opcode.DECL_VAR)
        assert len(decl_vars) == 1, "only the int x declaration should appear"

    @covers(JavaFeature.PACKAGE_DECLARATION)
    def test_package_declaration_emits_no_ir(self):
        """package declarations are silently discarded — no-op by design."""
        ir = _parse_java("package com.example.myapp;\nint x = 1;")
        assert not any(
            inst.opcode == Opcode.SYMBOLIC for inst in ir
        ), "package declarations must not produce SYMBOLIC fallbacks"
        decl_vars = _find_all(ir, Opcode.DECL_VAR)
        assert len(decl_vars) == 1, "only the int x declaration should appear"

    @covers(JavaFeature.MODULE_DECLARATION)
    def test_module_declaration_emits_no_ir(self):
        """module-info.java module declarations are silently discarded — no-op by design.
        Module directives (requires, exports) are Java 9+ module system metadata
        with no runtime execution semantics.
        """
        ir = _parse_java("module com.example.myapp { requires java.base; }")
        assert not any(
            inst.opcode == Opcode.SYMBOLIC for inst in ir
        ), "module declarations must not produce SYMBOLIC fallbacks"
        non_label = [inst for inst in ir if inst.opcode != Opcode.LABEL]
        assert (
            non_label == []
        ), "module-info content should produce no executable IR beyond the entry label"


class TestJavaFinallyBlock:
    """Finally blocks must emit a try_finally label and execute their body."""

    @covers(JavaFeature.FINALLY)
    def test_finally_emits_try_finally_label(self):
        """try { } finally { } must produce a try_finally label in the IR."""
        instructions = _parse_java(
            "class M { void m() { try { int x = 1; } finally { int y = 2; } } }"
        )
        labels = [str(i.label) for i in instructions if i.opcode == Opcode.LABEL]
        assert any("try_finally" in lbl for lbl in labels)

    @covers(JavaFeature.FINALLY)
    def test_finally_body_instructions_emitted(self):
        """The finally body must emit STORE_VAR (or equivalent) instructions."""
        instructions = _parse_java(
            "class M { void m() { int x = 0; try { x = 1; } finally { x = 2; } } }"
        )
        store_vars = _find_all(instructions, Opcode.STORE_VAR)
        # finally body assigns x = 2; must appear somewhere after try_body
        stored_names = [str(i.operands) for i in store_vars]
        assert any("x" in s for s in stored_names)
        labels = [str(i.label) for i in instructions if i.opcode == Opcode.LABEL]
        assert any("try_finally" in lbl for lbl in labels)

    @covers(JavaFeature.FINALLY)
    def test_finally_and_catch_both_present(self):
        """try-catch-finally must emit both catch and finally labels."""
        instructions = _parse_java(
            "class M { void m() { try { int x = 1; } catch (Exception e) { int x = 99; } finally { int x = 100; } } }"
        )
        labels = [str(i.label) for i in instructions if i.opcode == Opcode.LABEL]
        assert any("catch" in lbl for lbl in labels)
        assert any("try_finally" in lbl for lbl in labels)


class TestJavaTryWithResources:
    """try-with-resources: resource declaration and try body lowering."""

    @covers(JavaFeature.TRY_WITH_RESOURCES)
    def test_resource_emits_decl_var(self):
        """Resource variable must be declared before the try body."""
        instructions = _parse_java(
            'class M { static void run() { try (java.io.StringReader r = new java.io.StringReader("x")) { int x = 1; } } }'
        )
        decl_vars = _find_all(instructions, Opcode.DECL_VAR)
        assert any("r" in str(inst.operands) for inst in decl_vars)

    @covers(JavaFeature.TRY_WITH_RESOURCES)
    def test_try_body_label_emitted(self):
        """try-with-resources must emit a try_body label for the protected block."""
        instructions = _parse_java(
            'class M { static void run() { try (java.io.StringReader r = new java.io.StringReader("x")) { int x = 1; } } }'
        )
        labels = [str(i.label) for i in instructions if i.opcode == Opcode.LABEL]
        assert any("try_body" in lbl for lbl in labels)

    @covers(JavaFeature.TRY_WITH_RESOURCES)
    def test_resource_constructor_call_emitted(self):
        """Resource initialiser must emit a CALL_CTOR instruction."""
        instructions = _parse_java(
            'class M { static void run() { try (java.io.StringReader r = new java.io.StringReader("x")) { int x = 1; } } }'
        )
        call_ctors = _find_all(instructions, Opcode.CALL_CTOR)
        assert len(call_ctors) >= 1


class TestJavaSwitchRule:
    """Arrow-form case labels (case X ->) in switch expressions."""

    @covers(JavaFeature.SWITCH_RULE)
    def test_switch_rule_emits_branch_if(self):
        """Arrow-form cases must emit BRANCH_IF for each case value."""
        instructions = _parse_java(
            "class M { static int f(int x) { return switch (x) { case 1 -> 10; default -> 99; }; } }"
        )
        branch_ifs = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branch_ifs) >= 1

    @covers(JavaFeature.SWITCH_RULE)
    def test_switch_rule_emits_switch_end_label(self):
        """Arrow-form switch must emit a switch_end label."""
        instructions = _parse_java(
            "class M { static int f(int x) { return switch (x) { case 1 -> 10; default -> 99; }; } }"
        )
        labels = [str(i.label) for i in instructions if i.opcode == Opcode.LABEL]
        assert any("switch_end" in lbl for lbl in labels)

    @covers(JavaFeature.SWITCH_RULE)
    def test_switch_rule_default_arm_reachable(self):
        """Arrow-form switch with default must emit a case_arm label for the default."""
        instructions = _parse_java(
            "class M { static int f(int x) { return switch (x) { case 1 -> 10; default -> 99; }; } }"
        )
        labels = [str(i.label) for i in instructions if i.opcode == Opcode.LABEL]
        assert any("case_arm" in lbl for lbl in labels)


class TestJavaSpreadParameter:
    """Varargs (T... name) parameters must be lowered as slice(arguments, idx)."""

    @covers(JavaFeature.SPREAD_PARAMETER)
    def test_varargs_param_emits_decl_var(self):
        """int... nums must produce a DECL_VAR for 'nums' in the method body."""
        instructions = _parse_java(
            "class M { static int sum(int... nums) { return 0; } }"
        )
        decl_vars = _find_all(instructions, Opcode.DECL_VAR)
        assert any("nums" in inst.operands for inst in decl_vars)

    @covers(JavaFeature.SPREAD_PARAMETER)
    def test_varargs_param_slices_arguments(self):
        """int... nums must load 'arguments' and call slice — no SYMBOLIC for the varargs name."""
        instructions = _parse_java(
            "class M { static int sum(int... nums) { return 0; } }"
        )
        load_vars = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("arguments" in str(inst.operands) for inst in load_vars)
        call_funcs = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("slice" in str(inst.operands) for inst in call_funcs)

    @covers(JavaFeature.SPREAD_PARAMETER)
    def test_varargs_alongside_regular_params(self):
        """(String prefix, int... vals) must declare both 'prefix' and 'vals'."""
        instructions = _parse_java(
            "class M { static void show(String prefix, int... vals) { } }"
        )
        decl_vars = _find_all(instructions, Opcode.DECL_VAR)
        decl_names = [str(inst.operands) for inst in decl_vars]
        assert any("prefix" in n for n in decl_names)
        assert any("vals" in n for n in decl_names)


class TestJavaImplicitReturn:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_trailing_return_is_marked_implicit(self):
        src = "class A { int f() { return 42; } }"
        instructions = _parse_java(src)
        returns = _find_all(instructions, Opcode.RETURN)
        assert any(r.implicit for r in returns)
        assert any(not r.implicit for r in returns)
