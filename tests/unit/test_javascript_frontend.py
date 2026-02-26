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
        assert Opcode.CALL_FUNCTION in opcodes
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("keys" in inst.operands for inst in calls)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("a" in inst.operands for inst in stores)
        assert any("b" in inst.operands for inst in stores)

    def test_obj_destructure_rename(self):
        source = "const { x: localX, y: localY } = obj;"
        instructions = _parse_js(source)
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        field_names = [inst.operands[1] for inst in loads if len(inst.operands) > 1]
        assert "x" in field_names
        assert "y" in field_names
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("localX" in inst.operands for inst in stores)
        assert any("localY" in inst.operands for inst in stores)

    def test_arr_destructure_basic(self):
        source = "const [a, b] = arr;"
        instructions = _parse_js(source)
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_INDEX in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("a" in inst.operands for inst in stores)
        assert any("b" in inst.operands for inst in stores)

    def test_arr_destructure_three(self):
        source = "const [x, y, z] = arr;"
        instructions = _parse_js(source)
        loads = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(loads) >= 3
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        assert any("y" in inst.operands for inst in stores)
        assert any("z" in inst.operands for inst in stores)


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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("obj" in inst.operands for inst in stores)

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
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_sequence_with_side_effects(self):
        instructions = _parse_js("const x = (a++, b++, c);")
        binops = _find_all(instructions, Opcode.BINOP)
        assert len(binops) >= 2


class TestJavaScriptSpreadElement:
    def test_spread_in_call(self):
        instructions = _parse_js("foo(...args);")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("spread" in inst.operands for inst in calls)

    def test_spread_in_array(self):
        instructions = _parse_js("const arr = [...items, 4, 5];")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("spread" in inst.operands for inst in calls)

    def test_spread_multiple(self):
        instructions = _parse_js("foo(...a, ...b);")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        spread_calls = [c for c in calls if "spread" in c.operands]
        assert len(spread_calls) >= 2


class TestJavaScriptFunctionExpression:
    def test_anonymous_function(self):
        instructions = _parse_js("const f = function(x) { return x + 1; };")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any("function:" in str(inst.operands) for inst in consts)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("f" in inst.operands for inst in stores)

    def test_named_function_expression(self):
        instructions = _parse_js("const f = function myFunc(x) { return x; };")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("function:" in str(inst.operands) for inst in consts)
        assert any("myFunc" in str(inst.operands) for inst in consts)

    def test_function_expression_as_callback(self):
        instructions = _parse_js("arr.forEach(function(item) { process(item); });")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("forEach" in inst.operands for inst in calls)


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
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("add" in inst.operands for inst in stores)

    def test_export_variable_declaration(self):
        instructions = _parse_js("export const x = 42;")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)

    def test_export_class_declaration(self):
        instructions = _parse_js("export class Foo { constructor() {} }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Foo" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)
