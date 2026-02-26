"""Tests for CFrontend — tree-sitter C AST -> IR lowering."""

from __future__ import annotations

import tree_sitter_language_pack

from interpreter.frontends.c import CFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_and_lower(source: str) -> list[IRInstruction]:
    parser = tree_sitter_language_pack.get_parser("c")
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    frontend = CFrontend()
    return frontend.lower(tree, source_bytes)


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestCFrontendDeclaration:
    def test_declaration_produces_const_and_store(self):
        ir = _parse_and_lower("int x = 10;")
        opcodes = _opcodes(ir)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 1

    def test_declaration_without_initializer(self):
        ir = _parse_and_lower("int x;")
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 1


class TestCFrontendFunctionDefinition:
    def test_function_def_produces_label_and_return(self):
        source = "int add(int a, int b) { return a + b; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.LABEL in opcodes
        assert Opcode.RETURN in opcodes

    def test_function_params_lowered_as_symbolic(self):
        source = "int add(int a, int b) { return a + b; }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        param_symbolics = [
            s for s in symbolics if any("param:" in str(op) for op in s.operands)
        ]
        assert len(param_symbolics) >= 2

    def test_function_name_stored(self):
        source = "int add(int a, int b) { return a + b; }"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        add_stores = [s for s in stores if "add" in s.operands]
        assert len(add_stores) >= 1


class TestCFrontendFunctionCall:
    def test_function_call_produces_call_function(self):
        source = "void f() { add(1, 2); }"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        add_calls = [c for c in calls if "add" in c.operands]
        assert len(add_calls) >= 1


class TestCFrontendIfElse:
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

    def test_if_else_produces_labels(self):
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
        assert len(labels) >= 3


class TestCFrontendWhileLoop:
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
        label_names = [lbl.label for lbl in labels]
        for_labels = [l for l in label_names if l and "for_" in l]
        assert len(for_labels) >= 2


class TestCFrontendStructDefinition:
    def test_struct_definition_produces_class_label(self):
        source = """
struct Point {
    int x;
    int y;
};
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        point_stores = [s for s in stores if "Point" in s.operands]
        assert len(point_stores) >= 1
        consts = _find_all(ir, Opcode.CONST)
        class_refs = [
            c for c in consts if any("class:" in str(op) for op in c.operands)
        ]
        assert len(class_refs) >= 1

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


class TestCFrontendAssignmentExpression:
    def test_assignment_expression(self):
        source = "void f() { int x; x = 10; }"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 2


class TestCFrontendFieldAccess:
    def test_dot_field_access_produces_load_field(self):
        source = "void f() { int z = obj.field; }"
        ir = _parse_and_lower(source)
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert len(load_fields) >= 1
        assert "field" in load_fields[0].operands

    def test_arrow_field_access_produces_load_field(self):
        source = "void f() { int z = ptr->field; }"
        ir = _parse_and_lower(source)
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert len(load_fields) >= 1
        assert "field" in load_fields[0].operands


class TestCFrontendReturn:
    def test_return_with_value(self):
        source = "int f() { return 42; }"
        ir = _parse_and_lower(source)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1

    def test_return_without_value(self):
        source = "void f() { return; }"
        ir = _parse_and_lower(source)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1


class TestCFrontendUpdateExpression:
    def test_increment_expression(self):
        source = "void f() { int i = 0; i++; }"
        ir = _parse_and_lower(source)
        binops = _find_all(ir, Opcode.BINOP)
        plus_ops = [b for b in binops if "+" in b.operands]
        assert len(plus_ops) >= 1

    def test_decrement_expression(self):
        source = "void f() { int i = 10; i--; }"
        ir = _parse_and_lower(source)
        binops = _find_all(ir, Opcode.BINOP)
        minus_ops = [b for b in binops if "-" in b.operands]
        assert len(minus_ops) >= 1


class TestCFrontendCastExpression:
    def test_cast_expression_lowers_value(self):
        source = "void f() { int y = (int)x; }"
        ir = _parse_and_lower(source)
        # The cast should transparently lower the inner value
        stores = _find_all(ir, Opcode.STORE_VAR)
        y_stores = [s for s in stores if "y" in s.operands]
        assert len(y_stores) >= 1


class TestCFrontendPreprocessor:
    def test_preprocessor_is_skipped(self):
        source = """
