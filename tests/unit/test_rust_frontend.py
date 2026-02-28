"""Tests for RustFrontend -- tree-sitter Rust AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.rust import RustFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_rust(source: str) -> list[IRInstruction]:
    parser = get_parser("rust")
    tree = parser.parse(source.encode("utf-8"))
    frontend = RustFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestRustDeclarations:
    def test_let_declaration(self):
        instructions = _parse_rust("fn main() { let x = 10; }")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_let_mut_declaration(self):
        instructions = _parse_rust("fn main() { let mut x = 5; }")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_let_without_initializer(self):
        instructions = _parse_rust("fn main() { let x: i32; }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestRustFunctions:
    def test_function_definition(self):
        instructions = _parse_rust("fn add(a: i32, b: i32) -> i32 { a + b }")
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("add" in inst.operands for inst in stores)

    def test_function_call(self):
        instructions = _parse_rust("fn main() { add(1, 2); }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("add" in inst.operands for inst in calls)

    def test_return_expression(self):
        instructions = _parse_rust("fn main() { return 42; }")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)


class TestRustControlFlow:
    def test_if_expression_value_producing(self):
        instructions = _parse_rust("fn main() { let y = if x > 0 { 1 } else { 0 }; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("if_true" in (inst.label or "") for inst in labels)
        assert any("if_false" in (inst.label or "") for inst in labels)

    def test_while_loop_produces_ir(self):
        """Test that a while loop in Rust produces meaningful IR."""
        instructions = _parse_rust(
            "fn main() { let mut x: i32 = 10; while x > 0 { x = x - 1; } }"
        )
        # The while should produce some IR beyond just function scaffolding
        # (even if the tree-sitter grammar version maps it to a different node type)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        assert Opcode.LABEL in opcodes
        # Should have lowered the condition or body in some form
        assert len(instructions) > 10

    def test_match_expression(self):
        instructions = _parse_rust(
            "fn main() { let r = match x { 1 => 10, 2 => 20, _ => 0 }; }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("match" in (inst.label or "") for inst in labels)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("r" in inst.operands for inst in stores)


class TestRustStructs:
    def test_struct_definition(self):
        instructions = _parse_rust("struct Dog { name: String }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

    def test_impl_block_with_methods(self):
        instructions = _parse_rust(
            'impl Dog { fn bark(&self) -> String { return String::from("woof"); } }'
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        assert Opcode.RETURN in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)


class TestRustExpressions:
    def test_closure_expression(self):
        instructions = _parse_rust("fn main() { let f = |a, b| a + b; }")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        assert Opcode.BINOP in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any("__closure" in str(inst.operands) for inst in consts)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("f" in inst.operands for inst in stores)

    def test_reference_expression(self):
        instructions = _parse_rust("fn main() { let r = &x; }")
        unops = _find_all(instructions, Opcode.UNOP)
        assert any("&" in inst.operands for inst in unops)

    def test_dereference_expression(self):
        instructions = _parse_rust("fn main() { let v = *x; }")
        unops = _find_all(instructions, Opcode.UNOP)
        assert any("*" in inst.operands for inst in unops)

    def test_assignment_expression(self):
        instructions = _parse_rust("fn main() { x = 10; }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_compound_assignment(self):
        instructions = _parse_rust("fn main() { x += 5; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_macro_invocation(self):
        instructions = _parse_rust('fn main() { println!("hello"); }')
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("println!" in inst.operands for inst in calls)


class TestRustSpecial:
    def test_empty_program(self):
        instructions = _parse_rust("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_fallback_symbolic(self):
        instructions = _parse_rust("fn main() { unsafe { do_risky(); } }")
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes or Opcode.CALL_FUNCTION in opcodes

    def test_binary_expression(self):
        instructions = _parse_rust("fn main() { let z = x + y; }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_block_expression_returns_last(self):
        instructions = _parse_rust("fn main() { let v = { let a = 1; a + 2 }; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("v" in inst.operands for inst in stores)


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialRust:
    def test_match_with_multiple_arms(self):
        source = """\
fn main() {
    let r = match x {
        1 => 10,
        2 => 20,
        3 => 30,
        _ => 0,
    };
}
"""
        instructions = _parse_rust(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 3
        labels = _labels_in_order(instructions)
        assert any("match" in lbl for lbl in labels)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("r" in inst.operands for inst in stores)
        assert len(instructions) > 20

    def test_impl_with_constructor_and_method(self):
        source = """\
struct Counter { count: i32 }
impl Counter {
    fn new(start: i32) -> Counter {
        Counter { count: start }
    }
    fn value(&self) -> i32 {
        return self.count;
    }
}
"""
        instructions = _parse_rust(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Counter" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1
        assert len(instructions) > 15

    def test_closure_in_method_call(self):
        source = """\
fn main() {
    let doubled = items.iter().map(|x| x * 2);
}
"""
        instructions = _parse_rust(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        assert "iter" in method_names
        assert "map" in method_names
        consts = _find_all(instructions, Opcode.CONST)
        assert any("__closure" in str(inst.operands) for inst in consts)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("doubled" in inst.operands for inst in stores)

    def test_for_range_with_mutation(self):
        source = """\
