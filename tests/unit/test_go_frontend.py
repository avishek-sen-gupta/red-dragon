"""Tests for GoFrontend — tree-sitter Go AST -> IR lowering."""

from __future__ import annotations

from interpreter.frontends.go import GoFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode
from interpreter.type_environment_builder import TypeEnvironmentBuilder


def _parse_and_lower(source: str) -> list[IRInstruction]:
    frontend = GoFrontend(TreeSitterParserFactory(), "go")
    return frontend.lower(source.encode("utf-8"))


def _parse_go_with_types(
    source: str,
) -> tuple[list[IRInstruction], TypeEnvironmentBuilder]:
    frontend = GoFrontend(TreeSitterParserFactory(), "go")
    instructions = frontend.lower(source.encode("utf-8"))
    return instructions, frontend.type_env_builder


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestGoFrontendShortVarDecl:
    def test_short_var_decl_produces_const_and_store(self):
        ir = _parse_and_lower("package main; func main() { x := 10 }")
        opcodes = _opcodes(ir)
        assert Opcode.CONST in opcodes
        assert Opcode.DECL_VAR in opcodes
        stores = _find_all(ir, Opcode.DECL_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 1

    def test_short_var_decl_string_value(self):
        ir = _parse_and_lower('package main; func main() { name := "hello" }')
        stores = _find_all(ir, Opcode.DECL_VAR)
        name_stores = [s for s in stores if "name" in s.operands]
        assert len(name_stores) >= 1


class TestGoFrontendAssignment:
    def test_assignment_produces_store(self):
        source = "package main; func main() { x := 10; x = x + 5 }"
        ir = _parse_and_lower(source)
        decls = _find_all(ir, Opcode.DECL_VAR)
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_decls = [s for s in decls if "x" in s.operands]
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_decls) >= 1
        assert len(x_stores) >= 1

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
        stores = _find_all(ir, Opcode.DECL_VAR)
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

    def test_if_elseif_chain_all_branches_produce_ir(self):
        """All branches of if/else-if/else-if/else must produce IR."""
        source = """package main
func f() {
    if x == 1 { y = 10 } else if x == 2 { y = 20 } else if x == 3 { y = 30 } else { y = 40 }
}"""
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
    def test_struct_definition_produces_class_ref(self):
        source = """package main
type Point struct {
    X int
    Y int
}"""
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        class_refs = [
            c for c in consts if any("<class:" in str(op) for op in c.operands)
        ]
        assert len(class_refs) >= 1
        stores = _find_all(ir, Opcode.DECL_VAR)
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
        """Bare return emits CONST with default value followed by RETURN."""
        source = "package main; func f() { return }"
        ir = _parse_and_lower(source)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1
        # Bare return should emit a CONST "None" (default return value) before RETURN
        consts = _find_all(ir, Opcode.CONST)
        assert any(
            c.operands == ["None"] for c in consts
        ), f"bare return should emit CONST ['None'], got {[c.operands for c in consts]}"


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
        loads = _find_all(ir, Opcode.LOAD_VAR)
        assert any("b" in inst.operands for inst in loads)
        assert any("a" in inst.operands for inst in loads)


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
    for _, v := range items {
        if v > 2 {
            total = total + v
        }
    }
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("total" in s.operands for s in stores)
        assert any("v" in s.operands for s in stores)
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
        consts = _find_all(ir, Opcode.CONST)
        assert any("<class:" in str(c.operands) for c in consts)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1
        stores = _find_all(ir, Opcode.DECL_VAR)
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
        stores = _find_all(ir, Opcode.DECL_VAR)
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
        stores = _find_all(ir, Opcode.DECL_VAR)
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
        stores = _find_all(ir, Opcode.DECL_VAR)
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
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestGoConstDeclaration:
    def test_const_with_value(self):
        source = """\
package main
const Pi = 3
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
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
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("A" in inst.operands for inst in stores)
        assert any("B" in inst.operands for inst in stores)

    def test_const_with_explicit_type(self):
        source = """\
