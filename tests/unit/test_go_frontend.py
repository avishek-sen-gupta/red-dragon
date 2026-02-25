"""Tests for GoFrontend — tree-sitter Go AST -> IR lowering."""

from __future__ import annotations

import tree_sitter_language_pack

from interpreter.frontends.go import GoFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_and_lower(source: str) -> list[IRInstruction]:
    parser = tree_sitter_language_pack.get_parser("go")
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    frontend = GoFrontend()
    return frontend.lower(tree, source_bytes)


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestGoFrontendShortVarDecl:
    def test_short_var_decl_produces_const_and_store(self):
        ir = _parse_and_lower("package main; func main() { x := 10 }")
        opcodes = _opcodes(ir)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 1

    def test_short_var_decl_string_value(self):
        ir = _parse_and_lower('package main; func main() { name := "hello" }')
        stores = _find_all(ir, Opcode.STORE_VAR)
        name_stores = [s for s in stores if "name" in s.operands]
        assert len(name_stores) >= 1


class TestGoFrontendAssignment:
    def test_assignment_produces_store(self):
        source = "package main; func main() { x := 10; x = x + 5 }"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 2

    def test_assignment_with_binop(self):
        source = "package main; func main() { x := 10; x = x + 5 }"
        ir = _parse_and_lower(source)
        binops = _find_all(ir, Opcode.BINOP)
        assert len(binops) >= 1
        assert "+" in binops[0].operands


class TestGoFrontendFunctionDecl:
    def test_function_declaration_produces_label_and_return(self):
        source = "package main; func add(a int, b int) int { return a + b }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.LABEL in opcodes
        assert Opcode.RETURN in opcodes

    def test_function_params_lowered_as_symbolic(self):
        source = "package main; func add(a int, b int) int { return a + b }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        param_symbolics = [
            s for s in symbolics if any("param:" in str(op) for op in s.operands)
        ]
        assert len(param_symbolics) >= 2

    def test_function_name_stored(self):
        source = "package main; func add(a int, b int) int { return a + b }"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        add_stores = [s for s in stores if "add" in s.operands]
        assert len(add_stores) >= 1


class TestGoFrontendFunctionCall:
    def test_function_call_produces_call_function(self):
        source = "package main; func main() { add(1, 2) }"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        add_calls = [c for c in calls if "add" in c.operands]
        assert len(add_calls) >= 1


class TestGoFrontendIfElse:
    def test_if_produces_branch_if_and_labels(self):
        source = """package main
func main() {
    x := 10
    if x > 5 {
        x = 1
    } else {
        x = 2
    }
}"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        labels = _find_all(ir, Opcode.LABEL)
        assert len(labels) >= 3


class TestGoFrontendForLoop:
    def test_c_style_for_loop(self):
        source = """package main
func main() {
    for i := 0; i < 10; i++ {
        x := i
    }
}"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(ir, Opcode.LABEL)
        label_names = [lbl.label for lbl in labels]
        for_labels = [l for l in label_names if l and "for_" in l]
        assert len(for_labels) >= 2

    def test_condition_only_for_loop(self):
        source = """package main
func main() {
    x := 10
    for x > 0 {
        x = x - 1
    }
}"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes


class TestGoFrontendSelectorExpression:
    def test_field_access_produces_load_field(self):
        source = "package main; func main() { x := obj.field }"
        ir = _parse_and_lower(source)
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert len(load_fields) >= 1
        assert "field" in load_fields[0].operands


class TestGoFrontendMethodCall:
    def test_method_call_produces_call_method(self):
        source = 'package main; import "fmt"; func main() { fmt.Println("hello") }'
        ir = _parse_and_lower(source)
        method_calls = _find_all(ir, Opcode.CALL_METHOD)
        assert len(method_calls) >= 1
        assert "Println" in method_calls[0].operands


class TestGoFrontendStructDef:
    def test_struct_definition_produces_symbolic(self):
        source = """package main
