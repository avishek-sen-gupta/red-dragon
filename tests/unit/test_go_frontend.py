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
    def test_go_statement_produces_call_function(self):
        source = "package main; func main() { go func() {} () }"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("go" in inst.operands for inst in calls)

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

    def test_defer_produces_call_function(self):
        source = """\
package main
func main() {
    x := open()
    defer x.Close()
    x.Read()
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("defer" in inst.operands for inst in calls)
        method_calls = _find_all(ir, Opcode.CALL_METHOD)
        assert any("Read" in inst.operands for inst in method_calls)


class TestGoCompositeLiteral:
    def test_composite_keyed(self):
        source = """\
package main
func main() { p := Point{X: 1, Y: 2} }
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_FIELD in opcodes
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        field_names = [
            inst.operands[1] for inst in store_fields if len(inst.operands) > 1
        ]
        assert "X" in field_names
        assert "Y" in field_names

    def test_composite_positional(self):
        source = """\
package main
func main() { nums := []int{1, 2, 3} }
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes
        store_indices = _find_all(ir, Opcode.STORE_INDEX)
        assert len(store_indices) >= 3


class TestGoTypeAssertionExpression:
    def test_type_assertion_produces_call_function(self):
        source = """\
package main
func main() {
    var i interface{} = "hello"
    s := i.(string)
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("type_assert" in inst.operands for inst in calls)

    def test_type_assertion_includes_type(self):
        source = """\
package main
func main() {
    var i interface{} = 42
    n := i.(int)
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        ta_calls = [c for c in calls if "type_assert" in c.operands]
        assert any("int" in str(inst.operands) for inst in ta_calls)


class TestGoSliceExpression:
    def test_slice_produces_call_function(self):
        source = """\
package main
func main() {
    a := []int{1, 2, 3, 4, 5}
    b := a[1:3]
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("slice" in inst.operands for inst in calls)

    def test_slice_with_indices(self):
        source = """\
package main
func main() {
    s := "hello"
    t := s[0:2]
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        slice_calls = [c for c in calls if "slice" in c.operands]
        assert len(slice_calls) >= 1

    def test_slice_without_end(self):
        source = """\
package main
func main() {
    a := []int{1, 2, 3}
    b := a[1:]
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("slice" in inst.operands for inst in calls)


class TestGoFuncLiteral:
    def test_func_literal_produces_function_ref(self):
        source = """\
package main
func main() {
    f := func(x int) int { return x * 2 }
}
"""
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        assert any("__anon" in str(inst.operands) for inst in consts)

    def test_func_literal_has_return(self):
        source = """\
package main
func main() {
    f := func() { return }
}
"""
        ir = _parse_and_lower(source)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1

    def test_func_literal_params_lowered(self):
        source = """\
package main
func main() {
    f := func(a int, b int) int { return a + b }
}
"""
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        param_symbolics = [
            s for s in symbolics if any("param:" in str(op) for op in s.operands)
        ]
        assert len(param_symbolics) >= 2


class TestGoDeferStatement:
    def test_defer_produces_defer_call(self):
        source = """\
package main
func main() {
    defer close()
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("defer" in inst.operands for inst in calls)

    def test_defer_method_call(self):
        source = """\
package main
func main() {
    x := open()
    defer x.Close()
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("defer" in inst.operands for inst in calls)


class TestGoGoStatement:
    def test_go_statement_produces_go_call(self):
        source = """\
package main
func main() {
    go doWork()
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("go" in inst.operands for inst in calls)

    def test_go_with_func_literal(self):
        source = """\
package main
func main() {
    go func() { doSomething() }()
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("go" in inst.operands for inst in calls)


class TestGoExpressionSwitch:
    def test_switch_produces_branch_if(self):
        source = """\
package main
func main() {
    x := 1
    switch x {
    case 1:
        y := 10
    case 2:
        y := 20
    default:
        y := 0
    }
}
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 2

    def test_switch_case_bodies_lowered(self):
        source = """\
package main
func main() {
    switch x {
    case 1:
        result := "one"
    case 2:
        result := "two"
    }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)

    def test_switch_end_label(self):
        source = """\
package main
func main() {
    switch x {
    case 1:
        y := 1
    }
}
"""
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("switch_end" in lbl for lbl in labels)


class TestGoTypeSwitchStatement:
    def test_type_switch_produces_type_check(self):
        source = """\
package main
func main() {
    var i interface{} = "hello"
    switch i.(type) {
    case string:
        x := "is string"
    case int:
        x := "is int"
    }
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("type_check" in inst.operands for inst in calls)

    def test_type_switch_produces_branches(self):
        source = """\
package main
func main() {
    switch v.(type) {
    case int:
        x := 1
    case string:
        x := 2
    }
}
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 2


class TestGoSelectStatement:
    def test_select_produces_labels(self):
        source = """\
package main
func main() {
    select {
    case msg := <-ch:
        x := msg
    default:
        y := 0
    }
}
"""
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("select" in lbl for lbl in labels)

    def test_select_end_label(self):
        source = """\
package main
func main() {
    select {
    default:
        x := 1
    }
}
"""
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("select_end" in lbl for lbl in labels)


class TestGoSendStatement:
    def test_send_produces_chan_send(self):
        source = """\
package main
func main() {
    ch <- 42
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("chan_send" in inst.operands for inst in calls)

    def test_send_with_variable(self):
        source = """\
package main
func main() {
    ch <- msg
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("chan_send" in inst.operands for inst in calls)


class TestGoLabeledStatement:
    def test_labeled_statement_produces_label(self):
        source = """\
package main
func main() {
    outer:
    for i := 0; i < 10; i++ {
        x := i
    }
}
"""
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("outer" in lbl for lbl in labels)

    def test_labeled_statement_body_lowered(self):
        source = """\
package main
func main() {
    myLabel:
    x := 42
}
"""
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("myLabel" in lbl for lbl in labels)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestGoConstDeclaration:
    def test_const_with_value(self):
        source = """\
package main
const Pi = 3
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("Pi" in inst.operands for inst in stores)

    def test_const_multiple(self):
        source = """\
package main
const (
    A = 1
    B = 2
)
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("A" in inst.operands for inst in stores)
        assert any("B" in inst.operands for inst in stores)

    def test_const_without_value(self):
        source = """\
package main
const X int = 10
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("X" in inst.operands for inst in stores)


class TestGoGotoStatement:
    def test_goto_produces_branch(self):
        source = """\
package main
func main() {
    goto end
    end:
    x := 1
}
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH)
        assert any(inst.label == "end" for inst in branches)

    def test_goto_with_label(self):
        source = """\
package main
func main() {
    goto myLabel
    myLabel:
    y := 2
}
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH)
        assert any(inst.label == "myLabel" for inst in branches)


class TestGoVarDeclarationMultiName:
    def test_var_multi_name_with_values(self):
        source = "package main\nvar a, b = 1, 2"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "a" in store_names
        assert "b" in store_names

    def test_var_multi_name_without_values(self):
        source = "package main\nvar a, b int"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "a" in store_names
        assert "b" in store_names

    def test_var_block_form(self):
        source = "package main\nvar (\n    x = 10\n    y = 20\n)"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "x" in store_names
        assert "y" in store_names

    def test_var_multi_name_three_elements(self):
        source = "package main\nfunc f() { var x, y, z = 1, 2, 3 }"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "x" in store_names
        assert "y" in store_names
        assert "z" in store_names