fn main() {
    let mut total = 0;
    let mut i = 0;
    while i < 10 {
        if i % 2 == 0 {
            total = total + i;
        }
        i = i + 1;
    }
}
"""
        instructions = _parse_rust(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("total" in inst.operands for inst in stores)
        assert any("i" in inst.operands for inst in stores)
        assert len(instructions) > 20

    def test_nested_if_as_expression(self):
        source = """\
fn main() {
    let grade = if score > 90 {
        "A"
    } else if score > 70 {
        "B"
    } else {
        "C"
    };
}
"""
        instructions = _parse_rust(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("grade" in inst.operands for inst in stores)
        labels = _labels_in_order(instructions)
        assert any("if_true" in lbl for lbl in labels)

    def test_reference_and_dereference(self):
        source = """\
fn main() {
    let x = 42;
    let r = &x;
    let val = *r;
    let y = val + 1;
}
"""
        instructions = _parse_rust(source)
        unops = _find_all(instructions, Opcode.UNOP)
        operators = [inst.operands[0] for inst in unops if inst.operands]
        assert "&" in operators
        assert "*" in operators
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        assert any("r" in inst.operands for inst in stores)
        assert any("val" in inst.operands for inst in stores)
        assert any("y" in inst.operands for inst in stores)

    def test_while_loop_with_nested_if(self):
        source = """\
fn main() {
    let mut count = 0;
    let mut sum = 0;
    while count < 100 {
        if count > 50 {
            sum = sum + count;
        } else {
            sum = sum + 1;
        }
        count = count + 1;
    }
}
"""
        instructions = _parse_rust(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("count" in inst.operands for inst in stores)
        assert any("sum" in inst.operands for inst in stores)
        assert len(instructions) > 25

    def test_function_calling_function(self):
        source = """\