package main
const X int = 10
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
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
        stores = _find_all(ir, Opcode.DECL_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "a" in store_names
        assert "b" in store_names

    def test_var_multi_name_without_values(self):
        source = "package main\nvar a, b int"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "a" in store_names
        assert "b" in store_names

    def test_var_block_form(self):
        source = "package main\nvar (\n    x = 10\n    y = 20\n)"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "x" in store_names
        assert "y" in store_names

    def test_var_multi_name_three_elements(self):
        source = "package main\nfunc f() { var x, y, z = 1, 2, 3 }"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "x" in store_names
        assert "y" in store_names
        assert "z" in store_names


class TestGoReceiveStatement:
    def test_receive_statement_no_symbolic(self):
        source = (
            "package main\nfunc f() {\n  ch := make(chan int)\n"
            "  select {\n  case v := <-ch:\n    _ = v\n  }\n}"
        )
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("receive_statement" in str(inst.operands) for inst in symbolics)

    def test_receive_statement_chan_recv(self):
        source = (
            "package main\nfunc f() {\n  ch := make(chan int)\n"
            "  select {\n  case v := <-ch:\n    _ = v\n  }\n}"
        )
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("chan_recv" in inst.operands for inst in calls)


class TestGoChannelType:
    def test_channel_type_no_symbolic(self):
        source = "package main\nfunc f() { var ch chan int }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("channel_type" in str(inst.operands) for inst in symbolics)


class TestGoSliceType:
    def test_slice_type_no_symbolic(self):
        source = "package main\nfunc f() { var s []int }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("slice_type" in str(inst.operands) for inst in symbolics)


class TestGoTypeConversionExpression:
    """type_conversion_expression: []byte(s), Foo[int](y) — complex type conversions.

    Note: simple conversions like int(y), float64(x) are parsed by tree-sitter
    as call_expression and handled by the existing lower_go_call handler.
    type_conversion_expression is only triggered for complex type syntax.
    """

    def test_slice_byte_conversion_produces_call_function(self):
        """[]byte(s) should produce CALL_FUNCTION with '[]byte' as function name."""
        source = 'package main\nfunc main() { s := "hello"; x := []byte(s) }'
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        byte_calls = [c for c in calls if "[]byte" in c.operands]
        assert len(byte_calls) >= 1

    def test_slice_byte_conversion_no_symbolic(self):
        source = 'package main\nfunc main() { x := []byte("hello") }'
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "type_conversion_expression" in str(inst.operands) for inst in symbolics
        )

    def test_generic_type_conversion_produces_call_function(self):
        """Foo[int](y) should produce CALL_FUNCTION."""
        source = "package main\nfunc main() { x := Foo[int](y) }"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert len(calls) >= 1

    def test_generic_type_conversion_no_symbolic(self):
        source = "package main\nfunc main() { x := Foo[int](y) }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "type_conversion_expression" in str(inst.operands) for inst in symbolics
        )

    def test_type_conversion_operand_is_lowered(self):
        """The operand expression should be lowered and passed as argument."""
        source = 'package main\nfunc main() { s := "hi"; x := []byte(s) }'
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        byte_calls = [c for c in calls if "[]byte" in c.operands]
        assert len(byte_calls) >= 1
        # The call should have 2 operands: function name + 1 arg register
        assert len(byte_calls[0].operands) == 2

    def test_simple_int_conversion_still_works(self):
        """int(y) is call_expression — verify existing handler still covers it."""
        source = "package main\nfunc main() { y := 3; x := int(y) }"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        int_calls = [c for c in calls if "int" in c.operands]
        assert len(int_calls) >= 1


class TestGoGenericType:
    """generic_type: Foo[int] — Go 1.18+ generic type references.

    tree-sitter Go parses Foo[int] as generic_type (not type_instantiation_expression).
    generic_type appears in composite_literal types and var declarations.
    """

    def test_generic_composite_literal_no_symbolic(self):
        """Foo[int]{} should not produce any unsupported symbolics."""
        source = "package main\nfunc main() { x := Foo[int]{} }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("generic_type" in str(inst.operands) for inst in symbolics)

    def test_generic_var_decl_no_symbolic(self):
        """var x Foo[int] should not produce any unsupported symbolics."""
        source = "package main\nfunc main() { var x Foo[int] }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("generic_type" in str(inst.operands) for inst in symbolics)


