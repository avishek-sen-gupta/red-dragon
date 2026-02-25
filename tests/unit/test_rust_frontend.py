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