#include <stdio.h>
#define MAX 100
int x = 10;
"""
        ir = _parse_and_lower(source)
        # Preprocessor directives should be noise and not produce meaningful IR
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 1
        # No SYMBOLIC for the preprocessor directives themselves
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        preproc_symbolics = [
            s for s in symbolics if any("preproc" in str(op) for op in s.operands)
        ]
        assert len(preproc_symbolics) == 0


class TestCFrontendPointerOps:
    def test_pointer_dereference(self):
        source = "void f() { int z = *ptr; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.LOAD_FIELD in opcodes
        loads = _find_all(ir, Opcode.LOAD_FIELD)
        assert any("*" in inst.operands for inst in loads)

    def test_address_of(self):
        source = "void f() { int *p = &x; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.UNOP in opcodes
        unops = _find_all(ir, Opcode.UNOP)
        assert any("&" in inst.operands for inst in unops)

    def test_pointer_store(self):
        source = "void f() { *ptr = 42; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.STORE_FIELD in opcodes
        stores = _find_all(ir, Opcode.STORE_FIELD)
        assert any("*" in inst.operands for inst in stores)

    def test_sizeof_type(self):
        source = "void f() { int s = sizeof(int); }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.CALL_FUNCTION in opcodes
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("sizeof" in inst.operands for inst in calls)

    def test_compound_literal(self):
        source = "void f() { struct Point p = (struct Point){1, 2}; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes


class TestCFrontendFallback:
    def test_entry_label_always_present(self):
        ir = _parse_and_lower("")
        assert ir[0].opcode == Opcode.LABEL
        assert ir[0].label == "entry"


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialC:
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
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("sum" in s.operands for s in stores)
        assert any("i" in s.operands for s in stores)
        assert any("j" in s.operands for s in stores)
        assert len(ir) > 25

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
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("Point" in s.operands for s in stores)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("x" in str(inst.operands) for inst in store_fields)
        assert any("y" in str(inst.operands) for inst in store_fields)
        binops = _find_all(ir, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

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
        # Address-of produces UNOP with "&"
        assert Opcode.UNOP in opcodes
        unops = _find_all(ir, Opcode.UNOP)
        assert any("&" in inst.operands for inst in unops)
        # Pointer dereference produces LOAD_FIELD with "*"
        assert Opcode.LOAD_FIELD in opcodes
        loads = _find_all(ir, Opcode.LOAD_FIELD)
        assert any("*" in inst.operands for inst in loads)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in s.operands for s in stores)
        assert any("p" in s.operands for s in stores)
        assert any("y" in s.operands for s in stores)

    def test_function_calling_function(self):
        source = """\
int double_val(int x) { return x * 2; }
int quadruple(int x) { return double_val(double_val(x)); }
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("double_val" in s.operands for s in stores)
        assert any("quadruple" in s.operands for s in stores)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("double_val" in inst.operands for inst in calls)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 2

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
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("total" in s.operands for s in stores)
        assert any("count" in s.operands for s in stores)
        assert len(ir) > 25

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
        assert Opcode.SYMBOLIC in opcodes or Opcode.BRANCH_IF in opcodes
        assert len(ir) > 3

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
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in s.operands for s in stores)
        assert len(ir) > 10

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
    def test_struct_field_with_default(self):
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
        assert any("user_start" in (inst.label or "") for inst in labels)
        branches = _find_all(ir, Opcode.BRANCH)
        assert any("user_start" in (inst.label or "") for inst in branches)

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
        assert any("user_done" in (inst.label or "") for inst in branches)


class TestCFrontendTypedef:
    def test_typedef_simple(self):
        source = "typedef int myint;"
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        assert any("int" in str(inst.operands) for inst in consts)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("myint" in inst.operands for inst in stores)

    def test_typedef_struct(self):
        source = "typedef struct Point { int x; int y; } Point;"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("Point" in inst.operands for inst in stores)

    def test_typedef_unsigned(self):
        source = "typedef unsigned long ulong;"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("ulong" in inst.operands for inst in stores)