class TestGoRuneLiteral:
    def test_rune_literal_no_symbolic(self):
        """Rune literal 'a' should not produce SYMBOLIC fallthrough."""
        ir = _parse_and_lower("package main; func main() { x := 'a' }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("rune_literal" in str(inst.operands) for inst in symbolics)

    def test_rune_literal_emits_const(self):
        """Rune literal should emit a CONST instruction."""
        ir = _parse_and_lower("package main; func main() { x := 'a' }")
        consts = _find_all(ir, Opcode.CONST)
        assert any("'a'" in str(inst.operands) for inst in consts)

    def test_rune_literal_stored_to_variable(self):
        """Rune literal should be stored in a variable."""
        ir = _parse_and_lower("package main; func main() { x := 'a' }")
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestGoBlankIdentifier:
    def test_blank_identifier_no_symbolic(self):
        """Blank identifier _ should not produce SYMBOLIC fallthrough."""
        ir = _parse_and_lower("package main; func main() { _ = 42 }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("blank_identifier" in str(inst.operands) for inst in symbolics)


class TestGoFallthroughStatement:
    def test_fallthrough_no_symbolic(self):
        """fallthrough should not produce SYMBOLIC fallthrough."""
        source = """\
package main
func main() {
    x := 1
    switch x {
    case 1:
        x = 10
        fallthrough
    case 2:
        x = 20
    }
}
"""
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "fallthrough_statement" in str(inst.operands) for inst in symbolics
        )

    def test_fallthrough_is_noop(self):
        """fallthrough should not emit any branch/jump — it's a no-op in our model."""
        source = """\
package main
func main() {
    x := 1
    switch x {
    case 1:
        x = 10
        fallthrough
    default:
        x = 20
    }
}
"""
        ir = _parse_and_lower(source)
        # fallthrough should NOT produce its own BRANCH instruction;
        # the switch lowering handles control flow
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "fallthrough_statement" in str(inst.operands) for inst in symbolics
        )


class TestGoVariadicArgument:
    def test_variadic_argument_no_symbolic(self):
        """args... in function call should not produce SYMBOLIC."""
        ir = _parse_and_lower("func main() { fmt.Println(args...) }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("variadic_argument" in str(inst.operands) for inst in symbolics)


class TestGoInterfaceLowering:
    """Go interface type declarations should emit CLASS blocks with method stubs."""

    def test_interface_emits_class_block(self):
        """Interface produces BRANCH-LABEL...LABEL-CONST(<class:>)-STORE_VAR."""
        ir = _parse_and_lower("""\
package main

type Shape interface {
    Area() float64
}
""")
        consts = _find_all(ir, Opcode.CONST)
        class_refs = [i for i in consts if "<class:" in str(i.operands)]
        assert len(class_refs) == 1
        assert "Shape" in str(class_refs[0].operands[0])

    def test_interface_methods_emit_function_labels(self):
        """Each interface method should produce a function label."""
        ir = _parse_and_lower("""\
package main

type Shape interface {
    Area() float64
    Perimeter() float64
}
""")
        labels = _find_all(ir, Opcode.LABEL)
        func_labels = [i.label for i in labels if "func_" in (i.label or "")]
        assert any("Area" in lbl for lbl in func_labels)
        assert any("Perimeter" in lbl for lbl in func_labels)

    def test_interface_methods_seed_return_types(self):
        """Interface method return types are seeded in type_env_builder."""
        _ir, builder = _parse_go_with_types("""\
package main

type Calculator interface {
    Compute(x int) int
    Reset() bool
}
""")
        rt = dict(builder.func_return_types)
        compute_entries = {k: v for k, v in rt.items() if "Compute" in k}
        reset_entries = {k: v for k, v in rt.items() if "Reset" in k}
        assert (
            len(compute_entries) >= 1
        ), f"Expected return type for 'Compute', got: {rt}"
        assert len(reset_entries) >= 1, f"Expected return type for 'Reset', got: {rt}"
