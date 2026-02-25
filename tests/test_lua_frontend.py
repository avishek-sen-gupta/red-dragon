"""Tests for LuaFrontend — tree-sitter Lua AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.lua import LuaFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_lua(source: str) -> list[IRInstruction]:
    parser = get_parser("lua")
    tree = parser.parse(source.encode("utf-8"))
    frontend = LuaFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestLuaSmoke:
    def test_empty_program(self):
        instructions = _parse_lua("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_entry_label_always_present(self):
        instructions = _parse_lua("local x = 1")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"


class TestLuaLocalVariables:
    def test_local_variable_declaration(self):
        instructions = _parse_lua("local x = 10")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("10" in inst.operands for inst in consts)

    def test_local_without_initializer(self):
        # tree-sitter Lua wraps the identifier inside variable_list (no
        # assignment_statement child), and the current frontend does not find
        # the identifier as a direct child of variable_declaration.  The
        # expected behaviour is that the declaration produces no IR beyond
        # the entry label — this test documents that limitation.
        instructions = _parse_lua("local x")
        assert instructions[0].opcode == Opcode.LABEL
        # Only the entry label is emitted
        assert len(instructions) == 1

    def test_local_with_nil_initializer(self):
        # Explicitly assigning nil does produce CONST + STORE_VAR
        instructions = _parse_lua("local x = nil")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any("nil" in inst.operands for inst in consts)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestLuaExpressions:
    def test_arithmetic_expression(self):
        instructions = _parse_lua("local y = x + 5")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.CONST in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_assignment(self):
        instructions = _parse_lua("x = x + 1")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_nil_literal(self):
        instructions = _parse_lua("local x = nil")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("nil" in inst.operands for inst in consts)

    def test_boolean_true(self):
        instructions = _parse_lua("local x = true")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("true" in inst.operands for inst in consts)

    def test_boolean_false(self):
        instructions = _parse_lua("local x = false")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("false" in inst.operands for inst in consts)


class TestLuaFunctions:
    def test_function_declaration(self):
        instructions = _parse_lua("function add(a, b) return a + b end")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        assert Opcode.RETURN in opcodes
        # Parameters are lowered as SYMBOLIC param:name
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

    def test_function_declaration_with_explicit_body(self):
        # A function whose body uses statements (not just return expr)
        instructions = _parse_lua("function inc(x) local r = x + 1 return r end")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.RETURN in opcodes

    def test_function_call(self):
        instructions = _parse_lua("add(1, 2)")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) >= 1
        assert "add" in calls[0].operands

    def test_method_call(self):
        instructions = _parse_lua("obj:method()")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1
        assert "method" in calls[0].operands

    def test_return_statement_with_value(self):
        instructions = _parse_lua("function f() return 42 end")
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1

    def test_return_statement_without_value(self):
        instructions = _parse_lua("function f() return end")
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1
        consts = _find_all(instructions, Opcode.CONST)
        assert any("nil" in inst.operands for inst in consts)


class TestLuaTableAccess:
    def test_dot_access(self):
        instructions = _parse_lua("local x = obj.field")
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert len(loads) >= 1
        assert "field" in loads[0].operands

    def test_bracket_access(self):
        instructions = _parse_lua("local x = obj[key]")
        loads = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(loads) >= 1

    def test_table_constructor(self):
        instructions = _parse_lua("local t = {a = 1, b = 2}")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any("a" in inst.operands for inst in consts)
        assert any("b" in inst.operands for inst in consts)


class TestLuaControlFlow:
    def test_if_statement(self):
        instructions = _parse_lua("if x > 5 then y = 1 end")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        assert Opcode.BINOP in opcodes

    def test_if_else_statement(self):
        instructions = _parse_lua("if x > 5 then y = 1 else y = 0 end")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        label_names = [inst.label for inst in labels]
        assert any("if_true" in (lbl or "") for lbl in label_names)
        assert any("if_false" in (lbl or "") for lbl in label_names)

    def test_if_elseif_else(self):
        instructions = _parse_lua(
            "if x > 5 then y = 1 elseif x > 0 then y = 2 else y = 3 end"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        branch_ifs = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branch_ifs) >= 2

    def test_while_loop(self):
        instructions = _parse_lua("while x > 0 do x = x - 1 end")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("while" in (inst.label or "") for inst in labels)

    def test_for_numeric(self):
        instructions = _parse_lua("for i = 1, 10 do print(i) end")
        opcodes = _opcodes(instructions)
        assert Opcode.STORE_VAR in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.BRANCH_IF in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("i" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("<=" in inst.operands for inst in binops)

    def test_repeat_until(self):
        instructions = _parse_lua("repeat x = x - 1 until x == 0")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.UNOP in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("repeat" in (inst.label or "") for inst in labels)

    def test_generic_for_fallback(self):
        instructions = _parse_lua("for k, v in pairs(t) do print(k) end")
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("generic_for_iteration" in str(inst.operands) for inst in symbolics)
