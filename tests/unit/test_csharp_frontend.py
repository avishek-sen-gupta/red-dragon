"""Tests for CSharpFrontend — tree-sitter C# AST -> IR lowering."""

from __future__ import annotations

import tree_sitter_language_pack

from interpreter.frontends.csharp import CSharpFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_and_lower(source: str) -> list[IRInstruction]:
    parser = tree_sitter_language_pack.get_parser("csharp")
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    frontend = CSharpFrontend()
    return frontend.lower(tree, source_bytes)


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestCSharpFrontendVariableDeclaration:
    def test_variable_decl_produces_const_and_store(self):
        ir = _parse_and_lower("int x = 10;")
        opcodes = _opcodes(ir)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 1

    def test_variable_decl_without_initializer(self):
        ir = _parse_and_lower("int x;")
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 1


class TestCSharpFrontendArithmetic:
    def test_arithmetic_produces_binop(self):
        ir = _parse_and_lower("int x = 10; int y = x + 5;")
        binops = _find_all(ir, Opcode.BINOP)
        assert len(binops) >= 1
        assert "+" in binops[0].operands

    def test_arithmetic_stores_result(self):
        ir = _parse_and_lower("int x = 10; int y = x + 5;")
        stores = _find_all(ir, Opcode.STORE_VAR)
        y_stores = [s for s in stores if "y" in s.operands]
        assert len(y_stores) >= 1


class TestCSharpFrontendMethodDeclaration:
    def test_method_decl_produces_label_and_return(self):
        source = """
class Calc {
    int Add(int a, int b) {
        return a + b;
    }
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.LABEL in opcodes
        assert Opcode.RETURN in opcodes

    def test_method_params_lowered_as_symbolic(self):
        source = """
class Calc {
    int Add(int a, int b) {
        return a + b;
    }
}
"""
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        param_symbolics = [
            s for s in symbolics if any("param:" in str(op) for op in s.operands)
        ]
        assert len(param_symbolics) >= 2


class TestCSharpFrontendMethodCall:
    def test_simple_function_call(self):
        ir = _parse_and_lower("Add(1, 2);")
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        add_calls = [c for c in calls if "Add" in c.operands]
        assert len(add_calls) >= 1


class TestCSharpFrontendIfElse:
    def test_if_else_produces_branch_if(self):
        source = """