type Point struct {
    X int
    Y int
}"""
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        struct_symbolics = [
            s for s in symbolics if any("struct:" in str(op) for op in s.operands)
        ]
        assert len(struct_symbolics) >= 1
        stores = _find_all(ir, Opcode.STORE_VAR)
        point_stores = [s for s in stores if "Point" in s.operands]
        assert len(point_stores) >= 1


class TestGoFrontendIncDec:
    def test_inc_statement(self):
        source = "package main; func main() { i := 0; i++ }"
        ir = _parse_and_lower(source)
        binops = _find_all(ir, Opcode.BINOP)
        plus_ops = [b for b in binops if "+" in b.operands]
        assert len(plus_ops) >= 1

    def test_dec_statement(self):
        source = "package main; func main() { i := 10; i-- }"
        ir = _parse_and_lower(source)
        binops = _find_all(ir, Opcode.BINOP)
        minus_ops = [b for b in binops if "-" in b.operands]
        assert len(minus_ops) >= 1


class TestGoFrontendReturn:
    def test_return_with_value(self):
        source = "package main; func f() int { return 42 }"
        ir = _parse_and_lower(source)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1

    def test_return_without_value(self):
        source = "package main; func f() { return }"
        ir = _parse_and_lower(source)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1


class TestGoFrontendMultipleReturn:
    def test_multiple_return_values(self):
        source = """package main
func swap(a int, b int) (int, int) {
    return b, a
}"""
        ir = _parse_and_lower(source)
        returns = _find_all(ir, Opcode.RETURN)
        # Multiple return values produce multiple RETURN instructions
        assert len(returns) >= 2


class TestGoFrontendFallback:
    def test_unsupported_construct_produces_symbolic(self):
        source = "package main; func main() { go func() {} () }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        # The go statement should produce SYMBOLIC as a fallback
        assert Opcode.SYMBOLIC in opcodes or Opcode.CALL_UNKNOWN in opcodes

    def test_entry_label_always_present(self):
        source = "package main"
        ir = _parse_and_lower(source)
        assert ir[0].opcode == Opcode.LABEL
        assert ir[0].label == "entry"


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialGo:
    def test_for_range_with_accumulator(self):
        source = """\
package main
func main() {
    items := []int{1, 2, 3, 4, 5}
    total := 0
    for i := 0; i < 5; i++ {
        if items[i] > 2 {
            total = total + items[i]
        }
    }
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("total" in s.operands for s in stores)
        assert len(ir) > 20

    def test_struct_method_with_receiver(self):
        source = """\
package main
type Counter struct {
    count int
}
func (c Counter) Value() int {
    return c.count
}
"""
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert any("struct:" in str(s.operands) for s in symbolics)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("Counter" in s.operands for s in stores)
        assert any("Value" in s.operands for s in stores)

    def test_multiple_return_values(self):
        source = """\
package main
func divide(a int, b int) (int, int) {
    return a / b, a % b
}
"""
        ir = _parse_and_lower(source)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 2
        binops = _find_all(ir, Opcode.BINOP)
        operators = [inst.operands[0] for inst in binops if inst.operands]
        assert "/" in operators
        assert "%" in operators

    def test_nested_for_with_field_access(self):
        source = """\
package main
func main() {
    total := 0
    for i := 0; i < 10; i++ {
        for j := 0; j < 10; j++ {
            total = total + obj.value
        }
    }
}
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert any("value" in inst.operands for inst in load_fields)
        assert len(ir) > 25

    def test_if_else_chain(self):
        source = """\
package main
func classify(x int) string {
    if x > 100 {
        return "high"
    } else if x > 50 {
        return "medium"
    } else {
        return "low"
    }
}
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 3

    def test_for_with_short_var_and_condition(self):
        source = """\
package main
func main() {
    sum := 0
    for i := 1; i <= 100; i++ {
        sum = sum + i
    }
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("sum" in s.operands for s in stores)
        assert any("i" in s.operands for s in stores)
        binops = _find_all(ir, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        labels = _labels_in_order(ir)
        assert any("for_" in lbl for lbl in labels)

    def test_function_calling_function(self):
        source = """\
package main
func double(x int) int {
    return x * 2
}
func quadruple(x int) int {
    return double(double(x))
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("double" in s.operands for s in stores)
        assert any("quadruple" in s.operands for s in stores)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("double" in inst.operands for inst in calls)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 2

    def test_defer_produces_symbolic(self):
        source = """\
package main
func main() {
    x := open()
    defer x.Close()
    x.Read()
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.SYMBOLIC in opcodes
        calls = _find_all(ir, Opcode.CALL_METHOD)
        assert any("Read" in inst.operands for inst in calls)
