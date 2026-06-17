"""Tests for LuaFrontend — tree-sitter Lua AST to IR lowering."""

from __future__ import annotations

from interpreter.frontends.lua import LuaFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import Opcode
from interpreter.instructions import InstructionBase
from tests.unit.rosetta.conftest import execute_for_language, extract_answer
from interpreter.frontends.lua.features import LuaFeature
from tests.covers import covers, NotLanguageFeature


def _parse_lua(source: str) -> list[InstructionBase]:
    frontend = LuaFrontend(TreeSitterParserFactory(), "lua")
    return frontend.lower(source.encode("utf-8"))


def _opcodes(instructions: list[InstructionBase]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(
    instructions: list[InstructionBase], opcode: Opcode
) -> list[InstructionBase]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestLuaSmoke:
    @covers(LuaFeature.FUNCTION_CALL)
    def test_empty_program(self):
        instructions = _parse_lua("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    @covers(LuaFeature.FUNCTION_CALL)
    def test_entry_label_always_present(self):
        instructions = _parse_lua("local x = 1")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"


class TestLuaLocalVariables:
    @covers(LuaFeature.LOCAL_VARIABLE_DECLARATION)
    def test_local_variable_declaration(self):
        instructions = _parse_lua("local x = 10")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any(10 in inst.operands for inst in consts)

    @covers(LuaFeature.LOCAL_VARIABLE_DECLARATION)
    def test_local_without_initializer_produces_no_ir(self):
        # tree-sitter Lua wraps the identifier inside variable_list (no
        # assignment_statement child), and the current frontend does not find
        # the identifier as a direct child of variable_declaration.  The
        # expected behaviour is that the declaration produces no IR beyond
        # the entry label — this test documents that limitation.
        instructions = _parse_lua("local x")
        assert instructions[0].opcode == Opcode.LABEL
        # Only the entry label is emitted
        assert len(instructions) == 1

    @covers(LuaFeature.LOCAL_VARIABLE_DECLARATION)
    def test_local_with_nil_initializer(self):
        # Explicitly assigning nil does produce CONST + STORE_VAR
        instructions = _parse_lua("local x = nil")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any(None in inst.operands for inst in consts)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestLuaExpressions:
    @covers(LuaFeature.ARITHMETIC)
    def test_arithmetic_expression(self):
        instructions = _parse_lua("local y = x + 5")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.CONST in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    @covers(LuaFeature.ARITHMETIC)
    def test_assignment(self):
        instructions = _parse_lua("x = x + 1")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    @covers(LuaFeature.ARITHMETIC)
    def test_nil_literal(self):
        instructions = _parse_lua("local x = nil")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(None in inst.operands for inst in consts)

    @covers(LuaFeature.ARITHMETIC)
    def test_boolean_true(self):
        instructions = _parse_lua("local x = true")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(True in inst.operands for inst in consts)

    @covers(LuaFeature.ARITHMETIC)
    def test_boolean_false(self):
        instructions = _parse_lua("local x = false")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(False in inst.operands for inst in consts)


class TestLuaOperators:
    @covers(LuaFeature.OPERATORS)
    def test_concatenation_operator(self):
        instructions = _parse_lua('local x = "hello" .. " world"')
        binops = _find_all(instructions, Opcode.BINOP)
        assert any(".." in inst.operands for inst in binops)

    @covers(LuaFeature.OPERATORS)
    def test_not_equal_operator(self):
        instructions = _parse_lua("if x ~= 0 then y = 1 end")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("~=" in inst.operands for inst in binops)

    @covers(LuaFeature.OPERATORS)
    def test_length_operator(self):
        instructions = _parse_lua('local x = #"hello"')
        unops = _find_all(instructions, Opcode.UNOP)
        assert any("#" in inst.operands for inst in unops)


class TestLuaFunctions:
    @covers(LuaFeature.FUNCTION_DECLARATION)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("add" in inst.operands for inst in stores)

    @covers(LuaFeature.FUNCTION_DECLARATION)
    def test_function_declaration_with_explicit_body(self):
        # A function whose body uses statements (not just return expr)
        instructions = _parse_lua("function inc(x) local r = x + 1 return r end")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.RETURN in opcodes

    @covers(LuaFeature.FUNCTION_CALL)
    def test_function_call(self):
        instructions = _parse_lua("add(1, 2)")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) >= 1
        assert "add" in calls[0].operands

    @covers(LuaFeature.METHOD_CALL)
    def test_method_call(self):
        instructions = _parse_lua("obj:method()")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1
        assert "method" in calls[0].operands

    @covers(LuaFeature.FUNCTION_DECLARATION)
    def test_return_statement_with_value(self):
        instructions = _parse_lua("function f() return 42 end")
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            "42" in str(c.operands) for c in consts
        ), f"return 42 should emit CONST 42, got {[c.operands for c in consts]}"

    @covers(LuaFeature.FUNCTION_DECLARATION)
    def test_return_statement_without_value(self):
        instructions = _parse_lua("function f() return end")
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1
        consts = _find_all(instructions, Opcode.CONST)
        assert any(None in inst.operands for inst in consts)


