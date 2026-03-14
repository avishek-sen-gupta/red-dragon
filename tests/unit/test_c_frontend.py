"""Tests for CFrontend — tree-sitter C AST -> IR lowering."""

from __future__ import annotations

from interpreter.frontends.c import CFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode
from interpreter.type_environment_builder import TypeEnvironmentBuilder


def _parse_and_lower(source: str) -> list[IRInstruction]:
    frontend = CFrontend(TreeSitterParserFactory(), "c")
    return frontend.lower(source.encode("utf-8"))


def _parse_and_lower_with_types(
    source: str,
) -> tuple[list[IRInstruction], TypeEnvironmentBuilder]:
    frontend = CFrontend(TreeSitterParserFactory(), "c")
    instructions = frontend.lower(source.encode("utf-8"))
    return instructions, frontend.type_env_builder


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
            target for inst in branch_ifs for target in inst.label.split(",")
        }
        label_set = set(labels)
        assert branch_targets.issubset(
            label_set
        ), f"Unreachable targets: {branch_targets - label_set}"


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
        loads = _find_all(ir, Opcode.LOAD_VAR)
        assert any("x" in inst.operands for inst in loads)
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
        assert Opcode.ADDRESS_OF in opcodes
        addr_ofs = _find_all(ir, Opcode.ADDRESS_OF)
        assert any("x" in inst.operands for inst in addr_ofs)

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
        # grid[i][j] should produce two chained LOAD_INDEX (one per subscript)
        load_indices = _find_all(ir, Opcode.LOAD_INDEX)
        assert (
            len(load_indices) == 2
        ), "grid[i][j] should produce 2 LOAD_INDEX instructions"
        # Second LOAD_INDEX should chain off the first (nested subscript)
        assert (
            load_indices[1].operands[0] == load_indices[0].result_reg
        ), "grid[i][j]: second subscript should use result of first as base"

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
        # Address-of produces ADDRESS_OF for identifiers
        assert Opcode.ADDRESS_OF in opcodes
        addr_ofs = _find_all(ir, Opcode.ADDRESS_OF)
        assert any("x" in inst.operands for inst in addr_ofs)
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
        assert (
            Opcode.BRANCH_IF in opcodes
        ), "switch should lower to BRANCH_IF, not fall back to SYMBOLIC"
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
        """typedef int myint; seeds alias myint → Int."""
        source = "typedef int myint;"
        _, builder = _parse_and_lower_with_types(source)
        assert "myint" in builder.type_aliases
        assert str(builder.type_aliases["myint"]) == "Int"

    def test_typedef_struct(self):
        """typedef struct Point { ... } Point; seeds alias Point."""
        source = "typedef struct Point { int x; int y; } Point;"
        ir, builder = _parse_and_lower_with_types(source)
        # Point should be seeded as alias (the struct body is still lowered)
        assert "Point" in builder.type_aliases

    def test_typedef_unsigned(self):
        """typedef unsigned long ulong; seeds alias ulong → Int."""
        source = "typedef unsigned long ulong;"
        _, builder = _parse_and_lower_with_types(source)
        assert "ulong" in builder.type_aliases


class TestCFrontendEnumSpecifier:
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

    def test_enum_ordinal_values(self):
        source = "enum Priority { Low, Medium, High };"
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        const_vals = [inst.operands[0] for inst in consts if inst.operands]
        assert "0" in const_vals
        assert "1" in const_vals
        assert "2" in const_vals

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
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("Bits" in inst.operands for inst in stores)


class TestCFrontendUnionSpecifier:
    def test_union_produces_class_ref(self):
        source = """\
union Data {
    int i;
    float f;
};
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("Data" in inst.operands for inst in stores)
        consts = _find_all(ir, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

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
    def test_char_literal_produces_const(self):
        source = "void f() { char c = 'A'; }"
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        assert any("'A'" in str(inst.operands) for inst in consts)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("char_literal" in str(inst.operands) for inst in symbolics)

    def test_char_literal_no_symbolic_fallback(self):
        source = "void f() { char c = 'x'; }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("char_literal" in str(inst.operands) for inst in symbolics)
        assert not any("character_literal" in str(inst.operands) for inst in symbolics)

    def test_char_literal_stored_to_variable(self):
        source = "void f() { char c = 'Z'; }"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("c" in inst.operands for inst in stores)


class TestCFrontendInitializerList:
    def test_initializer_list_produces_new_array(self):
        source = "void f() { int arr[] = {1, 2, 3}; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes
        store_indexes = _find_all(ir, Opcode.STORE_INDEX)
        assert len(store_indexes) >= 3

    def test_initializer_list_empty(self):
        source = "void f() { int arr[] = {}; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes

    def test_initializer_list_nested(self):
        source = "void f() { int m[2][2] = {{1, 2}, {3, 4}}; }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes
        store_indexes = _find_all(ir, Opcode.STORE_INDEX)
        assert len(store_indexes) >= 2


class TestCInitializerPair:
    def test_designated_initializer_no_symbolic(self):
        source = "void f() { struct S s = {.x = 1, .y = 2}; }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("initializer_pair" in str(inst.operands) for inst in symbolics)

    def test_designated_initializer_lowers_values(self):
        source = "void f() { struct S s = {.x = 10, .y = 20}; }"
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        assert any("10" in inst.operands for inst in consts)
        assert any("20" in inst.operands for inst in consts)


class TestCFrontendPreprocFunctionDef:
    def test_preproc_function_def_no_unsupported(self):
        """#define MAX(a, b) ((a) > (b) ? (a) : (b)) should not produce unsupported SYMBOLIC."""
        source = "#define MAX(a, b) ((a) > (b) ? (a) : (b))"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_preproc_function_def_with_other_code(self):
        source = """\
#define SQUARE(x) ((x) * (x))
int y = 10;
"""
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)


