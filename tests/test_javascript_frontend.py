"""Tests for JavaScriptFrontend — tree-sitter JavaScript AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.javascript import JavaScriptFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_js(source: str) -> list[IRInstruction]:
    parser = get_parser("javascript")
    tree = parser.parse(source.encode("utf-8"))
    frontend = JavaScriptFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


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
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_arithmetic_expression(self):
        instructions = _parse_js("let y = x + 5;")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.CONST in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_ternary_expression(self):
        instructions = _parse_js('let y = x > 0 ? "pos" : "neg";')
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.STORE_VAR in opcodes

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
        assert any("while" in (inst.label or "") for inst in labels)

    def test_for_loop(self):
        instructions = _parse_js("for (let i = 0; i < 10; i++) { x = x + i; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("i" in inst.operands for inst in stores)

    def test_for_in_loop(self):
        instructions = _parse_js("for (let k in obj) { x = k; }")
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes
        assert Opcode.BRANCH_IF in opcodes


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
        assert len(calls) >= 1
        assert "add" in calls[0].operands

    def test_arrow_function(self):
        instructions = _parse_js("const f = (a, b) => a + b;")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)


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
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialJavaScript:
    def test_arrow_function_in_method_call(self):
        source = "const doubled = items.map((x) => x * 2);"
        instructions = _parse_js(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("map" in inst.operands for inst in calls)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("*" in inst.operands for inst in binops)
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Counter" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("classify" in inst.operands for inst in stores)

    def test_template_literal_with_expressions(self):
        source = """\
const name = "world";
const count = 5;
const msg = `Hello ${name}, you have ${count} items`;
"""
        instructions = _parse_js(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        labels = [i.label for i in instructions if i.opcode == Opcode.LABEL]
        # try/catch body and catch block are lowered with LABEL/BRANCH
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_end" in l for l in labels)
        assert Opcode.THROW in opcodes
        # No catch_clause: SYMBOLIC placeholders
        symbolics = [i for i in instructions if i.opcode == Opcode.SYMBOLIC]
        assert not any("catch_clause:" in str(s.operands) for s in symbolics)
        assert len(instructions) > 1

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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("config" in inst.operands for inst in stores)
        assert any("upper" in inst.operands for inst in stores)
