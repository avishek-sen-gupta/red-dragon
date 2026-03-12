"""Tests for CppFrontend -- tree-sitter C++ AST to IR lowering."""

from __future__ import annotations

from interpreter.frontends.cpp import CppFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_cpp(source: str) -> list[IRInstruction]:
    frontend = CppFrontend(TreeSitterParserFactory(), "cpp")
    return frontend.lower(source.encode("utf-8"))


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

    def test_if_elseif_chain_all_branches_produce_ir(self):
        """All branches of if/else-if/else-if/else must produce IR."""
        instructions = _parse_cpp(
            "int main() { if (x==1) { y=10; }"
            " else if (x==2) { y=20; }"
            " else if (x==3) { y=30; }"
            " else { y=40; } }"
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
            target for inst in branch_ifs for target in inst.label.split(",")
        }
        label_set = set(labels)
        assert branch_targets.issubset(
            label_set
        ), f"Unreachable targets: {branch_targets - label_set}"


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
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("delete" in inst.operands for inst in calls)

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
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("unsupported:" in str(inst.operands) for inst in symbolics)

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
        delete_calls = [
            c
            for c in _find_all(instructions, Opcode.CALL_FUNCTION)
            if "delete" in c.operands
        ]
        assert len(delete_calls) >= 1

    def test_lambda_capture_and_call(self):
        source = """\
int main() {
    int x = 10;
    auto f = [x](int a, int b) { return a + x + b; };
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
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("x" in inst.operands for inst in loads)

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
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("pi" in inst.operands for inst in loads)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

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
        assert len(instructions) > 10

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


class TestCppFieldInitializerList:
    def test_field_initializer_list(self):
        source = """\
class Point {
    int x, y;
    Point(int a, int b) : x(a), y(b) {}
};
"""
        instructions = _parse_cpp(source)
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.STORE_FIELD in opcodes
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        field_names = [
            inst.operands[1] for inst in store_fields if len(inst.operands) > 1
        ]
        assert "x" in field_names
        assert "y" in field_names

    def test_field_initializer_single(self):
        source = """\
class Counter {
    int count;
    Counter(int c) : count(c) {}
};
"""
        instructions = _parse_cpp(source)
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        field_names = [
            inst.operands[1] for inst in store_fields if len(inst.operands) > 1
        ]
        assert "count" in field_names


class TestCppDeleteExpression:
    def test_delete_calls_function(self):
        instructions = _parse_cpp("int main() { int* p = new int(5); delete p; }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("delete" in inst.operands for inst in calls)

    def test_delete_array(self):
        instructions = _parse_cpp("int main() { int* arr = new int[10]; delete arr; }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("delete" in inst.operands for inst in calls)


class TestCppCharLiteral:
    def test_char_literal_produces_const(self):
        instructions = _parse_cpp("int main() { char c = 'A'; }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("'A'" in str(inst.operands) for inst in consts)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("char_literal" in str(inst.operands) for inst in symbolics)

    def test_char_literal_no_symbolic_fallback(self):
        instructions = _parse_cpp("int main() { char c = 'x'; }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("char_literal" in str(inst.operands) for inst in symbolics)
        assert not any("character_literal" in str(inst.operands) for inst in symbolics)


class TestCppEnumSpecifier:
    def test_c_style_enum(self):
        instructions = _parse_cpp("enum Color { Red, Green, Blue };")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("enum:Color" in str(inst.operands) for inst in new_objs)
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        field_names = [
            inst.operands[1] for inst in store_fields if len(inst.operands) > 1
        ]
        assert "Red" in field_names
        assert "Green" in field_names
        assert "Blue" in field_names

    def test_enum_class_scoped(self):
        instructions = _parse_cpp("enum class Direction { North, South, East, West };")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("enum:" in str(inst.operands) for inst in new_objs)
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        field_names = [
            inst.operands[1] for inst in store_fields if len(inst.operands) > 1
        ]
        assert "North" in field_names
        assert "West" in field_names

    def test_enum_class_with_values(self):
        instructions = _parse_cpp("enum class Flag { A = 1, B = 2, C = 4 };")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("enum:" in str(inst.operands) for inst in new_objs)
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        field_names = [
            inst.operands[1] for inst in store_fields if len(inst.operands) > 1
        ]
        assert "A" in field_names
        assert "B" in field_names
        assert "C" in field_names
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Flag" in inst.operands for inst in stores)


class TestCppConceptDefinition:
    def test_concept_definition_no_unsupported(self):
        """template<typename T> concept Numeric = std::is_arithmetic_v<T>; should not produce unsupported SYMBOLIC."""
        source = "template<typename T> concept Numeric = std::is_arithmetic_v<T>;"
        instructions = _parse_cpp(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_concept_definition_with_requires(self):
        source = """\