class TestCFrontendCaseStatementDefensive:
    """Verify case_statement has a dispatch entry for defensive handling."""

    def test_case_statement_has_dispatch_entry(self):
        """case_statement is registered in stmt dispatch for defensive handling."""
        frontend = CFrontend(TreeSitterParserFactory(), "c")
        assert "case_statement" in frontend._build_stmt_dispatch()

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

    def test_int_pointer_variable_gets_pointer_int(self):
        """int *p = &x; should seed var_types['p'] = 'Pointer[Int]'."""
        _, builder = _parse_and_lower_with_types("void f() { int *p = &x; }")
        assert builder.var_types["p"] == "Pointer[Int]"

    def test_float_pointer_variable(self):
        """float *fp; should seed var_types['fp'] = 'Pointer[Float]'."""
        _, builder = _parse_and_lower_with_types("void f() { float *fp; }")
        assert builder.var_types["fp"] == "Pointer[Float]"

    def test_double_pointer_variable(self):
        """int **pp; should seed var_types['pp'] = 'Pointer[Pointer[Int]]'."""
        _, builder = _parse_and_lower_with_types("void f() { int **pp; }")
        assert builder.var_types["pp"] == "Pointer[Pointer[Int]]"

    def test_non_pointer_unchanged(self):
        """int x = 42; should still seed var_types['x'] = 'Int'."""
        _, builder = _parse_and_lower_with_types("void f() { int x = 42; }")
        assert builder.var_types["x"] == "Int"

    def test_pointer_parameter_gets_pointer_type(self):
        """int f(int *arr) should seed param type as Pointer[Int]."""
        _, builder = _parse_and_lower_with_types("int f(int *arr) { return *arr; }")
        # Find the param type for 'arr'
        func_label = next(k for k in builder.func_param_types if "f" in k)
        param_types = dict(builder.func_param_types[func_label])
        assert param_types["arr"] == "Pointer[Int]"

    def test_char_pointer_gets_pointer_int(self):
        """char *s; — char maps to Int, so char* is Pointer[Int]."""
        _, builder = _parse_and_lower_with_types("void f() { char *s; }")
        assert builder.var_types["s"] == "Pointer[Int]"

    def test_void_pointer(self):
        """void *vp; — void maps to Any, so void* is Pointer[Any]."""
        _, builder = _parse_and_lower_with_types("void f() { void *vp; }")
        assert builder.var_types["vp"] == "Pointer[Any]"


class TestCLinkageSpecification:
    def test_linkage_spec_no_symbolic(self):
        """extern 'C' { ... } should not produce SYMBOLIC fallthrough."""
        frontend = CFrontend(TreeSitterParserFactory(), "c")
        ir = frontend.lower(b'extern "C" { int foo(); }')
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "linkage_specification" in str(inst.operands) for inst in symbolics
        )

    def test_linkage_spec_body_lowered(self):
        """Declarations inside extern 'C' should still be lowered."""
        frontend = CFrontend(TreeSitterParserFactory(), "c")
        ir = frontend.lower(b'extern "C" { int x = 42; }')
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestCStructInitializerList:
    """Struct initializer lists must emit CALL_FUNCTION + STORE_FIELD, not NEW_ARRAY."""

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

    def test_array_init_still_uses_new_array(self):
        """int arr[] = {1, 2, 3} should still use NEW_ARRAY (not affected by fix)."""
        ir = _parse_and_lower("int arr[] = {1, 2, 3};")
        new_arrays = _find_all(ir, Opcode.NEW_ARRAY)
        assert len(new_arrays) >= 1, "Array init should still use NEW_ARRAY"
