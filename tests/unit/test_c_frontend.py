"""Tests for CFrontend — tree-sitter C AST -> IR lowering."""

from __future__ import annotations

from interpreter.run import execute_cfg, VMConfig
from interpreter.registry import FunctionRegistry as Registry
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from interpreter.types.typed_value import unwrap
from interpreter.api import build_cfg_from_source
from interpreter.frontends.c import CFrontend
from interpreter.frontends.c.features import CFeature
from interpreter.instructions import BranchIf, InstructionBase, CallFunction, Binop
from interpreter.ir import Opcode
from interpreter.parser import TreeSitterParserFactory
from interpreter.type_name import TypeName
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
from tests.covers import covers


def _parse_and_lower(source: str) -> list[InstructionBase]:
    frontend = CFrontend(TreeSitterParserFactory(), "c")
    return frontend.lower(source.encode("utf-8"))


def _parse_and_lower_with_types(
    source: str,
) -> tuple[list[InstructionBase], TypeEnvironmentBuilder]:
    frontend = CFrontend(TreeSitterParserFactory(), "c")
    instructions = frontend.lower(source.encode("utf-8"))
    return instructions, frontend.type_env_builder


def _opcodes(instructions: list[InstructionBase]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(
    instructions: list[InstructionBase], opcode: Opcode
) -> list[InstructionBase]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestCFrontendDeclaration:
    @covers(CFeature.VARIABLE_DECLARATION)
    def test_declaration_with_init_produces_const_and_decl_var(self):
        """int x = 10 produces CONST and DECL_VAR with value operand."""
        ir = _parse_and_lower("int x = 10;")
        opcodes = _opcodes(ir)
        assert Opcode.CONST in opcodes, "Expected CONST for initializer value"
        assert Opcode.DECL_VAR in opcodes, "Expected DECL_VAR for declaration"
        # Verify x is declared with the const value
        decls = _find_all(ir, Opcode.DECL_VAR)
        x_decls = [d for d in decls if "x" in str(d.operands)]
        assert len(x_decls) >= 1, "Expected DECL_VAR for x"

    @covers(CFeature.VARIABLE_DECLARATION)
    def test_declaration_without_initializer(self):
        ir = _parse_and_lower("int x;")
        stores = _find_all(ir, Opcode.DECL_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 1


class TestCFrontendFunctionDefinition:
    @covers(CFeature.FUNCTION_DECLARATION)
    def test_function_def_produces_label_and_return(self):
        source = "int add(int a, int b) { return a + b; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.LABEL in opcodes
        assert Opcode.RETURN in opcodes

    @covers(CFeature.FUNCTION_DECLARATION)
    def test_function_params_lowered_as_symbolic(self):
        source = "int add(int a, int b) { return a + b; }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        param_symbolics = [
            s for s in symbolics if any("param:" in str(op) for op in s.operands)
        ]
        assert len(param_symbolics) >= 2

    @covers(CFeature.FUNCTION_DECLARATION)
    def test_function_name_stored(self):
        source = "int add(int a, int b) { return a + b; }"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        add_stores = [s for s in stores if "add" in s.operands]
        assert len(add_stores) >= 1


class TestCFrontendFunctionCall:
    @covers(CFeature.FUNCTION_CALL)
    def test_function_call_produces_call_function(self):
        source = "void f() { add(1, 2); }"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        add_calls = [c for c in calls if "add" in c.operands]
        assert len(add_calls) >= 1


class TestCFrontendIfElse:
    @covers(CFeature.IF_ELSE)
    def test_if_else_produces_branch_if(self):
        source = """
void f() {
    int x = 10;
    if (x > 5) {
        x = 1;
    } else {
        x = 2;
    }
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes

    @covers(CFeature.IF_ELSE)
    def test_if_else_produces_labels(self):
        """if-else produces LABEL opcodes for branch targets (then/else/merge)."""
        source = """
void f() {
    if (x > 5) {
        y = 1;
    } else {
        y = 2;
    }
}
"""
        ir = _parse_and_lower(source)
        labels = _find_all(ir, Opcode.LABEL)
        # Verify we have labels for then block, else block, and merge point
        assert (
            len(labels) >= 3
        ), f"Expected >= 3 LABEL opcodes for if-else structure (then/else/merge), got {len(labels)}"

    @covers(CFeature.IF_ELSE)
    def test_if_elseif_chain_all_branches_produce_ir(self):
        """All branches of if/else-if/else-if/else must produce IR."""
        source = """
void f() {
    if (x == 1) { y = 10; }
    else if (x == 2) { y = 20; }
    else if (x == 3) { y = 30; }
    else { y = 40; }
}
"""
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        const_values = [op for inst in consts for op in inst.operands]
        assert "10" in const_values, "if-branch value missing"
        assert "20" in const_values, "first else-if-branch value missing"
        assert "30" in const_values, "second else-if-branch value missing"
        assert "40" in const_values, "else-branch value missing"

        branch_ifs = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branch_ifs) == 3

        labels = _labels_in_order(ir)
        branch_targets = {
            target for inst in branch_ifs for target in inst.branch_targets
        }
        label_set = set(labels)
        assert branch_targets.issubset(
            label_set
        ), f"Unreachable targets: {branch_targets - label_set}"


class TestCFrontendWhileLoop:
    @covers(CFeature.WHILE_LOOP)
    def test_while_loop_produces_branch_if_and_branch(self):
        source = """
void f() {
    int x = 10;
    while (x > 0) {
        x = x - 1;
    }
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes


class TestCFrontendForLoop:
    @covers(CFeature.FOR_LOOP)
    def test_c_style_for_loop(self):
        source = """
void f() {
    for (int i = 0; i < 10; i++) {
        int x = i;
    }
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        labels = _find_all(ir, Opcode.LABEL)
        label_names = [str(lbl.label) for lbl in labels]
        for_labels = [lbl for lbl in label_names if lbl and "for_" in lbl]
        assert len(for_labels) >= 2


class TestCFrontendStructDefinition:
    @covers(CFeature.STRUCT)
    def test_struct_definition_produces_class_label(self):
        source = """
struct Point {
    int x;
    int y;
};
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        point_stores = [s for s in stores if "Point" in s.operands]
        assert len(point_stores) >= 1
        consts = _find_all(ir, Opcode.CONST)
        class_refs = [
            c for c in consts if any("class_" in str(op) for op in c.operands)
        ]
        assert len(class_refs) >= 1

    @covers(CFeature.STRUCT)
    def test_struct_fields_lowered_as_store_field(self):
        source = """
struct Point {
    int x;
    int y;
};
"""
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        field_names = [
            inst.operands[1] for inst in store_fields if len(inst.operands) > 1
        ]
        assert "x" in field_names
        assert "y" in field_names
        load_vars = _find_all(ir, Opcode.LOAD_VAR)
        assert any("this" in inst.operands for inst in load_vars)

    @covers(CFeature.STRUCT)
    def test_plain_struct_var_decl_emits_new_object(self):
        """struct Circle c; should emit NEW_OBJECT to create a heap-backed instance."""
        source = """
struct Circle { int radius; };
struct Circle c;
"""
        ir = _parse_and_lower(source)
        new_objects = _find_all(ir, Opcode.NEW_OBJECT)
        assert len(new_objects) >= 1
        assert any("Circle" in str(inst.operands) for inst in new_objects)

    @covers(CFeature.STRUCT)
    def test_struct_field_store_load_emits_correct_opcodes(self):
        """c.radius = 5; int result = c.radius; should emit STORE_FIELD then LOAD_FIELD."""
        source = """
struct Circle { int radius; };
struct Circle c;
c.radius = 5;
int result = c.radius;
"""
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        radius_stores = [s for s in store_fields if "radius" in s.operands]
        radius_loads = [load for load in load_fields if "radius" in load.operands]
        assert len(radius_stores) >= 1
        assert len(radius_loads) >= 1


class TestCFrontendAssignmentExpression:
    @covers(CFeature.ASSIGNMENT)
    def test_assignment_expression(self):
        source = "void f() { int x; x = 10; }"
        ir = _parse_and_lower(source)
        decls = _find_all(ir, Opcode.DECL_VAR)
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_decls = [s for s in decls if "x" in s.operands]
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_decls) >= 1
        assert len(x_stores) >= 1


class TestCFrontendFieldAccess:
    @covers(CFeature.FIELD_ACCESS)
    def test_dot_field_access_produces_load_field(self):
        source = "void f() { int z = obj.field; }"
        ir = _parse_and_lower(source)
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert len(load_fields) >= 1
        assert "field" in load_fields[0].operands

    @covers(CFeature.ARROW_OPERATOR)
    def test_arrow_field_access_produces_load_field(self):
        source = "void f() { int z = ptr->field; }"
        ir = _parse_and_lower(source)
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert len(load_fields) >= 1
        assert "field" in load_fields[0].operands


class TestCFrontendReturn:
    @covers(CFeature.RETURN)
    def test_return_with_value(self):
        source = "int f() { return 42; }"
        ir = _parse_and_lower(source)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1

    @covers(CFeature.RETURN)
    def test_return_without_value(self):
        source = "void f() { return; }"
        ir = _parse_and_lower(source)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1


class TestCFrontendUpdateExpression:
    @covers(CFeature.ARITHMETIC)
    def test_increment_expression(self):
        source = "void f() { int i = 0; i++; }"
        ir = _parse_and_lower(source)
        binops = _find_all(ir, Opcode.BINOP)
        plus_ops = [b for b in binops if "+" in b.operands]
        assert len(plus_ops) >= 1

    @covers(CFeature.ARITHMETIC)
    def test_decrement_expression(self):
        source = "void f() { int i = 10; i--; }"
        ir = _parse_and_lower(source)
        binops = _find_all(ir, Opcode.BINOP)
        minus_ops = [b for b in binops if "-" in b.operands]
        assert len(minus_ops) >= 1


class TestCFrontendCastExpression:
    @covers(CFeature.CAST)
    def test_cast_expression_lowers_value(self):
        source = "void f() { int y = (int)x; }"
        ir = _parse_and_lower(source)
        # The cast should transparently lower the inner value
        loads = _find_all(ir, Opcode.LOAD_VAR)
        assert any("x" in inst.operands for inst in loads)
        stores = _find_all(ir, Opcode.DECL_VAR)
        y_stores = [s for s in stores if "y" in s.operands]
        assert len(y_stores) >= 1


class TestCFrontendPreprocessor:
    @covers(CFeature.PREPROCESSOR)
    def test_preprocessor_is_skipped(self):
        source = """
#include <stdio.h>
#define MAX 100
int x = 10;
"""
        ir = _parse_and_lower(source)
        # Preprocessor directives should be noise and not produce meaningful IR
        stores = _find_all(ir, Opcode.DECL_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 1
        # No SYMBOLIC for the preprocessor directives themselves
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        preproc_symbolics = [
            s for s in symbolics if any("preproc" in str(op) for op in s.operands)
        ]
        assert len(preproc_symbolics) == 0


class TestCFrontendPointerOps:
    @covers(CFeature.POINTER_DEREFERENCE)
    def test_pointer_dereference(self):
        source = "void f() { int z = *ptr; }"
        ir = _parse_and_lower(source)
        loads = _find_all(ir, Opcode.LOAD_INDIRECT)
        assert len(loads) >= 1

    @covers(CFeature.ADDRESS_OF)
    def test_address_of(self):
        source = "void f() { int *p = &x; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.ADDRESS_OF in opcodes
        addr_ofs = _find_all(ir, Opcode.ADDRESS_OF)
        assert any("x" in inst.operands for inst in addr_ofs)

    @covers(CFeature.POINTER_STORE)
    def test_pointer_store(self):
        source = "void f() { *ptr = 42; }"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_INDIRECT)
        assert len(stores) >= 1

    @covers(CFeature.SIZEOF)
    def test_sizeof_type(self):
        source = "void f() { int s = sizeof(int); }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.CALL_FUNCTION in opcodes
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("sizeof" in inst.operands for inst in calls)

    @covers(CFeature.COMPOUND_LITERAL)
    def test_compound_literal(self):
        source = "void f() { struct Point p = (struct Point){1, 2}; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes


class TestCFrontendFallback:
    @covers(CFeature.ENTRY_LABEL)
    def test_entry_label_always_present(self):
        ir = _parse_and_lower("")
        assert ir[0].opcode == Opcode.LABEL
        assert ir[0].label == "entry"


def _labels_in_order(instructions: list[InstructionBase]) -> list[str]:
    return [str(inst.label) for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialC:
    @covers(CFeature.ARRAY_ACCESS)
    def test_nested_for_with_array_access(self):
        source = """\
void f() {
    int sum = 0;
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 3; j++) {
            sum = sum + grid[i][j];
        }
    }
}
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("sum" in s.operands for s in stores)
        assert any("i" in s.operands for s in stores)
        assert any("j" in s.operands for s in stores)
        # grid[i][j] should produce two chained LOAD_INDEX (one per subscript)
        load_indices = _find_all(ir, Opcode.LOAD_INDEX)
        assert (
            len(load_indices) == 2
        ), "grid[i][j] should produce 2 LOAD_INDEX instructions"
        # Second LOAD_INDEX should chain off the first (nested subscript)
        assert load_indices[1].operands[0] == str(
            load_indices[0].result_reg
        ), "grid[i][j]: second subscript should use result of first as base"

    @covers(CFeature.FIELD_ACCESS)
    def test_struct_field_access_and_mutation(self):
        source = """\
struct Point { int x; int y; };
void f() {
    struct Point p;
    p.x = 10;
    p.y = p.x + 5;
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("Point" in s.operands for s in stores)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("x" in str(inst.operands) for inst in store_fields)
        assert any("y" in str(inst.operands) for inst in store_fields)
        binops = _find_all(ir, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    @covers(CFeature.ADDRESS_OF)
    def test_pointer_dereference_and_address(self):
        source = """\
void f() {
    int x = 42;
    int *p = &x;
    int y = *p;
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        # Address-of produces ADDRESS_OF for identifiers
        assert Opcode.ADDRESS_OF in opcodes
        addr_ofs = _find_all(ir, Opcode.ADDRESS_OF)
        assert any("x" in inst.operands for inst in addr_ofs)
        # Pointer dereference produces LOAD_INDIRECT
        loads = _find_all(ir, Opcode.LOAD_INDIRECT)
        assert len(loads) >= 1
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in s.operands for s in stores)
        assert any("p" in s.operands for s in stores)
        assert any("y" in s.operands for s in stores)

    @covers(CFeature.FUNCTION_CALL)
    def test_function_calling_function(self):
        source = """\
int double_val(int x) { return x * 2; }
int quadruple(int x) { return double_val(double_val(x)); }
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("double_val" in s.operands for s in stores)
        assert any("quadruple" in s.operands for s in stores)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("double_val" in inst.operands for inst in calls)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 2

    @covers(CFeature.WHILE_LOOP)
    def test_while_with_nested_if_else(self):
        source = """\
void f() {
    int count = 0;
    int total = 0;
    while (count < 20) {
        if (count % 2 == 0) {
            total = total + count;
        } else {
            total = total - 1;
        }
        count++;
    }
}
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        labels = _labels_in_order(ir)
        assert any("while" in lbl for lbl in labels)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("total" in s.operands for s in stores)
        assert any("count" in s.operands for s in stores)
        assert len(ir) > 25

    @covers(CFeature.SWITCH)
    def test_switch_statement(self):
        source = """\
void f() {
    switch (x) {
        case 1: y = 10; break;
        case 2: y = 20; break;
        default: y = 0; break;
    }
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert (
            Opcode.BRANCH_IF in opcodes
        ), "switch should lower to BRANCH_IF, not fall back to SYMBOLIC"
        assert len(ir) > 3

    @covers(CFeature.DO_WHILE)
    def test_do_while_loop(self):
        source = """\
void f() {
    int x = 10;
    do {
        x = x - 1;
    } while (x > 0);
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in s.operands for s in stores)
        assert len(ir) > 10

    @covers(CFeature.ARROW_OPERATOR)
    def test_field_access_arrow_operator(self):
        source = """\
void f() {
    int val = node->value;
    node->next = other->next;
}
"""
        ir = _parse_and_lower(source)
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert any("value" in inst.operands for inst in load_fields)
        assert any("next" in inst.operands for inst in load_fields)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("next" in inst.operands for inst in store_fields)


class TestCFrontendStructFieldDeclaration:
    @covers(CFeature.STRUCT)
    def test_struct_multi_field_lowering(self):
        source = """
struct Vec3 {
    float x;
    float y;
    float z;
};
"""
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        field_names = [
            inst.operands[1] for inst in store_fields if len(inst.operands) > 1
        ]
        assert "x" in field_names
        assert "y" in field_names
        assert "z" in field_names

    @covers(CFeature.STRUCT)
    def test_struct_field_loads_this(self):
        source = """
struct Pair {
    int first;
    int second;
};
"""
        ir = _parse_and_lower(source)
        load_vars = _find_all(ir, Opcode.LOAD_VAR)
        this_loads = [v for v in load_vars if "this" in v.operands]
        assert len(this_loads) >= 2


class TestCFrontendGoto:
    @covers(CFeature.GOTO)
    def test_goto_emits_branch(self):
        source = """\
void f() {
    int x = 0;
    start: x++;
    if (x < 10) goto start;
}
"""
        ir = _parse_and_lower(source)
        labels = _find_all(ir, Opcode.LABEL)
        assert any(inst.label.contains("user_start") for inst in labels)
        branches = _find_all(ir, Opcode.BRANCH)
        assert any(inst.label.contains("user_start") for inst in branches)

    @covers(CFeature.GOTO)
    def test_goto_with_different_label(self):
        source = """\
void f() {
    goto done;
    int x = 1;
    done: return;
}
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH)
        assert any(inst.label.contains("user_done") for inst in branches)


class TestCFrontendTypedef:
    @covers(CFeature.TYPEDEF)
    def test_typedef_simple(self):
        """typedef int myint; seeds alias myint → Int."""
        source = "typedef int myint;"
        _, builder = _parse_and_lower_with_types(source)
        assert TypeName("myint") in builder.type_aliases
        assert str(builder.type_aliases[TypeName("myint")]) == "Int"

    @covers(CFeature.TYPEDEF)
    def test_typedef_struct(self):
        """typedef struct Point { ... } Point; seeds alias Point."""
        source = "typedef struct Point { int x; int y; } Point;"
        ir, builder = _parse_and_lower_with_types(source)
        # Point should be seeded as alias (the struct body is still lowered)
        assert TypeName("Point") in builder.type_aliases

    @covers(CFeature.TYPEDEF)
    def test_typedef_unsigned(self):
        """typedef unsigned long ulong; seeds alias ulong → Int."""
        source = "typedef unsigned long ulong;"
        _, builder = _parse_and_lower_with_types(source)
        assert TypeName("ulong") in builder.type_aliases


class TestCFrontendEnumSpecifier:
    @covers(CFeature.ENUM)
    def test_enum_produces_new_object_and_store_field(self):
        source = "enum Color { Red, Green, Blue };"
        ir = _parse_and_lower(source)
        new_objs = _find_all(ir, Opcode.NEW_OBJECT)
        assert any("enum:Color" in str(inst.operands) for inst in new_objs)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        field_names = [
            inst.operands[1] for inst in store_fields if len(inst.operands) > 1
        ]
        assert "Red" in field_names
        assert "Green" in field_names
        assert "Blue" in field_names

    @covers(CFeature.ENUM)
    def test_enum_ordinal_values(self):
        source = "enum Priority { Low, Medium, High };"
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        const_vals = [inst.operands[0] for inst in consts if inst.operands]
        assert "0" in const_vals
        assert "1" in const_vals
        assert "2" in const_vals

    @covers(CFeature.ENUM)
    def test_enum_with_explicit_values(self):
        source = "enum Bits { A = 1, B = 2, C = 4 };"
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        field_names = [
            inst.operands[1] for inst in store_fields if len(inst.operands) > 1
        ]
        assert "A" in field_names
        assert "B" in field_names
        assert "C" in field_names
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("Bits" in inst.operands for inst in stores)


class TestCFrontendUnionSpecifier:
    @covers(CFeature.UNION)
    def test_union_produces_class_ref(self):
        source = """\
union Data {
    int i;
    float f;
};
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("Data" in inst.operands for inst in stores)
        consts = _find_all(ir, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)

    @covers(CFeature.UNION)
    def test_union_fields_lowered(self):
        source = """\
union Value {
    int x;
    double y;
};
"""
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        field_names = [
            inst.operands[1] for inst in store_fields if len(inst.operands) > 1
        ]
        assert "x" in field_names
        assert "y" in field_names


class TestCFrontendCharLiteral:
    @covers(CFeature.CHAR_LITERAL)
    def test_char_literal_produces_const(self):
        source = "void f() { char c = 'A'; }"
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        assert any("'A'" in str(inst.operands) for inst in consts)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("char_literal" in str(inst.operands) for inst in symbolics)

    @covers(CFeature.CHAR_LITERAL)
    def test_char_literal_no_symbolic_fallback(self):
        source = "void f() { char c = 'x'; }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("char_literal" in str(inst.operands) for inst in symbolics)
        assert not any("character_literal" in str(inst.operands) for inst in symbolics)

    @covers(CFeature.CHAR_LITERAL)
    def test_char_literal_stored_to_variable(self):
        source = "void f() { char c = 'Z'; }"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("c" in inst.operands for inst in stores)


class TestCFrontendInitializerList:
    @covers(CFeature.INITIALIZER_LIST)
    def test_initializer_list_produces_new_array(self):
        source = "void f() { int arr[] = {1, 2, 3}; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes
        store_indexes = _find_all(ir, Opcode.STORE_INDEX)
        assert len(store_indexes) >= 3

    @covers(CFeature.INITIALIZER_LIST)
    def test_initializer_list_empty(self):
        source = "void f() { int arr[] = {}; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes

    @covers(CFeature.INITIALIZER_LIST)
    def test_initializer_list_nested(self):
        source = "void f() { int m[2][2] = {{1, 2}, {3, 4}}; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes
        store_indexes = _find_all(ir, Opcode.STORE_INDEX)
        assert len(store_indexes) >= 2


class TestCInitializerPair:
    @covers(CFeature.DESIGNATED_INITIALIZER)
    def test_designated_initializer_no_symbolic(self):
        source = "void f() { struct S s = {.x = 1, .y = 2}; }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("initializer_pair" in str(inst.operands) for inst in symbolics)

    @covers(CFeature.DESIGNATED_INITIALIZER)
    def test_designated_initializer_lowers_values(self):
        source = "void f() { struct S s = {.x = 10, .y = 20}; }"
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        assert any("10" in inst.operands for inst in consts)
        assert any("20" in inst.operands for inst in consts)


class TestCFrontendPreprocFunctionDef:
    @covers(CFeature.MACRO)
    def test_preproc_function_def_no_unsupported(self):
        """#define MAX(a, b) ((a) > (b) ? (a) : (b)) should not produce unsupported SYMBOLIC."""
        source = "#define MAX(a, b) ((a) > (b) ? (a) : (b))"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    @covers(CFeature.MACRO)
    def test_preproc_function_def_with_other_code(self):
        source = """\
#define SQUARE(x) ((x) * (x))
int y = 10;
"""
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("y" in inst.operands for inst in stores)


class TestCFrontendCaseStatementDefensive:
    """Verify case_statement has a dispatch entry for defensive handling."""

    @covers(CFeature.SWITCH)
    def test_case_statement_has_dispatch_entry(self):
        """case_statement is registered in stmt dispatch for defensive handling."""
        frontend = CFrontend(TreeSitterParserFactory(), "c")
        assert "case_statement" in frontend._build_stmt_dispatch()

    @covers(CFeature.SWITCH)
    def test_switch_case_still_works_after_dispatch_entry(self):
        """Adding case_statement to _STMT_DISPATCH must not break normal
        switch/case lowering (which bypasses _lower_block on the body)."""
        source = """\
void f() {
    switch (x) {
        case 1: y = 10; break;
        case 2: y = 20; break;
        default: y = 0; break;
    }
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        # Normal switch produces BRANCH_IF for case comparisons
        assert Opcode.BRANCH_IF in opcodes
        # No unsupported SYMBOLIC
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)


class TestCFrontendPointerTypeSeed:
    """Pointer declarations should seed Pointer[BaseType] in type_env_builder."""

    @covers(CFeature.POINTER_TYPE)
    def test_int_pointer_variable_gets_pointer_int(self):
        """int *p = &x; should seed var_types['p'] = 'Pointer[Int]'."""
        _, builder = _parse_and_lower_with_types("void f() { int *p = &x; }")
        assert builder.var_types["p"] == "Pointer[Int]"

    @covers(CFeature.POINTER_TYPE)
    def test_float_pointer_variable(self):
        """float *fp; should seed var_types['fp'] = 'Pointer[Float]'."""
        _, builder = _parse_and_lower_with_types("void f() { float *fp; }")
        assert builder.var_types["fp"] == "Pointer[Float]"

    @covers(CFeature.POINTER_TYPE)
    def test_double_pointer_variable(self):
        """int **pp; should seed var_types['pp'] = 'Pointer[Pointer[Int]]'."""
        _, builder = _parse_and_lower_with_types("void f() { int **pp; }")
        assert builder.var_types["pp"] == "Pointer[Pointer[Int]]"

    @covers(CFeature.VARIABLE_DECLARATION)
    def test_non_pointer_unchanged(self):
        """int x = 42; should still seed var_types['x'] = 'Int'."""
        _, builder = _parse_and_lower_with_types("void f() { int x = 42; }")
        assert builder.var_types["x"] == "Int"

    @covers(CFeature.POINTER_TYPE)
    def test_pointer_parameter_gets_pointer_type(self):
        """int f(int *arr) should seed param type as Pointer[Int]."""
        _, builder = _parse_and_lower_with_types("int f(int *arr) { return *arr; }")
        # Find the param type for 'arr'
        func_label = next(k for k in builder.func_param_types if "f" in k)
        param_types = dict(builder.func_param_types[func_label])
        assert param_types["arr"] == "Pointer[Int]"

    @covers(CFeature.POINTER_TYPE)
    def test_char_pointer_gets_pointer_int(self):
        """char *s; — char maps to Int, so char* is Pointer[Int]."""
        _, builder = _parse_and_lower_with_types("void f() { char *s; }")
        assert builder.var_types["s"] == "Pointer[Int]"

    @covers(CFeature.POINTER_TYPE)
    def test_void_pointer(self):
        """void *vp; — void maps to Any, so void* is Pointer[Any]."""
        _, builder = _parse_and_lower_with_types("void f() { void *vp; }")
        assert builder.var_types["vp"] == "Pointer[Any]"


class TestCLinkageSpecification:
    @covers(CFeature.PREPROCESSOR)
    def test_linkage_spec_no_symbolic(self):
        """extern 'C' { ... } should not produce SYMBOLIC fallthrough."""
        frontend = CFrontend(TreeSitterParserFactory(), "c")
        ir = frontend.lower(b'extern "C" { int foo(); }')
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "linkage_specification" in str(inst.operands) for inst in symbolics
        )

    @covers(CFeature.PREPROCESSOR)
    def test_linkage_spec_body_lowered(self):
        """Declarations inside extern 'C' should still be lowered."""
        frontend = CFrontend(TreeSitterParserFactory(), "c")
        ir = frontend.lower(b'extern "C" { int x = 42; }')
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestCStructInitializerList:
    """Struct initializer lists must emit CALL_FUNCTION + STORE_FIELD, not NEW_ARRAY."""

    @covers(CFeature.INITIALIZER_LIST)
    def test_positional_init_emits_call_function_not_new_array(self):
        """struct Node n = {3, 0} should create an object, not an array."""
        ir = _parse_and_lower("""\
struct Node { int value; int next; };
struct Node n = {3, 0};
""")
        # Should NOT have NEW_ARRAY for the struct init
        new_arrays = _find_all(ir, Opcode.NEW_ARRAY)
        assert (
            len(new_arrays) == 0
        ), f"Expected no NEW_ARRAY for struct init, got {new_arrays}"
        # Should have CALL_FUNCTION Node (constructor)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        node_calls = [c for c in calls if "Node" in str(c.operands)]
        assert len(node_calls) >= 1, f"Expected CALL_FUNCTION Node, got {calls}"

    @covers(CFeature.INITIALIZER_LIST)
    def test_positional_init_stores_fields_by_name(self):
        """Positional initializer {3, 0} should emit STORE_FIELD with field names."""
        ir = _parse_and_lower("""\
struct Node { int value; int next; };
struct Node n = {3, 0};
""")
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        init_fields = [
            sf.operands[1] for sf in store_fields if sf.operands[1] in ("value", "next")
        ]
        # Class body emits default STORE_FIELD, plus the initializer should emit them
        # The initializer should store "value" and "next"
        assert (
            "value" in init_fields
        ), f"Expected STORE_FIELD for 'value' from initializer, got {init_fields}"
        assert (
            "next" in init_fields
        ), f"Expected STORE_FIELD for 'next' from initializer, got {init_fields}"

    @covers(CFeature.DESIGNATED_INITIALIZER)
    def test_designated_init_stores_fields_by_name(self):
        """Designated initializer {.value = 3, .next = 0} should emit STORE_FIELD."""
        ir = _parse_and_lower("""\
struct Node { int value; int next; };
struct Node n = {.value = 3, .next = 0};
""")
        new_arrays = _find_all(ir, Opcode.NEW_ARRAY)
        assert (
            len(new_arrays) == 0
        ), f"Expected no NEW_ARRAY for designated init, got {new_arrays}"
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        init_fields = [
            sf.operands[1] for sf in store_fields if sf.operands[1] in ("value", "next")
        ]
        assert "value" in init_fields
        assert "next" in init_fields

    @covers(CFeature.STRUCT)
    def test_pointer_field_included_in_struct_body(self):
        """struct Node { int value; struct Node* next; } should emit
        STORE_FIELD for both fields, including the pointer field."""
        ir = _parse_and_lower("""\
struct Node { int value; struct Node* next; };
""")
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        field_names = [sf.operands[1] for sf in store_fields]
        assert "value" in field_names, f"Missing 'value' field, got {field_names}"
        assert "next" in field_names, f"Missing 'next' pointer field, got {field_names}"

    @covers(CFeature.INITIALIZER_LIST)
    def test_array_init_still_uses_new_array(self):
        """int arr[] = {1, 2, 3} should still use NEW_ARRAY (not affected by fix)."""
        ir = _parse_and_lower("int arr[] = {1, 2, 3};")
        new_arrays = _find_all(ir, Opcode.NEW_ARRAY)
        assert len(new_arrays) >= 1, "Array init should still use NEW_ARRAY"


class TestCFrontendTernaryOperator:
    @covers(CFeature.TERNARY_OPERATOR)
    def test_c_ternary_operator_execution(self) -> None:
        source = """
        int compute(int val) {
            return val * 10;
        }
        int main() {
            int a = 6;
            int b = 0;
            // a > 5 is true
            // b (0) is false, so it takes the 'a + b' branch = 6 + 0 = 6
            int result1 = (a > 5) ? (b ? compute(a) * 2 : a + b) : compute(b) - 1;
            
            // a < 5 is false, so it evaluates compute(b) - 1 = compute(0) - 1 = -1
            int result2 = (a < 5) ? 100 : compute(b) - 1;
            
            return result1 + result2;
        }
        """
        from interpreter.api import build_cfg_from_source, lower_source
        from interpreter.cfg import build_cfg
        from interpreter.registry import build_registry
        from interpreter.run import execute_cfg, VMConfig
        from interpreter.var_name import VarName
        from interpreter.types.typed_value import unwrap

        from interpreter.run import build_execution_strategies
        from interpreter.frontend import get_frontend
        from interpreter.constants import Language

        frontend = get_frontend(Language("c"))
        instructions = frontend.lower(source.encode("utf-8"))
        cfg = build_cfg(instructions)
        registry = build_registry(
            instructions,
            cfg,
            func_symbol_table=frontend.func_symbol_table,
            class_symbol_table=frontend.class_symbol_table,
        )
        strategies = build_execution_strategies(
            frontend, instructions, registry, Language("c")
        )

        # Phase 1: preamble
        vm, _ = execute_cfg(
            cfg, cfg.entry, registry, VMConfig(max_steps=200), strategies
        )

        main_label = next(
            lbl for lbl in cfg.blocks if "main" in str(lbl) and "func" in str(lbl)
        )

        # Phase 2: call main
        final_state, stats = execute_cfg(
            cfg, main_label, registry, VMConfig(max_steps=200), strategies, vm=vm
        )

        # Expected return: result1 (6) + result2 (-1) = 5
        assert final_state is not None
        assert unwrap(final_state.current_frame.local_vars[VarName("result1")]) == 6
        assert unwrap(final_state.current_frame.local_vars[VarName("result2")]) == -1

    @covers(CFeature.TERNARY_OPERATOR)
    def test_c_ternary_operator(self) -> None:
        source = """
        int test_func(int condition) {
            int result = condition ? 42 : 99;
            return result;
        }
        """
        cfg = build_cfg_from_source(source, "c", function_name="test_func")

        # Verify the structure: conditional branch and a merge point
        branch_block = cfg.blocks[cfg.entry]
        branch_inst = branch_block.instructions[-1]
        assert isinstance(branch_inst, BranchIf)

        true_label, false_label = branch_inst.branch_targets
        assert true_label.value.startswith("ternary_true")
        assert false_label.value.startswith("ternary_false")

        true_block = cfg.blocks[true_label]
        false_block = cfg.blocks[false_label]

        # Verify both branches merge
        assert len(true_block.successors) == 1
        assert len(false_block.successors) == 1
        merge_label = true_block.successors[0]
        assert merge_label == false_block.successors[0]
        assert merge_label.value.startswith("ternary_end")

    @covers(CFeature.TERNARY_OPERATOR)
    def test_c_complex_nested_ternary(self) -> None:
        source = """
        int compute(int x);
        int test_complex(int a, int b) {
            int result = (a > 5) ? (b ? compute(a) * 2 : a + b) : compute(b) - 1;
            return result;
        }
        """
        cfg = build_cfg_from_source(source, "c", function_name="test_complex")

        # Verify we have multiple BranchIf instructions
        branch_ifs = [
            inst
            for block in cfg.blocks.values()
            for inst in block.instructions
            if isinstance(inst, BranchIf)
        ]
        assert len(branch_ifs) == 2

        # Verify we have both CallFunction (compute) and Binop instructions
        calls = [
            inst
            for block in cfg.blocks.values()
            for inst in block.instructions
            if isinstance(inst, CallFunction)
        ]
        assert len(calls) == 2

        binops = [
            inst
            for block in cfg.blocks.values()
            for inst in block.instructions
            if isinstance(inst, Binop)
        ]
        # At least one > for the condition, one * for compute(a)*2, one + for a+b, one - for compute(b)-1
        assert len(binops) >= 4