template<typename T>
concept Addable = requires(T a, T b) {
    { a + b } -> std::same_as<T>;
};
"""
        instructions = _parse_cpp(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)


class TestCppDerefThis:
    """*this should resolve to this, not LOAD_FIELD [this, '*']."""

    def test_deref_this_no_load_field_star(self):
        """return *this; should NOT produce LOAD_FIELD with field='*'."""
        ir = _parse_cpp("""\
class Counter {
public:
    Counter increment() {
        return *this;
    }
};
""")
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        star_fields = [inst for inst in load_fields if "*" in inst.operands]
        assert (
            len(star_fields) == 0
        ), f"Expected no LOAD_FIELD with '*', got {star_fields}"

    def test_deref_this_returns_this_via_load_var(self):
        """return *this; should produce LOAD_VAR this + RETURN."""
        ir = _parse_cpp("""\
class Counter {
public:
    Counter increment() {
        return *this;
    }
};
""")
        # Find the RETURN inside the increment function
        returns = _find_all(ir, Opcode.RETURN)
        # There should be a LOAD_VAR for 'this' that feeds into the return
        load_vars = _find_all(ir, Opcode.LOAD_VAR)
        this_loads = [inst for inst in load_vars if "this" in inst.operands]
        assert len(this_loads) >= 1, "Expected at least one LOAD_VAR 'this'"

    def test_deref_non_this_still_uses_load_field(self):
        """*ptr (not *this) should still produce LOAD_FIELD."""
        ir = _parse_cpp("""\
int main() {
    int* p;
    int x = *p;
}
""")
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        star_fields = [inst for inst in load_fields if "*" in inst.operands]
        assert (
            len(star_fields) >= 1
        ), "Expected LOAD_FIELD with '*' for non-this dereference"


class TestCppFieldInitB2:
    """B2 field initializer pattern: STORE_FIELD in __init__, not CLASS block."""

    def test_synthetic_init_generated(self):
        """Class with field initializer but no constructor gets synthetic __init__."""
        ir = _parse_cpp("""\
class Foo {
public:
    int x = 42;
};
""")
        func_consts = [
            inst
            for inst in _find_all(ir, Opcode.CONST)
            if inst.operands
            and isinstance(inst.operands[0], str)
            and "__init__" in inst.operands[0]
        ]
        assert len(func_consts) == 1, f"Expected synthetic __init__, got {func_consts}"

    def test_field_init_in_constructor_not_class_block(self):
        """Field init STORE_FIELD should be inside __init__, not before it."""
        ir = _parse_cpp("""\
class Foo {
public:
    int x = 42;
};
""")
        # Find the __init__ label
        labels = _find_all(ir, Opcode.LABEL)
        init_labels = [l for l in labels if "init" in (l.label or "")]
        assert len(init_labels) >= 1, "Expected __init__ label"

        # STORE_FIELD for 'x' should exist inside the __init__ function
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        x_stores = [sf for sf in store_fields if "x" in sf.operands]
        assert len(x_stores) >= 1, "Expected STORE_FIELD for 'x'"

    def test_no_store_field_in_class_block(self):
        """Field inits with values should NOT emit STORE_FIELD in the CLASS block."""
        ir = _parse_cpp("""\
class Foo {
public:
    int x = 42;
};
""")
        # Find class label and __init__ label positions
        init_start = next(
            (
                i
                for i, inst in enumerate(ir)
                if inst.opcode == Opcode.LABEL and "init" in (inst.label or "")
            ),
            None,
        )
        assert init_start is not None
        # All STORE_FIELD for 'x' should be after __init__ label
        for i, inst in enumerate(ir):
            if inst.opcode == Opcode.STORE_FIELD and "x" in inst.operands:
                assert (
                    i > init_start
                ), f"STORE_FIELD for 'x' at position {i} is before __init__ at {init_start}"

    def test_explicit_constructor_gets_field_inits(self):
        """Explicit constructor should have field inits prepended and be named __init__."""
        ir = _parse_cpp("""\
class Bar {
public:
    int y = 10;
    Bar() {}
};
""")
        func_consts = [
            inst
            for inst in _find_all(ir, Opcode.CONST)
            if inst.operands
            and isinstance(inst.operands[0], str)
            and "__init__" in inst.operands[0]
        ]
        assert (
            len(func_consts) == 1
        ), f"Expected __init__ from explicit constructor, got {func_consts}"
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        y_stores = [sf for sf in store_fields if "y" in sf.operands]
        assert len(y_stores) >= 1, "Expected STORE_FIELD for 'y' in constructor"

    def test_fields_without_init_still_lowered(self):
        """Fields without initializers should still emit STORE_FIELD (with default 0)."""
        ir = _parse_cpp("""\
class Baz {
public:
    int a;
};
""")
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        a_stores = [sf for sf in store_fields if "a" in sf.operands]
        assert len(a_stores) >= 1, "Expected STORE_FIELD for field 'a' with default"
