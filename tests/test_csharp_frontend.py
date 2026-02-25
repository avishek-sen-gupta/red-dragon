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

    def test_unsupported_node_produces_symbolic(self):
        # A lambda expression is lowered as SYMBOLIC
        source = "var f = (x) => x + 1;"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        lambda_symbolics = [
            s for s in symbolics if any("lambda:" in str(op) for op in s.operands)
        ]
        assert len(lambda_symbolics) >= 1
