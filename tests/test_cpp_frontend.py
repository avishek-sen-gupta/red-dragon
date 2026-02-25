"""Tests for CppFrontend -- tree-sitter C++ AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.cpp import CppFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_cpp(source: str) -> list[IRInstruction]:
    parser = get_parser("cpp")
    tree = parser.parse(source.encode("utf-8"))
    frontend = CppFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestCppDeclarations:
    def test_int_declaration(self):
        instructions = _parse_cpp("int x = 10;")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_declaration_without_initializer(self):
        instructions = _parse_cpp("int x;")
        opcodes = _opcodes(instructions)
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestCppFunctions:
    def test_function_definition(self):
        instructions = _parse_cpp("int add(int a, int b) { return a + b; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("add" in inst.operands for inst in stores)

    def test_function_call(self):
        instructions = _parse_cpp("int main() { add(1, 2); }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("add" in inst.operands for inst in calls)

    def test_return_statement(self):
        instructions = _parse_cpp("int main() { return 42; }")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)


class TestCppControlFlow:
    def test_if_else_with_condition_clause(self):
        instructions = _parse_cpp(
            "int main() { if (x > 5) { y = 1; } else { y = 0; } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("if_true" in (inst.label or "") for inst in labels)

    def test_while_with_condition_clause(self):
        instructions = _parse_cpp("int main() { while (x > 0) { x--; } }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("while" in (inst.label or "") for inst in labels)

    def test_c_style_for_loop(self):
        instructions = _parse_cpp(
            "int main() { for (int i = 0; i < 10; i++) { x = x + i; } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("i" in inst.operands for inst in stores)


class TestCppClasses:
    def test_class_with_methods(self):
        instructions = _parse_cpp("class Dog { public: void bark() { return; } };")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

    def test_namespace_transparent(self):
        instructions = _parse_cpp("namespace myns { int x = 10; }")
        opcodes = _opcodes(instructions)
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestCppExpressions:
    def test_new_expression(self):
        instructions = _parse_cpp('int main() { Dog* d = new Dog("Rex"); }')
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("Dog" in inst.operands for inst in calls)

    def test_delete_expression(self):
        instructions = _parse_cpp("int main() { delete ptr; }")
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("delete:" in str(inst.operands) for inst in symbolics)

    def test_lambda_expression(self):
        instructions = _parse_cpp(
            "int main() { auto f = [](int a, int b) { return a + b; }; }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        assert Opcode.BINOP in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any("__lambda" in str(inst.operands) for inst in consts)

    def test_template_declaration(self):
        instructions = _parse_cpp(
            "template <typename T> T identity(T val) { return val; }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("identity" in inst.operands for inst in stores)


class TestCppSpecial:
    def test_empty_program(self):
        instructions = _parse_cpp("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_fallback_symbolic(self):
        instructions = _parse_cpp('int main() { asm volatile("nop"); }')
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes

    def test_string_literal(self):
        instructions = _parse_cpp('int main() { const char* s = "hello"; }')
        consts = _find_all(instructions, Opcode.CONST)
        assert any('"hello"' in inst.operands for inst in consts)

    def test_binary_expression(self):
        instructions = _parse_cpp("int main() { int z = x + y; }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialCpp:
    def test_class_with_constructor_and_method(self):
        source = """\
class Counter {
public:
    int count;
    Counter(int start) { this->count = start; }
    int value() { return this->count; }
    void increment() { this->count = this->count + 1; }
};
"""
        instructions = _parse_cpp(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Counter" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("count" in inst.operands for inst in store_fields)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1
        assert len(instructions) > 20

    def test_new_delete_with_method(self):
        source = """\
int main() {
    Dog* d = new Dog("Rex");
    d->bark();
    delete d;
}
"""
        instructions = _parse_cpp(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("Dog" in inst.operands for inst in calls)
        method_calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("bark" in inst.operands for inst in method_calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("delete:" in str(inst.operands) for inst in symbolics)

    def test_lambda_capture_and_call(self):
        source = """\
int main() {
    int x = 10;
    auto f = [](int a, int b) { return a + b; };
    int result = f(x, 20);
}
"""
        instructions = _parse_cpp(source)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("__lambda" in str(inst.operands) for inst in consts)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)
        assert any("f" in inst.operands for inst in stores)

    def test_range_for_with_method(self):
        source = """\
int main() {
    for (auto& item : items) {
        item.process();
        result.push_back(item.value());
    }
}
"""
        instructions = _parse_cpp(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        assert "process" in method_names
        assert "push_back" in method_names
        assert len(instructions) > 10

    def test_static_cast(self):
        source = """\
int main() {
    double pi = 3.14;
    int truncated = static_cast<int>(pi);
}
"""
        instructions = _parse_cpp(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("pi" in inst.operands for inst in stores)
        assert any("truncated" in inst.operands for inst in stores)

    def test_try_catch_with_throw(self):
        source = """\
int main() {
    try {
        int result = riskyOp();
        use(result);
    } catch (const std::exception& e) {
        throw std::runtime_error("wrapped");
    }
}
"""
        instructions = _parse_cpp(source)
        opcodes = _opcodes(instructions)
        labels = [i.label for i in instructions if i.opcode == Opcode.LABEL]
        # try/catch body and catch block are lowered with LABEL/BRANCH
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_end" in l for l in labels)
        assert Opcode.THROW in opcodes
        # No catch_clause: SYMBOLIC placeholders
        symbolics = [i for i in instructions if i.opcode == Opcode.SYMBOLIC]
        assert not any("catch_clause:" in str(s.operands) for s in symbolics)
        assert len(instructions) > 3

    def test_namespace_function_with_loop(self):
        source = """\
namespace math {
    int sum(int n) {
        int total = 0;
        for (int i = 1; i <= n; i++) {
            total = total + i;
        }
        return total;
    }
}
"""
        instructions = _parse_cpp(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.RETURN in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("total" in inst.operands for inst in stores)
        assert any("sum" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        assert len(instructions) > 15

    def test_template_function(self):
        source = """\
template <typename T>
T max_val(T a, T b) {
    if (a > b) {
        return a;
    }
    return b;
}
"""
        instructions = _parse_cpp(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 2
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("max_val" in inst.operands for inst in stores)