fn double(x: i32) -> i32 {
    x * 2
}
fn quadruple(x: i32) -> i32 {
    double(double(x))
}
"""
        instructions = _parse_rust(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("double" in inst.operands for inst in stores)
        assert any("quadruple" in inst.operands for inst in stores)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("double" in inst.operands for inst in calls)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 2


class TestRustTryExpression:
    def test_try_expression_question_mark(self):
        instructions = _parse_rust("fn main() { let v = read_file()?; }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("try_unwrap" in inst.operands for inst in calls)

    def test_try_expression_chained(self):
        instructions = _parse_rust("fn main() { let v = foo()?.bar()?; }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert sum(1 for inst in calls if "try_unwrap" in inst.operands) >= 2

    def test_try_expression_stores_result(self):
        instructions = _parse_rust("fn main() { let x = some_fn()?; }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestRustAwaitExpression:
    def test_await_expression(self):
        instructions = _parse_rust("async fn main() { let v = fetch().await; }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("await" in inst.operands for inst in calls)

    def test_await_stores_result(self):
        instructions = _parse_rust("async fn main() { let r = get_data().await; }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("r" in inst.operands for inst in stores)


class TestRustAsyncBlock:
    def test_async_block_produces_ir(self):
        instructions = _parse_rust("fn main() { let f = async { 42 }; }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("f" in inst.operands for inst in stores)

    def test_async_block_with_statements(self):
        instructions = _parse_rust("fn main() { let f = async { let x = 1; x + 2 }; }")
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("f" in inst.operands for inst in stores)


class TestRustTraitItem:
    def test_trait_definition(self):
        instructions = _parse_rust("trait Animal { fn speak(&self); }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Animal" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

    def test_trait_with_default_method(self):
        instructions = _parse_rust(
            'trait Greet { fn hello(&self) -> String { return String::from("hi"); } }'
        )
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Greet" in inst.operands for inst in stores)
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes

    def test_trait_labels(self):
        instructions = _parse_rust("trait Drawable { fn draw(&self); }")
        labels = _labels_in_order(instructions)
        assert any("class_Drawable" in lbl for lbl in labels)


class TestRustEnumItem:
    def test_enum_basic(self):
        instructions = _parse_rust("enum Color { Red, Green, Blue }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Color" in inst.operands for inst in stores)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("enum:Color" in inst.operands for inst in new_objs)

    def test_enum_store_fields(self):
        instructions = _parse_rust("enum Direction { North, South, East, West }")
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        assert len(store_fields) >= 4

    def test_enum_with_data(self):
        instructions = _parse_rust("enum Shape { Circle(f64), Rect(f64, f64) }")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("enum:Shape" in inst.operands for inst in new_objs)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Shape" in inst.operands for inst in stores)


class TestRustConstItem:
    def test_const_item(self):
        instructions = _parse_rust("const MAX: i32 = 100;")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("MAX" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("100" in inst.operands for inst in consts)

    def test_const_item_string(self):
        instructions = _parse_rust('const NAME: &str = "hello";')
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("NAME" in inst.operands for inst in stores)


class TestRustStaticItem:
    def test_static_item(self):
        instructions = _parse_rust("static COUNT: i32 = 0;")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("COUNT" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("0" in inst.operands for inst in consts)

    def test_static_mut_item(self):
        instructions = _parse_rust("static mut COUNTER: i32 = 0;")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("COUNTER" in inst.operands for inst in stores)


class TestRustTypeItem:
    def test_type_alias(self):
        instructions = _parse_rust("type Pair = (i32, i32);")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Pair" in inst.operands for inst in stores)

    def test_type_alias_const_value(self):
        instructions = _parse_rust("type Meters = f64;")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("f64" in inst.operands for inst in consts)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Meters" in inst.operands for inst in stores)


class TestRustModItem:
    def test_mod_item_with_body(self):
        instructions = _parse_rust("mod utils { fn helper() { } }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("helper" in inst.operands for inst in stores)

    def test_mod_item_nested_function(self):
        instructions = _parse_rust(
            "mod math { fn add(a: i32, b: i32) -> i32 { a + b } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("add" in inst.operands for inst in stores)

    def test_mod_item_empty(self):
        instructions = _parse_rust("mod empty { }")
        # Should not crash, should just produce entry label
        assert instructions[0].opcode == Opcode.LABEL


class TestRustExternCrate:
    def test_extern_crate_noop(self):
        instructions = _parse_rust("extern crate serde;")
        # Should be a no-op, just the entry label
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_extern_crate_with_other_code(self):
        instructions = _parse_rust("extern crate serde; const X: i32 = 1;")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("X" in inst.operands for inst in stores)


class TestRustUnsafeBlock:
    def test_unsafe_block_lowers_body(self):
        instructions = _parse_rust("fn main() { unsafe { let x = 1; x + 2 } }")
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_unsafe_block_with_call(self):
        instructions = _parse_rust("fn main() { unsafe { do_risky(); } }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("do_risky" in inst.operands for inst in calls)


class TestRustTypeCastExpression:
    def test_type_cast_basic(self):
        instructions = _parse_rust("fn main() { let x = y as f64; }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("as" in inst.operands for inst in calls)
        assert any("f64" in str(inst.operands) for inst in calls)

    def test_type_cast_stores_result(self):
        instructions = _parse_rust("fn main() { let x = count as f64; }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_type_cast_not_symbolic(self):
        instructions = _parse_rust("fn main() { let x = y as i32; }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("type_cast" in str(inst.operands) for inst in symbolics)

    def test_type_cast_in_expression(self):
        instructions = _parse_rust("fn main() { let x = (a as f64) + 1.0; }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("as" in inst.operands for inst in calls)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestRustScopedIdentifier:
    def test_scoped_identifier_enum_variant(self):
        instructions = _parse_rust("fn main() { let x = Shape::Circle; }")
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("Shape::Circle" in inst.operands for inst in loads)

    def test_scoped_identifier_in_call(self):
        instructions = _parse_rust("fn main() { let m = HashMap::new(); }")
        # scoped_identifier is the callee inside call_expression
        # The call should go through CALL_UNKNOWN since target is not a plain identifier
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("HashMap::new" in inst.operands for inst in loads)

    def test_scoped_identifier_stores_result(self):
        instructions = _parse_rust("fn main() { let v = Option::None; }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("v" in inst.operands for inst in stores)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("Option::None" in inst.operands for inst in loads)


class TestRustDestructuring:
    def test_tuple_destructure_two_elements(self):
        instructions = _parse_rust("fn main() { let (a, b) = get_pair(); }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "a" in store_names
        assert "b" in store_names
        load_indices = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(load_indices) >= 2

    def test_tuple_destructure_three_elements(self):
        instructions = _parse_rust("fn main() { let (x, y, z) = get_triple(); }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "x" in store_names
        assert "y" in store_names
        assert "z" in store_names
        load_indices = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(load_indices) >= 3

    def test_struct_destructure(self):
        instructions = _parse_rust("fn main() { let Point { x, y } = point; }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "x" in store_names
        assert "y" in store_names
        load_fields = _find_all(instructions, Opcode.LOAD_FIELD)
        assert len(load_fields) >= 2


class TestRustRangeExpression:
    def test_range_expression_basic(self):
        instructions = _parse_rust("fn main() { let r = 0..10; }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("range" in inst.operands for inst in calls)
        # No SYMBOLIC fallback
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("range_expression" in str(inst.operands) for inst in symbolics)

    def test_range_inclusive(self):
        instructions = _parse_rust("fn main() { let r = 0..=10; }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("range" in inst.operands for inst in calls)

    def test_range_in_for_loop(self):
        instructions = _parse_rust("fn main() { for i in 0..n {} }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("range" in inst.operands for inst in calls)


class TestRustMatchPatternUnwrap:
    def test_match_pattern_no_symbolic(self):
        source = "fn f() { match x { (1) => 2, _ => 0 } }"
        instructions = _parse_rust(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("match_pattern" in str(inst.operands) for inst in symbolics)

    def test_match_pattern_lowers_inner(self):
        source = "fn f() { match x { (y) => y + 1, _ => 0 } }"
        instructions = _parse_rust(source)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("1" in inst.operands for inst in consts)
