"""Tests for JavaScriptFrontend — tree-sitter JavaScript AST to IR lowering."""

from __future__ import annotations

from interpreter.frontends.javascript import JavaScriptFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode, SpreadArguments
from tests.unit.rosetta.conftest import execute_for_language, extract_answer


def _parse_js(source: str) -> list[IRInstruction]:
    frontend = JavaScriptFrontend(TreeSitterParserFactory(), "javascript")
    return frontend.lower(source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestJavaScriptSmoke:
    def test_empty_program(self):
        instructions = _parse_js("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_number_literal(self):
        instructions = _parse_js("42;")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)


class TestJavaScriptExpressions:
    def test_variable_assignment(self):
        instructions = _parse_js("let x = 10;")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.DECL_VAR in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_arithmetic_expression(self):
        instructions = _parse_js("let y = x + 5;")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.CONST in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.DECL_VAR in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_ternary_expression(self):
        instructions = _parse_js('let y = x > 0 ? "pos" : "neg";')
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.DECL_VAR in opcodes

    def test_template_literal(self):
        instructions = _parse_js("const s = `hello`;")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("`hello`" in inst.operands for inst in consts)


class TestJavaScriptControlFlow:
    def test_if_else(self):
        instructions = _parse_js("if (x > 5) { y = 1; } else { y = 0; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        assert Opcode.BRANCH in opcodes

    def test_while_loop(self):
        instructions = _parse_js("while (x > 0) { x--; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any(inst.label.contains("while") for inst in labels)

    def test_for_loop(self):
        instructions = _parse_js("for (let i = 0; i < 10; i++) { x = x + i; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("i" in inst.operands for inst in stores)

    def test_for_in_loop(self):
        instructions = _parse_js("for (let k in obj) { x = k; }")
        opcodes = _opcodes(instructions)
        assert Opcode.CALL_FUNCTION in opcodes
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("keys" in inst.operands for inst in calls)
        assert Opcode.BRANCH_IF in opcodes

    def test_if_elseif_chain_all_branches_produce_ir(self):
        """All branches of if/else-if/else-if/else must produce IR."""
        instructions = _parse_js(
            "if (x===1) { y=10; }"
            " else if (x===2) { y=20; }"
            " else if (x===3) { y=30; }"
            " else { y=40; }"
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
            target for inst in branch_ifs for target in inst.branch_targets
        }
        label_set = set(labels)
        assert branch_targets.issubset(
            label_set
        ), f"Unreachable targets: {branch_targets - label_set}"


class TestJavaScriptFunctions:
    def test_function_declaration(self):
        instructions = _parse_js("function add(a, b) { return a + b; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        assert Opcode.RETURN in opcodes
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("a" in p for p in param_names)
        assert any("b" in p for p in param_names)

    def test_function_call(self):
        instructions = _parse_js("add(1, 2);")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) == 1
        assert "add" in calls[0].operands

    def test_arrow_function(self):
        instructions = _parse_js("const f = (a, b) => a + b;")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("f" in inst.operands for inst in stores)

    def test_method_call(self):
        instructions = _parse_js('console.log("hello");')
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1
        assert "log" in calls[0].operands


class TestJavaScriptClasses:
    def test_class_definition(self):
        instructions = _parse_js(
            'class Dog { constructor(n) { this.name = n; } bark() { return "woof"; } }'
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)


class TestJavaScriptLiterals:
    def test_object_literal(self):
        instructions = _parse_js("const obj = {a: 1, b: 2};")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes

    def test_array_literal(self):
        instructions = _parse_js("const arr = [1, 2, 3];")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.STORE_INDEX in opcodes


class TestJavaScriptSpecial:
    def test_throw_statement(self):
        instructions = _parse_js('throw new Error("fail");')
        opcodes = _opcodes(instructions)
        assert Opcode.THROW in opcodes

    def test_update_expression_decrement(self):
        instructions = _parse_js("x--;")
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("-" in inst.operands for inst in binops)

    def test_update_expression_increment(self):
        instructions = _parse_js("x++;")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_fallback_symbolic(self):
        instructions = _parse_js("debugger;")
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("unsupported:" in str(inst.operands) for inst in symbolics)


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [str(inst.label) for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialJavaScript:
    def test_arrow_function_in_method_call(self):
        source = "const doubled = items.map((x) => x * 2);"
        instructions = _parse_js(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("map" in inst.operands for inst in calls)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("*" in inst.operands for inst in binops)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("doubled" in inst.operands for inst in stores)

    def test_for_of_loop_with_method_body(self):
        source = """\
for (const item of items) {
    console.log(item);
    result.push(item);
}
"""
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LOAD_INDEX in opcodes
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        assert "log" in method_names
        assert "push" in method_names
        assert len(instructions) > 10

    def test_nested_ternary(self):
        source = 'const label = x > 100 ? "high" : x > 50 ? "mid" : "low";'
        instructions = _parse_js(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("label" in inst.operands for inst in stores)

    def test_class_with_constructor_and_methods(self):
        source = """\
class Counter {
    constructor(start) {
        this.count = start;
    }
    increment() {
        this.count = this.count + 1;
    }
    get() {
        return this.count;
    }
}
"""
        instructions = _parse_js(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Counter" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("count" in inst.operands for inst in store_fields)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1
        assert len(instructions) > 20

    def test_for_loop_building_array(self):
        source = """\
const result = [];
for (let i = 0; i < 10; i++) {
    result.push(i * 2);
}
"""
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.NEW_ARRAY in opcodes
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("push" in inst.operands for inst in calls)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("*" in inst.operands for inst in binops)
        assert len(instructions) > 15

    def test_if_else_chain_with_early_return(self):
        source = """\
function classify(x) {
    if (x > 100) {
        return "high";
    } else if (x > 50) {
        return "medium";
    } else {
        return "low";
    }
}
"""
        instructions = _parse_js(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 3
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("classify" in inst.operands for inst in stores)

    def test_template_literal_with_expressions(self):
        source = """\
const name = "world";
const count = 5;
const msg = `Hello ${name}, you have ${count} items`;
"""
        instructions = _parse_js(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("name" in inst.operands for inst in stores)
        assert any("count" in inst.operands for inst in stores)
        assert any("msg" in inst.operands for inst in stores)

    def test_while_with_object_mutation(self):
        source = """\
let i = 0;
while (i < 10) {
    obj.value = obj.value + i;
    i++;
}
"""
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("value" in inst.operands for inst in store_fields)
        labels = _labels_in_order(instructions)
        assert any("while" in lbl for lbl in labels)
        assert len(instructions) > 15

    def test_try_catch_with_throw(self):
        source = """\
try {
    const result = riskyOp();
    console.log(result);
} catch (e) {
    throw new Error("wrapped: " + e.message);
}
"""
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        labels = [str(i.label) for i in instructions if i.opcode == Opcode.LABEL]
        # try/catch body and catch block are lowered with LABEL/BRANCH
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_end" in l for l in labels)
        assert Opcode.THROW in opcodes
        # No catch_clause: SYMBOLIC placeholders
        symbolics = [i for i in instructions if i.opcode == Opcode.SYMBOLIC]
        assert not any("catch_clause:" in str(s.operands) for s in symbolics)
        assert len(instructions) > 10

    def test_object_literal_with_method_calls(self):
        source = """\
const config = {name: "app", version: 1};
const upper = config.name.toUpperCase();
"""
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("toUpperCase" in inst.operands for inst in calls)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("config" in inst.operands for inst in stores)
        assert any("upper" in inst.operands for inst in stores)


class TestJavaScriptForOf:
    def test_for_of_basic(self):
        """for...of should produce index-based IR (LOAD_INDEX, not SYMBOLIC)."""
        source = "for (const x of items) { y = x; }"
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_INDEX in opcodes
        assert Opcode.CALL_FUNCTION in opcodes  # len()
        labels = _labels_in_order(instructions)
        assert any("for_of" in lbl for lbl in labels)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_for_of_with_break(self):
        source = """\
for (const x of items) {
    if (x > 10) break;
}
"""
        instructions = _parse_js(source)
        labels = _labels_in_order(instructions)
        assert any("for_of_end" in lbl for lbl in labels)
        branches = _find_all(instructions, Opcode.BRANCH)
        end_labels = [lbl for lbl in labels if "for_of_end" in lbl]
        assert any(b.label in end_labels for b in branches)

    def test_for_in_basic(self):
        """for...in should emit CALL_FUNCTION keys + index-based loop."""
        source = "for (let k in obj) { x = k; }"
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        assert Opcode.CALL_FUNCTION in opcodes
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("keys" in inst.operands for inst in calls)
        assert Opcode.LOAD_INDEX in opcodes
        labels = _labels_in_order(instructions)
        assert any("for_in" in lbl for lbl in labels)

    def test_for_in_with_body(self):
        """for...in loop body is lowered."""
        source = "for (let k in obj) { console.log(k); }"
        instructions = _parse_js(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("log" in inst.operands for inst in calls)

    def test_for_in_with_break(self):
        """for...in supports break."""
        source = "for (let k in obj) { if (k === 'x') break; }"
        instructions = _parse_js(source)
        labels = _labels_in_order(instructions)
        assert any("for_in_end" in lbl for lbl in labels)


class TestJavaScriptDestructuring:
    def test_obj_destructure_basic(self):
        source = "const { a, b } = obj;"
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_FIELD in opcodes
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        field_names = [inst.operands[1] for inst in loads if len(inst.operands) > 1]
        assert "a" in field_names
        assert "b" in field_names
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("a" in inst.operands for inst in stores)
        assert any("b" in inst.operands for inst in stores)

    def test_obj_destructure_rename(self):
        source = "const { x: localX, y: localY } = obj;"
        instructions = _parse_js(source)
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        field_names = [inst.operands[1] for inst in loads if len(inst.operands) > 1]
        assert "x" in field_names
        assert "y" in field_names
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("localX" in inst.operands for inst in stores)
        assert any("localY" in inst.operands for inst in stores)

    def test_arr_destructure_basic(self):
        source = "const [a, b] = arr;"
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_INDEX in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("a" in inst.operands for inst in stores)
        assert any("b" in inst.operands for inst in stores)

    def test_arr_destructure_three(self):
        source = "const [x, y, z] = arr;"
        instructions = _parse_js(source)
        loads = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(loads) >= 3
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)
        assert any("y" in inst.operands for inst in stores)
        assert any("z" in inst.operands for inst in stores)

    def test_arr_destructure_rest(self):
        """const [first, ...rest] = arr; should LOAD_INDEX first, then slice for rest."""
        source = "const [first, ...rest] = arr;"
        instructions = _parse_js(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "first" in store_names, f"expected 'first' in stores, got {store_names}"
        assert "rest" in store_names, f"expected 'rest' in stores, got {store_names}"
        # 'rest' should NOT have '...' prefix
        assert "...rest" not in store_names, "rest var should not include '...' prefix"
        # Should have a slice call for the rest
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any(
            "slice" in inst.operands for inst in calls
        ), f"expected slice call, got {[inst.operands for inst in calls]}"

    def test_arr_destructure_rest_middle_elements(self):
        """const [a, b, ...rest] = arr; — rest starts at index 2."""
        source = "const [a, b, ...rest] = arr;"
        instructions = _parse_js(source)
        loads = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(loads) >= 2, "should LOAD_INDEX for a and b"
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        slice_calls = [inst for inst in calls if "slice" in inst.operands]
        assert len(slice_calls) == 1, f"expected 1 slice call, got {len(slice_calls)}"
        stores = _find_all(instructions, Opcode.DECL_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "a" in store_names
        assert "b" in store_names
        assert "rest" in store_names

    def test_obj_destructure_rest(self):
        """const {a, ...rest} = obj; should LOAD_FIELD a, then object_rest for rest."""
        source = "const {a, ...rest} = obj;"
        instructions = _parse_js(source)
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        field_names = [inst.operands[1] for inst in loads if len(inst.operands) > 1]
        assert "a" in field_names
        stores = _find_all(instructions, Opcode.DECL_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "rest" in store_names
        assert "...rest" not in store_names
        # Should have an object_rest call
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any(
            "object_rest" in inst.operands for inst in calls
        ), f"expected object_rest call, got {[inst.operands for inst in calls]}"

    def test_obj_destructure_rest_with_rename(self):
        """const {x: localX, ...rest} = obj; — renamed + rest."""
        source = "const {x: localX, ...rest} = obj;"
        instructions = _parse_js(source)
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        field_names = [inst.operands[1] for inst in loads if len(inst.operands) > 1]
        assert "x" in field_names
        stores = _find_all(instructions, Opcode.DECL_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "localX" in store_names
        assert "rest" in store_names


class TestJavaScriptRestParameter:
    def test_rest_param_emits_slice(self):
        """function foo(a, ...rest) {} should emit slice(arguments, 1) for rest."""
        source = "function foo(a, ...rest) { return rest; }"
        instructions = _parse_js(source)
        # Should have SYMBOLIC param:a but NOT param:rest
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        sym_names = [inst.operands[0] for inst in symbolics]
        assert "param:a" in sym_names
        assert "param:rest" not in sym_names, "rest should not be a regular param"
        # Should have slice call for rest
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any(
            "slice" in inst.operands for inst in calls
        ), f"expected slice call, got {[inst.operands for inst in calls]}"
        # Should store as 'rest'
        stores = _find_all(instructions, Opcode.DECL_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "rest" in store_names

    def test_rest_param_only(self):
        """function foo(...args) {} should slice from index 0."""
        source = "function foo(...args) { return args; }"
        instructions = _parse_js(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        slice_calls = [inst for inst in calls if "slice" in inst.operands]
        assert len(slice_calls) == 1
        # The start index should be 0 (no preceding params)
        consts = _find_all(instructions, Opcode.CONST)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("args" in inst.operands for inst in stores)

    def test_rest_param_loads_arguments(self):
        """Rest param should emit LOAD_VAR arguments."""
        source = "function foo(x, y, ...rest) {}"
        instructions = _parse_js(source)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        load_names = [inst.operands[0] for inst in loads]
        assert (
            "arguments" in load_names
        ), f"expected LOAD_VAR arguments, got {load_names}"


class TestJavaScriptUsingDeclaration:
    """using x = expr should lower identically to const x = expr."""

    def test_using_simple_assignment(self):
        """using file = openFile() should emit CALL_FUNCTION + STORE_VAR."""
        source = "using file = openFile();"
        instructions = _parse_js(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any(
            "openFile" in inst.operands for inst in calls
        ), f"expected openFile call, got {[inst.operands for inst in calls]}"
        stores = _find_all(instructions, Opcode.DECL_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "file" in store_names, f"expected STORE_VAR file, got {store_names}"

    def test_using_produces_same_ir_as_const(self):
        """using x = expr and const x = expr should produce equivalent IR."""
        using_ir = _parse_js("using res = getResource();")
        const_ir = _parse_js("const res = getResource();")
        using_ops = _opcodes(using_ir)
        const_ops = _opcodes(const_ir)
        assert using_ops == const_ops, (
            f"using and const should produce same opcodes:\n"
            f"  using: {using_ops}\n  const: {const_ops}"
        )

    def test_using_with_destructuring(self):
        """using with object destructuring should work like const."""
        source = "using {conn, pool} = createPool();"
        instructions = _parse_js(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "conn" in store_names
        assert "pool" in store_names


class TestJavaScriptNewExpression:
    def test_new_expression_basic(self):
        instructions = _parse_js("const obj = new Foo();")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("Foo" in inst.operands for inst in new_objs)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("constructor" in inst.operands for inst in calls)

    def test_new_expression_with_args(self):
        instructions = _parse_js("const obj = new Dog(name, age);")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("Dog" in inst.operands for inst in new_objs)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("constructor" in inst.operands for inst in calls)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("obj" in inst.operands for inst in stores)
        # Args should be loaded
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("name" in inst.operands for inst in loads)
        assert any("age" in inst.operands for inst in loads)

    def test_new_expression_in_throw(self):
        instructions = _parse_js('throw new Error("fail");')
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.THROW in opcodes


class TestJavaScriptAwaitExpression:
    def test_await_basic(self):
        instructions = _parse_js("const result = await fetch(url);")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("await" in inst.operands for inst in calls)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("result" in inst.operands for inst in stores)

    def test_await_in_assignment(self):
        instructions = _parse_js("const data = await response.json();")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("await" in inst.operands for inst in calls)

    def test_await_nested(self):
        instructions = _parse_js("const x = await (await fetch(url)).json();")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        await_calls = [c for c in calls if "await" in c.operands]
        assert len(await_calls) >= 2


class TestJavaScriptYieldExpression:
    def test_yield_with_value(self):
        instructions = _parse_js("function* gen() { yield 42; }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("yield" in inst.operands for inst in calls)

    def test_bare_yield(self):
        instructions = _parse_js("function* gen() { yield; }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("yield" in inst.operands for inst in calls)

    def test_yield_with_expression(self):
        instructions = _parse_js("function* gen() { const x = yield getValue(); }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("yield" in inst.operands for inst in calls)


class TestJavaScriptRegex:
    def test_regex_literal(self):
        instructions = _parse_js("const r = /abc/gi;")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("/abc/gi" in inst.operands for inst in consts)

    def test_regex_in_condition(self):
        instructions = _parse_js("if (/test/.test(str)) { x = 1; }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("/test/" in inst.operands for inst in consts)


class TestJavaScriptSequenceExpression:
    def test_sequence_basic(self):
        instructions = _parse_js("const x = (1, 2, 3);")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("1" in inst.operands for inst in consts)
        assert any("2" in inst.operands for inst in consts)
        assert any("3" in inst.operands for inst in consts)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_sequence_with_side_effects(self):
        instructions = _parse_js("const x = (a++, b++, c);")
        binops = _find_all(instructions, Opcode.BINOP)
        assert len(binops) >= 2
        # Side effects: a++ and b++ should produce STORE_VAR back to a and b
        stores = _find_all(instructions, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores if inst.operands]
        assert "a" in store_names
        assert "b" in store_names


class TestJavaScriptSpreadElement:
    def test_spread_in_call(self):
        instructions = _parse_js("foo(...args);")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any(
            any(isinstance(op, SpreadArguments) for op in inst.operands)
            for inst in calls
        )

    def test_spread_in_array(self):
        instructions = _parse_js("const arr = [...items, 4, 5];")
        spread_ops = [
            op
            for inst in instructions
            for op in inst.operands
            if isinstance(op, SpreadArguments)
        ]
        assert len(spread_ops) >= 1

    def test_spread_multiple(self):
        instructions = _parse_js("foo(...a, ...b);")
        spread_ops = [
            op
            for inst in instructions
            for op in inst.operands
            if isinstance(op, SpreadArguments)
        ]
        assert len(spread_ops) >= 2


class TestJavaScriptFunctionExpression:
    def test_anonymous_function(self):
        instructions = _parse_js("const f = function(x) { return x + 1; };")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            str(inst.operands[0]).startswith("func_")
            for inst in consts
            if inst.operands
        )
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("f" in inst.operands for inst in stores)

    def test_named_function_expression(self):
        instructions = _parse_js("const f = function myFunc(x) { return x; };")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            str(inst.operands[0]).startswith("func_")
            for inst in consts
            if inst.operands
        )
        assert any("myFunc" in str(inst.operands) for inst in consts)

    def test_function_expression_as_callback(self):
        instructions = _parse_js("arr.forEach(function(item) { process(item); });")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("forEach" in inst.operands for inst in calls)
        # Function expression should be lowered as a CONST with function reference
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            str(inst.operands[0]).startswith("func_")
            for inst in consts
            if inst.operands
        )


class TestJavaScriptSuperExpression:
    def test_super_call(self):
        source = """\
class Dog extends Animal {
    constructor(name) {
        super(name);
    }
}
"""
        instructions = _parse_js(source)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("super" in inst.operands for inst in loads)

    def test_super_method_call(self):
        source = """\
class Dog extends Animal {
    speak() {
        return super.speak() + " woof";
    }
}
"""
        instructions = _parse_js(source)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("super" in inst.operands for inst in loads)


class TestJavaScriptSwitchStatement:
    def test_switch_basic(self):
        source = """\
switch (x) {
    case 1:
        y = "one";
        break;
    case 2:
        y = "two";
        break;
    default:
        y = "other";
}
"""
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("===" in inst.operands for inst in binops)
        labels = _labels_in_order(instructions)
        assert any("switch_end" in lbl for lbl in labels)

    def test_switch_with_expressions(self):
        source = """\
switch (status) {
    case "active":
        process();
        break;
    default:
        skip();
}
"""
        instructions = _parse_js(source)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("===" in inst.operands for inst in binops)

    def test_switch_break_targets(self):
        source = """\
switch (x) {
    case 1:
        break;
    case 2:
        break;
}
"""
        instructions = _parse_js(source)
        branches = _find_all(instructions, Opcode.BRANCH)
        labels = _labels_in_order(instructions)
        end_labels = [lbl for lbl in labels if "switch_end" in lbl]
        assert len(end_labels) >= 1
        assert any(b.label in end_labels for b in branches)


class TestJavaScriptDoWhileStatement:
    def test_do_while_basic(self):
        source = "do { x++; } while (x < 10);"
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        labels = _labels_in_order(instructions)
        assert any("do_body" in lbl for lbl in labels)
        assert any("do_cond" in lbl for lbl in labels)
        assert any("do_end" in lbl for lbl in labels)

    def test_do_while_with_break(self):
        source = "do { if (x > 5) break; x++; } while (true);"
        instructions = _parse_js(source)
        labels = _labels_in_order(instructions)
        end_labels = [lbl for lbl in labels if "do_end" in lbl]
        assert len(end_labels) >= 1
        branches = _find_all(instructions, Opcode.BRANCH)
        assert any(b.label in end_labels for b in branches)

    def test_do_while_with_continue(self):
        source = "do { if (x > 5) continue; x++; } while (x < 10);"
        instructions = _parse_js(source)
        labels = _labels_in_order(instructions)
        cond_labels = [lbl for lbl in labels if "do_cond" in lbl]
        assert len(cond_labels) >= 1
        branches = _find_all(instructions, Opcode.BRANCH)
        assert any(b.label in cond_labels for b in branches)


class TestJavaScriptLabeledStatement:
    def test_labeled_statement_basic(self):
        source = "outer: for (let i = 0; i < 10; i++) { x = i; }"
        instructions = _parse_js(source)
        labels = _labels_in_order(instructions)
        assert any("outer" in lbl for lbl in labels)

    def test_labeled_statement_with_block(self):
        source = "myLabel: { x = 1; y = 2; }"
        instructions = _parse_js(source)
        labels = _labels_in_order(instructions)
        assert any("myLabel" in lbl for lbl in labels)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        assert any("y" in inst.operands for inst in stores)


class TestJavaScriptTemplateSubstitution:
    def test_template_with_substitution(self):
        source = "const msg = `Hello ${name}!`;"
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("msg" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_template_multiple_substitutions(self):
        source = "const msg = `${a} and ${b}`;"
        instructions = _parse_js(source)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        load_names = [inst.operands[0] for inst in loads if inst.operands]
        assert "a" in load_names
        assert "b" in load_names
        binops = _find_all(instructions, Opcode.BINOP)
        assert len(binops) >= 2

    def test_template_no_substitution(self):
        source = "const msg = `plain text`;"
        instructions = _parse_js(source)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("`plain text`" in inst.operands for inst in consts)


class TestJavaScriptClassStaticBlock:
    def test_class_static_block(self):
        source = """\
class Foo {
    static {
        Foo.count = 0;
    }
    constructor() {
        Foo.count++;
    }
}
"""
        instructions = _parse_js(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Foo" in inst.operands for inst in stores)
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("count" in inst.operands for inst in store_fields)

    def test_class_static_block_with_logic(self):
        source = """\
class Config {
    static {
        if (env === "prod") {
            Config.debug = false;
        }
    }
}
"""
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Config" in inst.operands for inst in stores)


class TestJavaScriptImportStatement:
    def test_import_default_is_noop(self):
        instructions = _parse_js('import foo from "bar";')
        # Should not crash; import is a no-op
        assert instructions[0].opcode == Opcode.LABEL

    def test_import_named_is_noop(self):
        instructions = _parse_js('import { a, b } from "module";')
        assert instructions[0].opcode == Opcode.LABEL
        # No SYMBOLIC for the import itself
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("import" in str(inst.operands) for inst in symbolics)

    def test_import_star_is_noop(self):
        instructions = _parse_js('import * as utils from "./utils";')
        assert instructions[0].opcode == Opcode.LABEL


class TestJavaScriptExportStatement:
    def test_export_function_declaration(self):
        instructions = _parse_js("export function add(a, b) { return a + b; }")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("add" in inst.operands for inst in stores)

    def test_export_variable_declaration(self):
        instructions = _parse_js("export const x = 42;")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)

    def test_export_class_declaration(self):
        instructions = _parse_js("export class Foo { constructor() {} }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Foo" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)


class TestJavaScriptOperatorExecution:
    """VM execution tests for JavaScript-specific operators."""

    def test_strict_equality_in_switch(self):
        source = """\
function classify(x) {
    switch(x) {
        case 1: return "one";
        case 2: return "two";
        default: return "other";
    }
}

let answer = classify(2);
"""
        vm, stats = execute_for_language("javascript", source)
        assert extract_answer(vm, "javascript") == "two"
        assert stats.llm_calls == 0

    def test_strict_equality_switch_default(self):
        source = """\
function classify(x) {
    switch(x) {
        case 1: return "one";
        case 2: return "two";
        default: return "other";
    }
}

let answer = classify(99);
"""
        vm, stats = execute_for_language("javascript", source)
        assert extract_answer(vm, "javascript") == "other"
        assert stats.llm_calls == 0


class TestJSStringFragment:
    def test_string_fragment_no_symbolic(self):
        source = "let x = `hello ${name} world`;"
        ir = _parse_js(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("string_fragment" in str(inst.operands) for inst in symbolics)

    def test_string_fragment_as_const(self):
        source = "let x = `prefix ${y}`;"
        ir = _parse_js(source)
        consts = _find_all(ir, Opcode.CONST)
        assert any("prefix " in str(inst.operands) for inst in consts)


class TestJavaScriptExportClause:
    def test_export_clause_no_unsupported(self):
        """export { a, b } from './module' should not produce unsupported SYMBOLIC."""
        source = 'export { a, b } from "./module";'
        instructions = _parse_js(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_export_clause_basic(self):
        source = 'export { foo, bar } from "./lib";'
        instructions = _parse_js(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)


class TestJavaScriptFieldDefinition:
    def test_private_field_no_unsupported(self):
        """Class with #privateField = 0 should not produce unsupported SYMBOLIC."""
        source = """\
class Foo {
    #privateField = 0;
    constructor() {
        this.#privateField = 1;
    }
}
"""
        instructions = _parse_js(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_field_definition_stores(self):
        source = """\
class Bar {
    count = 42;
}
"""
        instructions = _parse_js(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("count" in inst.operands for inst in stores)


class TestJavaScriptWithStatement:
    def test_with_statement_no_unsupported(self):
        """with (obj) { foo(); } should not produce unsupported SYMBOLIC."""
        source = "with (obj) { foo(); }"
        instructions = _parse_js(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)


class TestJSMetaProperty:
    def test_meta_property_no_symbolic(self):
        """new.target should not produce SYMBOLIC fallthrough."""
        frontend = JavaScriptFrontend(TreeSitterParserFactory(), "javascript")
        ir = frontend.lower(b"let x = new.target;")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("meta_property" in str(inst.operands) for inst in symbolics)

    def test_meta_property_stores_value(self):
        """new.target should be stored as a const."""
        frontend = JavaScriptFrontend(TreeSitterParserFactory(), "javascript")
        ir = frontend.lower(b"let x = new.target;")
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestJavaScriptForLoopUpdate:
    """C-style for-loop update expression must be lowered correctly."""

    def test_for_loop_update_produces_correct_result(self):
        """for (let i = 0; i < 5; i = i + 1) should terminate and sum correctly."""
        vm, stats = execute_for_language(
            "javascript",
            """\
let answer = 0;
for (let i = 0; i < 5; i = i + 1) {
    answer = answer + i;
}
""",
        )
        assert extract_answer(vm, "javascript") == 10
        assert stats.llm_calls == 0

    def test_for_loop_update_emits_store(self):
        """The update expression i = i + 1 must emit a STORE_VAR in the IR."""
        ir = _parse_js("""\
let x = 0;
for (let i = 0; i < 3; i = i + 1) {
    x = x + 1;
}
""")
        # The initializer 'let i = 0' produces DECL_VAR,
        # the update 'i = i + 1' produces STORE_VAR
        decls = _find_all(ir, Opcode.DECL_VAR)
        stores = _find_all(ir, Opcode.STORE_VAR)
        i_decls = [inst for inst in decls if inst.operands and inst.operands[0] == "i"]
        i_stores = [
            inst for inst in stores if inst.operands and inst.operands[0] == "i"
        ]
        assert (
            len(i_decls) >= 1
        ), f"Expected >= 1 DECL_VAR for 'i' (init), got {len(i_decls)}"
        assert (
            len(i_stores) >= 1
        ), f"Expected >= 1 STORE_VAR for 'i' (update), got {len(i_stores)}"


class TestOptionalChain:
    """optional_chain (?.) emits null-guard conditional around access."""

    def test_optional_chain_property_emits_null_guard(self):
        """obj?.prop should emit BRANCH_IF (null check) + LOAD_FIELD."""
        ir = _parse_js("const x = obj?.prop;")
        loads = _find_all(ir, Opcode.LOAD_FIELD)
        assert any(
            "prop" in inst.operands for inst in loads
        ), f"Expected LOAD_FIELD for 'prop', got: {[i.operands for i in loads]}"
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 1, "Expected BRANCH_IF for null guard"
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "optional_chain" in str(s.operands) for s in symbolics
        ), "optional_chain should not produce SYMBOLIC"

    def test_optional_chain_method_call_emits_null_guard(self):
        """obj?.method(1) should emit BRANCH_IF + CALL_METHOD."""
        ir = _parse_js("const y = obj?.method(1);")
        calls = _find_all(ir, Opcode.CALL_METHOD)
        assert any(
            "method" in inst.operands for inst in calls
        ), f"Expected CALL_METHOD for 'method', got: {[i.operands for i in calls]}"
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 1, "Expected BRANCH_IF for null guard"

    def test_optional_chain_index_emits_null_guard(self):
        """obj?.[0] should emit BRANCH_IF + LOAD_INDEX."""
        ir = _parse_js("const z = obj?.[0];")
        loads = _find_all(ir, Opcode.LOAD_INDEX)
        assert len(loads) >= 1, f"Expected LOAD_INDEX, got opcodes: {_opcodes(ir)}"
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 1, "Expected BRANCH_IF for null guard"

    def test_optional_chain_nested(self):
        """a?.b?.c should emit two null guards and two LOAD_FIELDs."""
        ir = _parse_js("const w = a?.b?.c;")
        loads = _find_all(ir, Opcode.LOAD_FIELD)
        field_names = [inst.operands[1] for inst in loads if len(inst.operands) >= 2]
        assert "b" in field_names, f"Expected LOAD_FIELD for 'b', got: {field_names}"
        assert "c" in field_names, f"Expected LOAD_FIELD for 'c', got: {field_names}"
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert (
            len(branches) >= 2
        ), f"Expected 2 BRANCH_IFs for chained guards, got {len(branches)}"

    def test_regular_member_access_no_guard(self):
        """obj.prop should NOT emit BRANCH_IF — only ?. gets a guard."""
        ir = _parse_js("const x = obj.prop;")
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert (
            len(branches) == 0
        ), f"Regular access should not emit BRANCH_IF, got {len(branches)}"


class TestComputedPropertyName:
    """computed_property_name ({ [expr]: value }) evaluates expression as key (ADR-101)."""

    def test_computed_property_identifier_key(self):
        """{ [key]: 1 } should evaluate 'key' via LOAD_VAR, not as const literal."""
        ir = _parse_js("const obj = { [key]: 1 };")
        loads = _find_all(ir, Opcode.LOAD_VAR)
        assert any(
            "key" in inst.operands for inst in loads
        ), f"Expected LOAD_VAR for 'key', got: {[i.operands for i in loads]}"
        stores = _find_all(ir, Opcode.STORE_INDEX)
        assert (
            len(stores) >= 1
        ), f"Expected STORE_INDEX for computed key, got: {_opcodes(ir)}"

    def test_computed_property_expression_key(self):
        """{ [1 + 2]: 'x' } should evaluate binary expression as key."""
        ir = _parse_js("const obj = { [1 + 2]: 'x' };")
        binops = _find_all(ir, Opcode.BINOP)
        assert any(
            "+" in inst.operands for inst in binops
        ), f"Expected BINOP with '+', got: {[i.operands for i in binops]}"
        stores = _find_all(ir, Opcode.STORE_INDEX)
        assert len(stores) >= 1, f"Expected STORE_INDEX for computed key"

    def test_mixed_computed_and_static_keys(self):
        """{ [key]: 1, normal: 2 } should handle both key types."""
        ir = _parse_js("const obj = { [key]: 1, normal: 2 };")
        stores = _find_all(ir, Opcode.STORE_INDEX)
        assert (
            len(stores) >= 2
        ), f"Expected >= 2 STORE_INDEX (computed + static), got {len(stores)}"


class TestAnonymousClassExpression:
    """Anonymous class expression: const Foo = class { ... }"""

    def test_anonymous_class_no_symbolic(self):
        ir = _parse_js("const Foo = class { constructor() {} };")
        symbolics = [
            s
            for s in ir
            if s.opcode == Opcode.SYMBOLIC and "unsupported:class" in str(s.operands)
        ]
        assert (
            len(symbolics) == 0
        ), f"class expression should not produce SYMBOLIC: {symbolics}"

    def test_anonymous_class_emits_class_block(self):
        ir = _parse_js("const Foo = class { constructor() {} };")
        labels = [
            str(inst.label)
            for inst in ir
            if inst.opcode == Opcode.LABEL and inst.label.is_present()
        ]
        class_labels = [l for l in labels if l.startswith("class_")]
        assert len(class_labels) >= 1, f"Expected class_ label, got: {labels}"

    def test_anonymous_class_methods_lowered(self):
        ir = _parse_js("""
            const Foo = class {
                constructor(x) { this.x = x; }
                greet() { return this.x; }
            };
            """)
        labels = [
            str(inst.label)
            for inst in ir
            if inst.opcode == Opcode.LABEL and inst.label.is_present()
        ]
        func_labels = [l for l in labels if l.startswith("func_")]
        assert any(
            "constructor" in l for l in func_labels
        ), f"Expected 'constructor' method, got: {func_labels}"
        assert any(
            "greet" in l for l in func_labels
        ), f"Expected 'greet' method, got: {func_labels}"

    def test_named_class_expression(self):
        """const Foo = class MyClass { ... } — class has explicit name."""
        ir = _parse_js("const Foo = class MyClass { constructor() {} };")
        labels = [
            str(inst.label)
            for inst in ir
            if inst.opcode == Opcode.LABEL and inst.label.is_present()
        ]
        class_labels = [l for l in labels if l.startswith("class_")]
        assert any(
            "MyClass" in l for l in class_labels
        ), f"Expected class label with 'MyClass', got: {class_labels}"

    def test_anonymous_class_stored_in_variable(self):
        ir = _parse_js("const Foo = class { constructor() {} };")
        stores = _find_all(ir, Opcode.DECL_VAR)
        store_names = [s.operands[0] for s in stores if s.operands]
        assert "Foo" in store_names, f"Expected 'Foo' in STORE_VAR, got: {store_names}"