if (x > 5) {
    y = 1;
} else {
    y = 2;
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes

    def test_if_else_produces_labels(self):
        source = """
if (x > 5) {
    y = 1;
} else {
    y = 2;
}
"""
        ir = _parse_and_lower(source)
        labels = _find_all(ir, Opcode.LABEL)
        assert len(labels) >= 3


class TestCSharpFrontendWhileLoop:
    def test_while_loop_produces_branch_if_and_branch(self):
        source = """
while (x > 0) {
    x = x - 1;
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes


class TestCSharpFrontendForLoop:
    def test_for_loop_produces_branch_if(self):
        source = """
for (int i = 0; i < 10; i++) {
    x = i;
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        labels = _find_all(ir, Opcode.LABEL)
        label_names = [lbl.label for lbl in labels]
        for_labels = [l for l in label_names if l and "for_" in l]
        assert len(for_labels) >= 2


class TestCSharpFrontendClassDeclaration:
    def test_class_declaration(self):
        source = """
class Dog {
    void Bark() {
        return;
    }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        dog_stores = [s for s in stores if "Dog" in s.operands]
        assert len(dog_stores) >= 1
        consts = _find_all(ir, Opcode.CONST)
        class_refs = [
            c for c in consts if any("class:" in str(op) for op in c.operands)
        ]
        assert len(class_refs) >= 1


class TestCSharpFrontendInvocationExpression:
    def test_console_writeline_produces_call_method(self):
        source = 'Console.WriteLine("hello");'
        ir = _parse_and_lower(source)
        method_calls = _find_all(ir, Opcode.CALL_METHOD)
        assert len(method_calls) >= 1
        assert "WriteLine" in method_calls[0].operands


class TestCSharpFrontendMemberAccess:
    def test_member_access_produces_load_field(self):
        ir = _parse_and_lower("var z = obj.field;")
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert len(load_fields) >= 1
        assert "field" in load_fields[0].operands


class TestCSharpFrontendObjectCreation:
    def test_object_creation_produces_call_function(self):
        source = 'var dog = new Dog("Rex");'
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        dog_calls = [c for c in calls if "Dog" in c.operands]
        assert len(dog_calls) >= 1


class TestCSharpFrontendReturn:
    def test_return_with_value(self):
        source = """
class C {
    int F() { return 42; }
}
"""
        ir = _parse_and_lower(source)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1


class TestCSharpFrontendAssignmentExpression:
    def test_assignment_expression(self):
        ir = _parse_and_lower("x = 10;")
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 1


class TestCSharpFrontendFallback:
    def test_entry_label_always_present(self):
        ir = _parse_and_lower("")
        assert ir[0].opcode == Opcode.LABEL
        assert ir[0].label == "entry"

    def test_lambda_produces_func_ref(self):
        # A lambda expression is now lowered as an inline function
        source = "var f = (x) => x + 1;"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.RETURN in opcodes
        consts = _find_all(ir, Opcode.CONST)
        assert any("func:" in str(inst.operands) for inst in consts)


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialCSharp:
    def test_foreach_with_method_calls(self):
        source = """\
foreach (var item in items) {
    Console.WriteLine(item);
    result.Add(item);
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        calls = _find_all(ir, Opcode.CALL_METHOD)
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        assert "WriteLine" in method_names
        assert "Add" in method_names
        assert len(ir) > 10

    def test_do_while_loop(self):
        source = """\
int x = 10;
do {
    x = x - 1;
} while (x > 0);
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        labels = _labels_in_order(ir)
        assert any("do_" in lbl for lbl in labels)
        assert len(ir) > 8

    def test_class_with_constructor_and_property(self):
        source = """\
class Counter {
    int count;
    Counter(int start) {
        this.count = start;
    }
    int Value() {
        return this.count;
    }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("Counter" in s.operands for s in stores)
        consts = _find_all(ir, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("count" in inst.operands for inst in store_fields)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1
        assert len(ir) > 15

    def test_try_catch_with_throw(self):
        source = """\
try {
    int result = RiskyOp();
    Console.WriteLine(result);
} catch (Exception e) {
    throw new InvalidOperationException("failed");
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        labels = [i.label for i in ir if i.opcode == Opcode.LABEL]
        # try/catch body and catch block are lowered with LABEL/BRANCH
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_end" in l for l in labels)
        assert Opcode.THROW in opcodes
        # No catch_clause: or finally_clause: SYMBOLIC placeholders
        symbolics = [i for i in ir if i.opcode == Opcode.SYMBOLIC]
        assert not any("catch_clause:" in str(s.operands) for s in symbolics)
        assert not any("finally_clause:" in str(s.operands) for s in symbolics)
        assert len(ir) > 1

    def test_nested_if_else_chain(self):
        source = """\
if (x > 100) {
    grade = "A";
} else if (x > 50) {
    grade = "B";
} else {
    grade = "F";
}
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 1
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("grade" in inst.operands for inst in stores)
        binops = _find_all(ir, Opcode.BINOP)
        assert len(binops) >= 2
        labels = _labels_in_order(ir)
        assert len(labels) >= 3

    def test_lambda_in_declaration(self):
        source = "var square = (x) => x * x;"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("square" in inst.operands for inst in stores)
        consts = _find_all(ir, Opcode.CONST)
        assert any("func:" in str(inst.operands) for inst in consts)

    def test_for_loop_with_nested_if(self):
        source = """\
int total = 0;
for (int i = 0; i < 20; i++) {
    if (i % 2 == 0) {
        total = total + i;
    }
    Console.WriteLine(i);
}
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("total" in inst.operands for inst in stores)
        calls = _find_all(ir, Opcode.CALL_METHOD)
        assert any("WriteLine" in inst.operands for inst in calls)
        assert len(ir) > 20

    def test_switch_produces_if_else_chain(self):
        source = """\
switch (x) {
    case 1: y = 10; break;
    case 2: y = 20; break;
    default: y = 0; break;
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        # Switch is now lowered as if/else chain with BINOP ==
        binops = _find_all(ir, Opcode.BINOP)
        eq_ops = [b for b in binops if "==" in b.operands]
        assert len(eq_ops) == 2
        assert Opcode.BRANCH_IF in opcodes


class TestCSharpLambda:
    def test_lambda_expr_body(self):
        source = "var f = (int x) => x + 1;"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.RETURN in opcodes
        assert Opcode.BINOP in opcodes
        consts = _find_all(ir, Opcode.CONST)
        assert any("func:" in str(inst.operands) for inst in consts)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("f" in inst.operands for inst in stores)

    def test_lambda_block_body(self):
        source = "var f = (int x) => { return x + 1; };"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.RETURN in opcodes
        assert Opcode.BINOP in opcodes
        consts = _find_all(ir, Opcode.CONST)
        assert any("func:" in str(inst.operands) for inst in consts)


class TestCSharpArrayCreation:
    def test_array_creation_with_initializer(self):
        source = "int[] a = new int[] { 1, 2, 3 };"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes
        stores = _find_all(ir, Opcode.STORE_INDEX)
        assert len(stores) >= 3

    def test_implicit_array_creation(self):
        source = "var a = new[] { 1, 2, 3 };"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes

    def test_array_creation_sized(self):
        source = "int[] a = new int[5];"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes


class TestCSharpEnumDeclaration:
    def test_enum_declaration(self):
        source = "enum Color { Red, Green, Blue }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_OBJECT in opcodes
        new_objs = _find_all(ir, Opcode.NEW_OBJECT)
        assert any("enum:Color" in str(inst.operands) for inst in new_objs)
        stores = _find_all(ir, Opcode.STORE_INDEX)
        assert len(stores) >= 3

    def test_enum_with_values(self):
        source = "enum Priority { Low, Medium, High }"
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        const_vals = [inst.operands[0] for inst in consts if inst.operands]
        assert "Low" in const_vals
        assert "Medium" in const_vals
        assert "High" in const_vals


class TestCSharpTypeofAndIsCheck:
    def test_typeof_expression(self):
        source = "class C { void M() { var t = typeof(int); } }"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("typeof" in inst.operands for inst in calls)
        consts = _find_all(ir, Opcode.CONST)
        const_vals = [inst.operands[0] for inst in consts if inst.operands]
        assert "int" in const_vals

    def test_typeof_with_class_type(self):
        source = "class C { void M() { var t = typeof(string); } }"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("typeof" in inst.operands for inst in calls)

    def test_is_check_expression(self):
        source = "class C { void M(object x) { bool b = x is string; } }"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("is_check" in inst.operands for inst in calls)
        consts = _find_all(ir, Opcode.CONST)
        const_vals = [inst.operands[0] for inst in consts if inst.operands]
        assert "string" in const_vals

    def test_is_check_in_condition(self):
        source = """\
class C {
    void M(object x) {
        if (x is int) {
            int y = 1;
        }
    }
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("is_check" in inst.operands for inst in calls)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes


class TestCSharpInterfaceDeclaration:
    def test_interface_emits_new_object(self):
        source = "interface IShape { void Draw(); }"
        ir = _parse_and_lower(source)
        new_objs = _find_all(ir, Opcode.NEW_OBJECT)
        assert any("interface:IShape" in str(inst.operands) for inst in new_objs)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("IShape" in inst.operands for inst in stores)

    def test_interface_with_multiple_members(self):
        source = "interface IAnimal { void Speak(); string Name(); }"
        ir = _parse_and_lower(source)
        new_objs = _find_all(ir, Opcode.NEW_OBJECT)
        assert any("interface:IAnimal" in str(inst.operands) for inst in new_objs)
        store_indexes = _find_all(ir, Opcode.STORE_INDEX)
        assert len(store_indexes) >= 2


class TestCSharpPropertyDeclaration:
    def test_auto_property(self):
        source = "class C { public int X { get; set; } }"
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("X" in inst.operands for inst in store_fields)
        load_vars = _find_all(ir, Opcode.LOAD_VAR)
        assert any("this" in inst.operands for inst in load_vars)

    def test_property_with_initializer(self):
        source = "class C { public int X { get; set; } = 42; }"
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("X" in inst.operands for inst in store_fields)
        consts = _find_all(ir, Opcode.CONST)
        const_vals = [inst.operands[0] for inst in consts if inst.operands]
        assert "42" in const_vals

    def test_property_with_accessor_body(self):
        source = """\
class C {
    int count;
    public int Count {
        get { return count; }
        set { count = value; }
    }
}
"""
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("Count" in inst.operands for inst in store_fields)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1