class TestLuaTableAccess:
    @covers(LuaFeature.TABLE_ACCESS)
    def test_dot_access(self):
        instructions = _parse_lua("local x = obj.field")
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert len(loads) >= 1
        assert "field" in loads[0].operands

    @covers(LuaFeature.TABLE_ACCESS)
    def test_bracket_access(self):
        instructions = _parse_lua("local x = obj[key]")
        loads = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(loads) >= 1

    @covers(LuaFeature.TABLE_ACCESS)
    def test_table_constructor(self):
        instructions = _parse_lua("local t = {a = 1, b = 2}")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any("a" in inst.operands for inst in consts)
        assert any("b" in inst.operands for inst in consts)


class TestLuaControlFlow:
    @covers(LuaFeature.IF_ELSE)
    def test_if_statement(self):
        instructions = _parse_lua("if x > 5 then y = 1 end")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        assert Opcode.BINOP in opcodes

    @covers(LuaFeature.IF_ELSE)
    def test_if_else_statement(self):
        instructions = _parse_lua("if x > 5 then y = 1 else y = 0 end")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        label_names = [str(inst.label) for inst in labels]
        assert any("if_true" in (lbl or "") for lbl in label_names)
        assert any("if_false" in (lbl or "") for lbl in label_names)

    @covers(LuaFeature.IF_ELSE)
    def test_if_elseif_else(self):
        instructions = _parse_lua(
            "if x > 5 then y = 1 elseif x > 0 then y = 2 else y = 3 end"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        branch_ifs = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branch_ifs) >= 2

    @covers(LuaFeature.WHILE_LOOP)
    def test_while_loop(self):
        instructions = _parse_lua("while x > 0 do x = x - 1 end")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any(inst.label.contains("while") for inst in labels)

    @covers(LuaFeature.FOR_LOOP)
    def test_for_numeric(self):
        instructions = _parse_lua("for i = 1, 10 do print(i) end")
        opcodes = _opcodes(instructions)
        assert Opcode.DECL_VAR in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.BRANCH_IF in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("i" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("<=" in inst.operands for inst in binops)

    @covers(LuaFeature.REPEAT_UNTIL)
    def test_repeat_until(self):
        instructions = _parse_lua("repeat x = x - 1 until x == 0")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.UNOP in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any(inst.label.contains("repeat") for inst in labels)

    @covers(LuaFeature.GENERIC_FOR)
    def test_generic_for_index_based(self):
        """Generic for should produce index-based IR with LOAD_INDEX."""
        instructions = _parse_lua("for k, v in pairs(t) do print(k) end")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_INDEX in opcodes
        assert Opcode.BRANCH_IF in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("k" in inst.operands for inst in stores)
        assert any("v" in inst.operands for inst in stores)

    @covers(LuaFeature.IF_ELSE)
    def test_if_elseif_chain_all_branches_produce_ir(self):
        """All branches of if/elseif/elseif/else must produce IR."""
        instructions = _parse_lua(
            "if x==1 then y=10 elseif x==2 then y=20"
            " elseif x==3 then y=30 else y=40 end"
        )
        consts = _find_all(instructions, Opcode.CONST)
        const_values = [op for inst in consts for op in inst.operands]
        assert 10 in const_values, "if-branch value missing"
        assert 20 in const_values, "first elseif-branch value missing"
        assert 30 in const_values, "second elseif-branch value missing"
        assert 40 in const_values, "else-branch value missing"

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


def _labels_in_order(instructions: list[InstructionBase]) -> list[str]:
    return [str(inst.label) for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialLua:
    @covers(LuaFeature.TABLE_ACCESS)
    def test_table_with_dot_and_bracket_access(self):
        source = """\
local config = {name = "app", version = 2}
local n = config.name
local v = config["version"]
"""
        instructions = _parse_lua(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes
        assert Opcode.LOAD_FIELD in opcodes
        assert Opcode.LOAD_INDEX in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("config" in inst.operands for inst in stores)
        assert any("n" in inst.operands for inst in stores)
        assert any("v" in inst.operands for inst in stores)

    @covers(LuaFeature.REPEAT_UNTIL)
    def test_repeat_until_loop(self):
        source = """\
local x = 10
repeat
    x = x - 1
    print(x)
until x == 0
"""
        instructions = _parse_lua(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.UNOP in opcodes
        labels = _labels_in_order(instructions)
        assert any("repeat" in lbl for lbl in labels)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("print" in inst.operands for inst in calls)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    @covers(LuaFeature.GENERIC_FOR)
    def test_generic_for_with_ipairs(self):
        source = """\
local t = {10, 20, 30}
for i, v in ipairs(t) do
    print(v)
end
"""
        instructions = _parse_lua(source)
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_INDEX in opcodes
        assert Opcode.BRANCH_IF in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("i" in inst.operands for inst in stores)
        assert any("v" in inst.operands for inst in stores)
        # Lua table constructors use NEW_OBJECT
        assert Opcode.NEW_OBJECT in opcodes

    @covers(LuaFeature.FUNCTION_DECLARATION)
    def test_local_function_with_nested_if(self):
        source = """\
local function classify(x)
    if x > 100 then
        return "high"
    elseif x > 50 then
        return "medium"
    else
        return "low"
    end
end
"""
        instructions = _parse_lua(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 3
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("classify" in inst.operands for inst in stores)

    @covers(LuaFeature.WHILE_LOOP)
    def test_nested_while_with_table_access(self):
        source = """\
local i = 0
local total = 0
while i < 10 do
    local j = 0
    while j < 5 do
        total = total + data[j]
        j = j + 1
    end
    i = i + 1
end
"""
        instructions = _parse_lua(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        labels = _labels_in_order(instructions)
        while_labels = [lbl for lbl in labels if "while" in lbl]
        assert len(while_labels) >= 2
        assert Opcode.LOAD_INDEX in _opcodes(instructions)
        assert len(instructions) > 25

    @covers(LuaFeature.METHOD_CALL)
    def test_method_call_colon_syntax(self):
        source = """\
local obj = {}
obj:init("hello")
local result = obj:process()
"""
        instructions = _parse_lua(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        assert "init" in method_names
        assert "process" in method_names
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)

    @covers(LuaFeature.FOR_LOOP)
    def test_numeric_for_with_step(self):
        source = """\
local total = 0
for i = 1, 10, 2 do
    total = total + i
end
"""
        instructions = _parse_lua(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        decls = _find_all(instructions, Opcode.DECL_VAR)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("total" in inst.operands for inst in stores)
        assert any("i" in inst.operands for inst in decls)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    @covers(LuaFeature.LOCAL_VARIABLE_DECLARATION)
    def test_multi_assignment(self):
        source = """\
local a, b = 1, 2
local c = a + b
"""
        instructions = _parse_lua(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("a" in inst.operands for inst in stores)
        assert any("b" in inst.operands for inst in stores)
        assert any("c" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestLuaGenericFor:
    @covers(LuaFeature.GENERIC_FOR)
    def test_generic_for_ipairs(self):
        source = "for i, v in ipairs(t) do print(v) end"
        instructions = _parse_lua(source)
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_INDEX in opcodes
        assert Opcode.CALL_FUNCTION in opcodes  # len()
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("i" in inst.operands for inst in stores)
        assert any("v" in inst.operands for inst in stores)

    @covers(LuaFeature.GENERIC_FOR)
    def test_generic_for_pairs(self):
        source = "for k, v in pairs(t) do print(k, v) end"
        instructions = _parse_lua(source)
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_INDEX in opcodes
        labels = _labels_in_order(instructions)
        assert any("generic_for" in lbl for lbl in labels)

    @covers(LuaFeature.GENERIC_FOR)
    def test_generic_for_single_var(self):
        source = "for item in items() do print(item) end"
        instructions = _parse_lua(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("item" in inst.operands for inst in stores)


class TestLuaFunctionDefinition:
    """Tests for anonymous function definition (function expression)."""

    @covers(LuaFeature.FUNCTION_DECLARATION)
    def test_anonymous_function_expression(self):
        """Anonymous function produces BRANCH, LABEL, RETURN, and func ref CONST."""
        instructions = _parse_lua("local f = function(x) return x end")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        assert Opcode.RETURN in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            str(inst.operands[0]).startswith("func_")
            for inst in consts
            if inst.operands
        )
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("f" in inst.operands for inst in stores)

    @covers(LuaFeature.FUNCTION_DECLARATION)
    def test_anonymous_function_with_params(self):
        """Anonymous function parameters are lowered as SYMBOLIC param:name."""
        instructions = _parse_lua("local cb = function(a, b) return a + b end")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("a" in p for p in param_names)
        assert any("b" in p for p in param_names)

    @covers(LuaFeature.FUNCTION_DECLARATION)
    def test_anonymous_function_as_call_arg(self):
        """Anonymous function passed as argument to a call."""
        instructions = _parse_lua("map(function(x) return x * 2 end, t)")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        assert Opcode.RETURN in opcodes
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("map" in inst.operands for inst in calls)


class TestLuaVarargExpression:
    """Tests for vararg_expression (...)."""

    @covers(LuaFeature.VARARG)
    def test_vararg_produces_symbolic(self):
        """... produces SYMBOLIC('varargs')."""
        instructions = _parse_lua("function f(...) return ... end")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("varargs" in inst.operands for inst in symbolics)

    @covers(LuaFeature.VARARG)
    def test_vararg_in_table_constructor(self):
        """Varargs inside a table constructor."""
        instructions = _parse_lua("function f(...) local t = {...} end")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("varargs" in inst.operands for inst in symbolics)
        assert Opcode.NEW_OBJECT in _opcodes(instructions)


class TestLuaGotoLabel:
    """Tests for goto_statement and label_statement."""

    @covers(LuaFeature.GOTO)
    def test_goto_produces_branch(self):
        """goto label produces a BRANCH instruction."""
        instructions = _parse_lua("goto skip\nprint('hello')\n::skip::")
        branches = _find_all(instructions, Opcode.BRANCH)
        assert any(inst.label == "skip" for inst in branches)

    @covers(LuaFeature.GOTO)
    def test_label_produces_label(self):
        """::name:: produces a LABEL instruction."""
        instructions = _parse_lua("::myLabel::\nprint('here')")
        labels = _find_all(instructions, Opcode.LABEL)
        assert any(inst.label == "myLabel" for inst in labels)

    @covers(LuaFeature.GOTO)
    def test_goto_and_label_together(self):
        """goto + label produces BRANCH and LABEL that match."""
        instructions = _parse_lua("goto done\nprint('skip')\n::done::\nprint('end')")
        branches = _find_all(instructions, Opcode.BRANCH)
        labels = _find_all(instructions, Opcode.LABEL)
        assert any(inst.label == "done" for inst in branches)
        assert any(inst.label == "done" for inst in labels)


class TestLuaStringContentEscapeSequence:
    """Tests for string_content and escape_sequence safety-net mapping."""

    @covers(LuaFeature.STRING_ESCAPE)
    def test_string_content_does_not_produce_symbolic(self):
        """string_content should produce CONST, not SYMBOLIC unsupported."""
        instructions = _parse_lua('local x = "hello"')
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        unsupported = [
            s for s in symbolics if any("unsupported:" in str(op) for op in s.operands)
        ]
        assert len(unsupported) == 0

    @covers(LuaFeature.STRING_ESCAPE)
    def test_escape_sequence_does_not_produce_symbolic(self):
        """escape_sequence should produce CONST, not SYMBOLIC unsupported."""
        instructions = _parse_lua(r'local x = "hello\nworld"')
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        unsupported = [
            s for s in symbolics if any("unsupported:" in str(op) for op in s.operands)
        ]
        assert len(unsupported) == 0


class TestLuaMethodIndexExpression:
    """Tests for method_index_expression (obj:method) lowering."""

    @covers(LuaFeature.METHOD_INDEX_EXPRESSION)
    def test_method_call_produces_call_method(self):
        """obj:method() should produce CALL_METHOD with obj and method name."""
        instructions = _parse_lua("obj:method()")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1
        assert "method" in calls[0].operands

    @covers(LuaFeature.METHOD_INDEX_EXPRESSION)
    def test_method_call_with_args_produces_call_method(self):
        """obj:method(a, b) should produce CALL_METHOD with args."""
        instructions = _parse_lua("obj:method(1, 2)")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1
        assert "method" in calls[0].operands

    @covers(LuaFeature.METHOD_INDEX_EXPRESSION)
    def test_method_call_no_symbolic_fallthrough(self):
        """obj:method() must NOT produce SYMBOLIC unsupported for method_index_expression."""
        instructions = _parse_lua("obj:method()")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        unsupported = [
            s for s in symbolics if any("unsupported:" in str(op) for op in s.operands)
        ]
        assert len(unsupported) == 0

    @covers(LuaFeature.METHOD_INDEX_EXPRESSION)
    def test_chained_method_calls(self):
        """obj:foo():bar() should produce two CALL_METHOD instructions."""
        instructions = _parse_lua("obj:foo():bar()")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 2
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        assert "foo" in method_names
        assert "bar" in method_names

    @covers(LuaFeature.METHOD_INDEX_EXPRESSION)
    def test_method_call_result_stored(self):
        """local r = obj:method() should store result."""
        instructions = _parse_lua("local r = obj:method()")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("r" in inst.operands for inst in stores)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1

    @covers(LuaFeature.METHOD_INDEX_EXPRESSION)
    def test_method_index_in_dispatch_table(self):
        """method_index_expression must be in the expr dispatch table."""
        from interpreter.frontends.lua import LuaFrontend
        from interpreter.parser import TreeSitterParserFactory
        from interpreter.frontends.lua.node_types import LuaNodeType

        frontend = LuaFrontend(TreeSitterParserFactory(), "lua")
        dispatch = frontend._build_expr_dispatch()
        assert LuaNodeType.METHOD_INDEX_EXPRESSION in dispatch


class TestLuaOperatorExecution:
    """VM execution tests for Lua-specific operators."""

    @covers(LuaFeature.OPERATORS)
    def test_concatenation_produces_correct_result(self):
        source = """\
function greet(name)
    return "hello " .. name
end

answer = greet("world")
"""
        vm, stats = execute_for_language("lua", source)
        assert extract_answer(vm, "lua") == "hello world"
        assert stats.llm_calls == 0

    @covers(LuaFeature.OPERATORS)
    def test_length_operator_produces_correct_result(self):
        source = 'answer = #"hello"'
        vm, stats = execute_for_language("lua", source)
        assert extract_answer(vm, "lua") == 5
        assert stats.llm_calls == 0

    @covers(LuaFeature.OPERATORS)
    def test_not_equal_in_while_loop(self):
        source = """\
function countdown(n)
    local count = 0
    while n ~= 0 do
        count = count + 1
        n = n - 1
    end
    return count
end

answer = countdown(7)
"""
        vm, stats = execute_for_language("lua", source)
        assert extract_answer(vm, "lua") == 7
        assert stats.llm_calls == 0


class TestLuaDottedFunctionDeclaration:
    @covers(LuaFeature.DOTTED_FUNCTION_DECLARATION)
    def test_dotted_function_emits_store_field(self):
        """function Counter.new() should emit STORE_FIELD on Counter, not DECL_VAR 'Counter.new'."""
        instructions = _parse_lua("""
Counter = {}
function Counter.new()
    return 1
end
""")
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        func_store = [
            inst
            for inst in store_fields
            if any("new" in str(op) for op in inst.operands)
        ]
        assert (
            len(func_store) >= 1
        ), f"Expected STORE_FIELD for 'new', got {store_fields}"
        decl_vars = _find_all(instructions, Opcode.DECL_VAR)
        dotted = [inst for inst in decl_vars if "Counter.new" in str(inst.operands)]
        assert len(dotted) == 0, f"Should not DECL_VAR 'Counter.new', got {dotted}"

    @covers(LuaFeature.DOTTED_FUNCTION_DECLARATION)
    def test_dotted_function_uses_method_name_only(self):
        """Function label and ref should use 'new', not 'Counter.new'."""
        instructions = _parse_lua("""
Counter = {}
function Counter.new()
    return 1
end
""")
        consts = _find_all(instructions, Opcode.CONST)
        func_refs = [
            inst
            for inst in consts
            if any(str(op).startswith("func_") for op in inst.operands)
        ]
        assert len(func_refs) >= 1
        ref_str = str(func_refs[0].operands[0])
        assert (
            "Counter.new" not in ref_str
        ), f"Func ref should not contain dots: {ref_str}"
        assert ref_str.startswith(
            "func_new_"
        ), f"Func ref should use method name 'new': {ref_str}"

    @covers(LuaFeature.DOTTED_FUNCTION_DECLARATION)
    def test_dotted_function_with_params(self):
        """function Counter.increment(self) should have params AND STORE_FIELD."""
        instructions = _parse_lua("""
Counter = {}
function Counter.increment(self)
    return self
end
""")
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        func_store = [
            inst
            for inst in store_fields
            if any("increment" in str(op) for op in inst.operands)
        ]
        assert len(func_store) >= 1
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any(
            "self" in p for p in param_names
        ), f"Expected param:self, got {param_names}"


class TestLuaDottedFunctionCall:
    @covers(LuaFeature.DOTTED_FUNCTION_CALL)
    def test_dotted_call_emits_load_field_and_call_unknown(self):
        """Counter.increment(x) should emit LOAD_FIELD + CALL_UNKNOWN, not CALL_METHOD."""
        instructions = _parse_lua("Counter.increment(x)")
        load_fields = _find_all(instructions, Opcode.LOAD_FIELD)
        field_loads = [
            inst for inst in load_fields if "increment" in str(inst.operands)
        ]
        assert (
            len(field_loads) >= 1
        ), f"Expected LOAD_FIELD 'increment', got {load_fields}"
        call_unknowns = _find_all(instructions, Opcode.CALL_UNKNOWN)
        assert len(call_unknowns) >= 1, f"Expected CALL_UNKNOWN, got none"
        call_methods = _find_all(instructions, Opcode.CALL_METHOD)
        dotted_methods = [
            inst for inst in call_methods if "increment" in str(inst.operands)
        ]
        assert (
            len(dotted_methods) == 0
        ), f"Should not emit CALL_METHOD for dot call: {dotted_methods}"

    @covers(LuaFeature.DOTTED_FUNCTION_CALL)
    def test_dotted_call_with_multiple_args(self):
        """Counter.add(a, b) should pass both args to CALL_UNKNOWN."""
        instructions = _parse_lua("Counter.add(a, b)")
        call_unknowns = _find_all(instructions, Opcode.CALL_UNKNOWN)
        assert len(call_unknowns) >= 1
        assert len(call_unknowns[0].operands) >= 3, "Should have func + 2 args"

    @covers(LuaFeature.METHOD_CALL)
    def test_colon_call_still_emits_call_method(self):
        """obj:method() should still use CALL_METHOD (unchanged)."""
        instructions = _parse_lua("obj:method()")
        call_methods = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(call_methods) >= 1, "Colon syntax should still emit CALL_METHOD"

    @covers(LuaFeature.DOTTED_FUNCTION_CALL)
    def test_chained_dotted_calls(self):
        """Multiple consecutive dotted calls each produce LOAD_FIELD + CALL_UNKNOWN."""
        instructions = _parse_lua("Counter.a(x)\nCounter.b(y)")
        load_fields = _find_all(instructions, Opcode.LOAD_FIELD)
        field_names = [
            inst.operands[1] for inst in load_fields if len(inst.operands) >= 2
        ]
        assert "a" in field_names, f"Expected LOAD_FIELD 'a', got {field_names}"
        assert "b" in field_names, f"Expected LOAD_FIELD 'b', got {field_names}"
        call_unknowns = _find_all(instructions, Opcode.CALL_UNKNOWN)
        assert (
            len(call_unknowns) >= 2
        ), f"Expected 2 CALL_UNKNOWN, got {len(call_unknowns)}"


class TestLuaNumberLiterals:
    """Tests for int-vs-float NUMBER literal classification."""

    @covers(LuaFeature.ARITHMETIC)
    def test_integer_decimal_emits_int_const(self):
        """Plain decimal integer -> typed int CONST."""
        instructions = _parse_lua("local x = 42")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            op == 42 for inst in consts for op in inst.operands
        ), f"Expected int 42 in CONST operands, got {[c.operands for c in consts]}"

    @covers(LuaFeature.ARITHMETIC)
    def test_hex_integer_emits_int_const(self):
        """Hex integer 0xFF -> typed int CONST with value 255."""
        instructions = _parse_lua("local x = 0xFF")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            op == 255 for inst in consts for op in inst.operands
        ), f"Expected int 255 in CONST operands, got {[c.operands for c in consts]}"

    @covers(LuaFeature.ARITHMETIC)
    def test_decimal_float_emits_float_const(self):
        """Decimal float 3.14 -> typed float CONST."""
        instructions = _parse_lua("local x = 3.14")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            abs(op - 3.14) < 1e-9
            for inst in consts
            for op in inst.operands
            if isinstance(op, float)
        ), f"Expected float ~3.14 in CONST operands, got {[c.operands for c in consts]}"

    @covers(LuaFeature.ARITHMETIC)
    def test_trailing_dot_float_emits_float_const(self):
        """Trailing-dot float 3. -> typed float CONST with value 3.0."""
        instructions = _parse_lua("local x = 3.")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            op == 3.0 and isinstance(op, float)
            for inst in consts
            for op in inst.operands
        ), f"Expected float 3.0 in CONST operands, got {[c.operands for c in consts]}"

    @covers(LuaFeature.ARITHMETIC)
    def test_exponent_float_emits_float_const(self):
        """Scientific notation 1e5 -> typed float CONST with value 100000.0."""
        instructions = _parse_lua("local x = 1e5")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            op == 100000.0 and isinstance(op, float)
            for inst in consts
            for op in inst.operands
        ), f"Expected float 100000.0 in CONST operands, got {[c.operands for c in consts]}"

    @covers(LuaFeature.ARITHMETIC)
    def test_hex_float_emits_float_const(self):
        """Hex float 0x1p4 -> typed float CONST with value 16.0."""
        instructions = _parse_lua("local x = 0x1p4")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            op == 16.0 and isinstance(op, float)
            for inst in consts
            for op in inst.operands
        ), f"Expected float 16.0 in CONST operands, got {[c.operands for c in consts]}"


class TestLuaStringLiterals:
    """Tests for string literal forms including long bracket strings."""

    @covers(LuaFeature.STRING_ESCAPE)
    def test_double_quoted_string(self):
        """Double-quoted string strips quotes correctly."""
        instructions = _parse_lua('local x = "hello"')
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            op == "hello" for inst in consts for op in inst.operands
        ), f"Expected string 'hello' in CONST operands, got {[c.operands for c in consts]}"

    @covers(LuaFeature.STRING_ESCAPE)
    def test_single_quoted_string(self):
        """Single-quoted string strips quotes correctly."""
        instructions = _parse_lua("local x = 'world'")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            op == "world" for inst in consts for op in inst.operands
        ), f"Expected string 'world' in CONST operands, got {[c.operands for c in consts]}"

    @covers(LuaFeature.STRING_ESCAPE)
    def test_long_bracket_double_bracket(self):
        """[[...]] long bracket string strips delimiters."""
        instructions = _parse_lua("local x = [[hello world]]")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            op == "hello world" for inst in consts for op in inst.operands
        ), f"Expected string 'hello world' in CONST operands, got {[c.operands for c in consts]}"

    @covers(LuaFeature.STRING_ESCAPE)
    def test_long_bracket_single_equals(self):
        """[=[...]=] long bracket with one = strips delimiters."""
        instructions = _parse_lua("local x = [=[foo bar]=]")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            op == "foo bar" for inst in consts for op in inst.operands
        ), f"Expected string 'foo bar' in CONST operands, got {[c.operands for c in consts]}"

    @covers(LuaFeature.STRING_ESCAPE)
    def test_escape_newline_in_string(self):
        """String with \\n escape produces actual newline in the string value."""
        # Lua "a\nb" should unescape \n to an actual newline character
        instructions = _parse_lua('local x = "a\\nb"')
        consts = _find_all(instructions, Opcode.CONST)
        assert any(
            isinstance(op, str) and "\n" in op
            for inst in consts
            for op in inst.operands
        ), f"Expected string with newline in CONST operands, got {[c.operands for c in consts]}"


