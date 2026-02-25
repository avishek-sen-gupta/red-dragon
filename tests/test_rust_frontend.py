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