class TestLuaBitwiseXor:
    """Lua uses ~ for bitwise XOR; VM BINOP_TABLE must handle it."""

    @covers(LuaFeature.BITWISE_XOR)
    def test_tilde_xor_emits_binop(self):
        ir = _parse_lua("""\
a = 8
b = a ~ 5
""")
        binops = _find_all(ir, Opcode.BINOP)
        assert any(
            "~" in inst.operands for inst in binops
        ), "Expected BINOP with '~' for Lua XOR operator"

    @covers(LuaFeature.BITWISE_XOR)
    def test_tilde_xor_execution(self):
        """Lua ~ XOR produces correct result through VM."""
        vm, stats = execute_for_language(
            "lua",
            """\
a = 12
b = 10
c = a & b
answer = c ~ 5
""",
        )
        assert extract_answer(vm, "lua") == 13
        assert stats.llm_calls == 0


class TestLuaImplicitReturn:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_trailing_return_is_marked_implicit(self):
        instructions = _parse_lua("function f() return 42 end")
        returns = _find_all(instructions, Opcode.RETURN)
        # The synthetic fall-off-the-end return is marked implicit.
        assert any(r.implicit for r in returns)
        # The explicit `return 42` is NOT marked implicit.
        assert any(not r.implicit for r in returns)
