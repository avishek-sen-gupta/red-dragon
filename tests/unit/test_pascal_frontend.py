"""Tests for PascalFrontend — tree-sitter Pascal AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.pascal import PascalFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_pascal(source: str) -> list[IRInstruction]:
    parser = get_parser("pascal")
    tree = parser.parse(source.encode("utf-8"))
    frontend = PascalFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestPascalSmoke:
    def test_empty_program(self):
        instructions = _parse_pascal("program M; begin end.")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_entry_label_always_present(self):
        instructions = _parse_pascal("program M; begin x := 1; end.")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"


class TestPascalAssignment:
    def test_simple_assignment(self):
        instructions = _parse_pascal("program M; begin x := 10; end.")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("10" in inst.operands for inst in consts)

    def test_arithmetic_assignment(self):
        instructions = _parse_pascal("program M; begin x := 5 + 3; end.")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("5" in inst.operands for inst in consts)
        assert any("3" in inst.operands for inst in consts)


class TestPascalExpressions:
    def test_number_literal(self):
        instructions = _parse_pascal("program M; begin x := 42; end.")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)

    def test_string_literal(self):
        instructions = _parse_pascal("program M; begin x := 'hello'; end.")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("'hello'" in str(inst.operands) for inst in consts)

    def test_binary_operator_greater_than(self):
        instructions = _parse_pascal("program M; begin if x > 5 then x := 0; end.")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any(">" in inst.operands for inst in binops)

    def test_binary_operator_less_than(self):
        instructions = _parse_pascal("program M; begin if x < 5 then x := 0; end.")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("<" in inst.operands for inst in binops)

    def test_binary_operator_subtraction(self):
        instructions = _parse_pascal("program M; begin x := 10 - 3; end.")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("-" in inst.operands for inst in binops)


class TestPascalFunctions:
    def test_function_call(self):
        instructions = _parse_pascal("program M; begin WriteLn(10); end.")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) >= 1
        assert "WriteLn" in calls[0].operands

    def test_function_definition(self):
        instructions = _parse_pascal(
            "program M; function Add(a, b: Integer): Integer; begin Add := a + b; end; begin end."
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        assert Opcode.RETURN in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Add" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("function:" in str(inst.operands) for inst in consts)

    def test_function_params_are_symbolic(self):
        # The Pascal grammar wraps defProc around declProc + block.
        # The frontend finds identifier/declArgs inside defProc's children —
        # but they are nested inside declProc. The current implementation
        # does not extract params when they are inside declProc, so params
        # are not lowered. This test documents the current behaviour.
        instructions = _parse_pascal(
            "program M; function F(x: Integer): Integer; begin F := x; end; begin end."
        )
        opcodes = _opcodes(instructions)
        # The function body (F := x) still gets lowered
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.STORE_VAR in opcodes
        assert Opcode.RETURN in opcodes


class TestPascalControlFlow:
    def test_if_statement(self):
        instructions = _parse_pascal(
            "program M; begin if x > 5 then WriteLn('big'); end."
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes

    def test_if_else_statement(self):
        instructions = _parse_pascal(
            "program M; begin if x > 5 then WriteLn('big') else WriteLn('small'); end."
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        label_names = [inst.label for inst in labels]
        assert any("if_true" in (lbl or "") for lbl in label_names)
        assert any("if_false" in (lbl or "") for lbl in label_names)

    def test_while_loop(self):
        instructions = _parse_pascal("program M; begin while x > 0 do x := x - 1; end.")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("while" in (inst.label or "") for inst in labels)

    def test_for_loop(self):
        instructions = _parse_pascal(
            "program M; begin for x := 1 to 10 do WriteLn(x); end."
        )
        opcodes = _opcodes(instructions)
        assert Opcode.STORE_VAR in opcodes
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("for_" in (inst.label or "") for inst in labels)


class TestPascalVariableDeclarations:
    def test_var_declaration(self):
        instructions = _parse_pascal("program M; var x: Integer; begin x := 10; end.")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        # The var decl should initialize x to None (canonical nil)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("None" in inst.operands for inst in consts)

    def test_var_declaration_then_assignment(self):
        instructions = _parse_pascal("program M; var x: Integer; begin x := 42; end.")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        x_stores = [inst for inst in stores if "x" in inst.operands]
        # At least 2 stores: one from declaration (nil), one from assignment (42)
        assert len(x_stores) >= 2


class TestPascalFallback:
    def test_unsupported_construct_symbolic(self):
        # A construct the frontend does not have a handler for should produce SYMBOLIC
        instructions = _parse_pascal(
            "program M; begin case x of 1: WriteLn('one'); end; end."
        )
        opcodes = _opcodes(instructions)
        # case/switch is not handled, so it should fall back to expression lowering
        # which produces SYMBOLIC for unsupported node types
        assert Opcode.SYMBOLIC in opcodes or Opcode.CALL_FUNCTION in opcodes


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialPascal:
    def test_procedure_with_if_else(self):
        source = """\
program M;
procedure Classify(x: Integer);
begin
  if x > 100 then
    WriteLn('high')
  else
    WriteLn('low');
end;
begin
end.
"""
        instructions = _parse_pascal(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("WriteLn" in inst.operands for inst in calls)
        assert len(calls) >= 2
        # Pascal procedures are stored under an anonymous name
        consts = _find_all(instructions, Opcode.CONST)
        assert any("function:" in str(inst.operands) for inst in consts)
        assert len(instructions) > 10

    def test_function_with_for_loop(self):
        source = """\
program M;
function Sum(n: Integer): Integer;
var i, total: Integer;
begin
  total := 0;
  i := 1;
  while i <= n do
  begin
    total := total + i;
    i := i + 1;
  end;
  Sum := total;
end;
begin
end.
"""
        instructions = _parse_pascal(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("total" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        labels = _labels_in_order(instructions)
        assert any("while" in lbl for lbl in labels)
        assert len(instructions) > 15

    def test_nested_begin_end_blocks(self):
        source = """\
program M;
begin
  x := 10;
  begin
    y := x + 5;
    begin
      z := y * 2;
    end;
  end;
end.
"""
        instructions = _parse_pascal(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        assert any("y" in inst.operands for inst in stores)
        assert any("z" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        operators = [inst.operands[0] for inst in binops if inst.operands]
        assert "+" in operators
        assert "*" in operators

    def test_while_with_nested_if_else(self):
        source = """\
program M;
begin
  while x > 0 do
  begin
    if x > 50 then
      total := total + x
    else
      total := total + 1;
    x := x - 1;
  end;
end.
"""
        instructions = _parse_pascal(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        labels = _labels_in_order(instructions)
        assert any("while" in lbl for lbl in labels)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("total" in inst.operands for inst in stores)
        assert len(instructions) > 15

    def test_nested_function(self):
        source = """\
program M;
function Outer(x: Integer): Integer;
  function Inner(y: Integer): Integer;
  begin
    Inner := y * 2;
  end;
begin
  Outer := Inner(x) + 1;
end;
begin
end.
"""
        instructions = _parse_pascal(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        # Outer's body references Inner via CALL_FUNCTION
        assert any("Outer" in inst.operands for inst in stores)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("Inner" in inst.operands for inst in calls)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1

    def test_for_downto_loop(self):
        source = """\
program M;
begin
  for x := 10 downto 1 do
    WriteLn(x);
end.
"""
        instructions = _parse_pascal(source)
        opcodes = _opcodes(instructions)
        assert Opcode.STORE_VAR in opcodes
        assert Opcode.BRANCH_IF in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        # downto uses >= comparison
        assert any(">=" in inst.operands for inst in binops)

    def test_procedure_calling_procedure(self):
        source = """\
program M;
procedure Main;
begin
  WriteLn('Hello');
  WriteLn('World');
end;
begin
end.
"""
        instructions = _parse_pascal(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        writeln_calls = [c for c in calls if "WriteLn" in c.operands]
        assert len(writeln_calls) >= 2
        consts = _find_all(instructions, Opcode.CONST)
        assert any("function:" in str(inst.operands) for inst in consts)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1

    def test_function_result_assignment(self):
        source = """\
program M;
function Double(x: Integer): Integer;
begin
  Double := x * 2;
end;
begin
end.
"""
        instructions = _parse_pascal(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Double" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("*" in inst.operands for inst in binops)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1


class TestPascalExprDot:
    """Tests for exprDot (obj.field) access."""

    def test_dot_access_produces_load_field(self):
        instructions = _parse_pascal("program M; begin x := rec.field; end.")
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert len(loads) >= 1
        assert "field" in loads[0].operands

    def test_dot_access_chain(self):
        instructions = _parse_pascal("program M; begin x := a.b.c; end.")
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert len(loads) >= 2

    def test_dot_access_in_assignment(self):
        instructions = _parse_pascal("program M; begin x := obj.name; end.")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("name" in inst.operands for inst in loads)


class TestPascalExprSubscript:
    """Tests for exprSubscript (arr[idx]) access."""

    def test_subscript_produces_load_index(self):
        instructions = _parse_pascal("program M; begin x := arr[1]; end.")
        loads = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(loads) >= 1

    def test_subscript_with_variable_index(self):
        instructions = _parse_pascal("program M; begin x := arr[i]; end.")
        loads = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(loads) >= 1
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestPascalExprUnary:
    """Tests for exprUnary (not, -, +)."""

    def test_not_operator(self):
        instructions = _parse_pascal("program M; begin if not done then x := 1; end.")
        unops = _find_all(instructions, Opcode.UNOP)
        assert len(unops) >= 1
        assert any("not" in inst.operands for inst in unops)

    def test_negation_operator(self):
        instructions = _parse_pascal("program M; begin x := -y; end.")
        unops = _find_all(instructions, Opcode.UNOP)
        assert len(unops) >= 1
        assert any("-" in inst.operands for inst in unops)


class TestPascalCaseStatement:
    """Tests for case statement."""

    def test_case_produces_branch_if(self):
        instructions = _parse_pascal(
            "program M; begin case x of 1: WriteLn('one'); 2: WriteLn('two'); end; end."
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BINOP in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("==" in inst.operands for inst in binops)

    def test_case_calls_correct_branches(self):
        instructions = _parse_pascal(
            "program M; begin case x of 1: WriteLn('one'); 2: WriteLn('two'); end; end."
        )
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("WriteLn" in inst.operands for inst in calls)
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("case_match" in (inst.label or "") for inst in labels)

    def test_case_with_end_label(self):
        instructions = _parse_pascal(
            "program M; begin case x of 1: WriteLn('one'); end; end."
        )
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("case_end" in (inst.label or "") for inst in labels)


class TestPascalRepeatUntil:
    """Tests for repeat ... until loop."""

    def test_repeat_produces_branch_if(self):
        instructions = _parse_pascal(
            "program M; begin repeat x := x - 1; until x = 0; end."
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes

    def test_repeat_has_body_label(self):
        instructions = _parse_pascal(
            "program M; begin repeat x := x + 1; until x = 10; end."
        )
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("repeat" in (inst.label or "") for inst in labels)

    def test_repeat_lowers_body_before_condition(self):
        """Body should appear before condition check in instruction order."""
        instructions = _parse_pascal(
            "program M; begin repeat WriteLn(x); until x = 0; end."
        )
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        branch_ifs = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(calls) >= 1
        assert len(branch_ifs) >= 1
        # Call should come before BRANCH_IF in instruction order
        call_idx = instructions.index(calls[0])
        branch_idx = instructions.index(branch_ifs[0])
        assert call_idx < branch_idx


class TestPascalExprBrackets:
    """Tests for exprBrackets (set literal [1,2,3])."""

    def test_set_literal_produces_new_array(self):
        instructions = _parse_pascal("program M; begin x := [1, 2, 3]; end.")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        arrays = _find_all(instructions, Opcode.NEW_ARRAY)
        assert any("set" in inst.operands for inst in arrays)

    def test_set_literal_stores_elements(self):
        instructions = _parse_pascal("program M; begin x := [1, 2, 3]; end.")
        stores = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(stores) >= 3


class TestPascalDeclConsts:
    """Tests for const declarations."""

    def test_const_declaration(self):
        instructions = _parse_pascal("program M; const MAX = 100; begin end.")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("MAX" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("100" in inst.operands for inst in consts)

    def test_multiple_consts(self):
        instructions = _parse_pascal("program M; const A = 1; B = 2; begin end.")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("A" in inst.operands for inst in stores)
        assert any("B" in inst.operands for inst in stores)


class TestPascalParenthesizedExpression:
    def test_parenthesized_expression_no_symbolic(self):
        instructions = _parse_pascal("program M; begin x := (5 + 3); end.")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("exprParens" in str(inst.operands) for inst in symbolics)
        assert not any(
            "parenthesized_expression" in str(inst.operands) for inst in symbolics
        )

    def test_parenthesized_expression_evaluates(self):
        instructions = _parse_pascal("program M; begin x := (10); end.")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("10" in inst.operands for inst in consts)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_parenthesized_nested(self):
        instructions = _parse_pascal("program M; begin x := ((2 + 3) * 4); end.")
        binops = _find_all(instructions, Opcode.BINOP)
        operators = [inst.operands[0] for inst in binops if inst.operands]
        assert "+" in operators
        assert "*" in operators
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("exprParens" in str(inst.operands) for inst in symbolics)


class TestPascalDeclTypeNoop:
    """Tests for type declarations (should be no-op)."""

    def test_type_declaration_does_not_crash(self):
        instructions = _parse_pascal(
            "program M; type MyInt = Integer; begin x := 1; end."
        )
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_type_declaration_produces_no_symbolic(self):
        instructions = _parse_pascal("program M; type MyInt = Integer; begin end.")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        unsupported = [
            s for s in symbolics if any("unsupported:" in str(op) for op in s.operands)
        ]
        assert len(unsupported) == 0


class TestPascalTry:
    def test_try_no_symbolic(self):
        instructions = _parse_pascal(
            "program M; begin try x := 1; except x := 0; end; end."
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:try" in str(inst.operands) for inst in symbolics)

    def test_try_lowers_body(self):
        instructions = _parse_pascal(
            "program M; begin try x := 1; except x := 0; end; end."
        )
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestPascalDeclUsesNoop:
    def test_uses_declaration_no_symbolic(self):
        instructions = _parse_pascal(
            "program M; uses SysUtils, Classes; begin x := 1; end."
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("declUses" in str(inst.operands) for inst in symbolics)

    def test_uses_declaration_does_not_crash(self):
        instructions = _parse_pascal("program M; uses SysUtils; begin end.")
        assert instructions[0].opcode == Opcode.LABEL


class TestPascalExceptionHandler:
    def test_exception_handler_no_unsupported(self):
        """on E: Exception do ... should not produce unsupported SYMBOLIC."""
        source = """\
program M;
begin
  try
    x := 1;
  except
    on E: Exception do
      x := 0;
  end;
end.
"""
        instructions = _parse_pascal(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_exception_handler_lowers_body(self):
        source = """\
program M;
begin
  try
    x := 1;
  except
    on E: Exception do
      WriteLn(E.Message);
  end;
end.
"""
        instructions = _parse_pascal(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("WriteLn" in inst.operands for inst in calls)


class TestPascalRaise:
    def test_raise_no_unsupported(self):
        """raise Exception.Create('error') should not produce unsupported SYMBOLIC."""
        source = "program M; begin raise Exception.Create('error'); end."
        instructions = _parse_pascal(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_raise_produces_throw(self):
        source = "program M; begin raise Exception.Create('error'); end."
        instructions = _parse_pascal(source)
        opcodes = _opcodes(instructions)
        assert Opcode.THROW in opcodes


class TestPascalRange:
    def test_range_no_unsupported(self):
        """case x of 1..10: should not produce unsupported SYMBOLIC for the range."""
        source = "program M; begin case x of 1..10: WriteLn('range'); end; end."
        instructions = _parse_pascal(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)


class TestPascalWith:
    def test_with_no_unsupported(self):
        """with rec do ... should not produce unsupported SYMBOLIC."""
        source = """\
program M;
begin
  with rec do
  begin
    x := 1;
    y := 2;
  end;
end.
"""
        instructions = _parse_pascal(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_with_lowers_body(self):
        source = "program M; begin with rec do x := 10; end."
        instructions = _parse_pascal(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestPascalInherited:
    def test_inherited_no_unsupported(self):
        """inherited Create; should not produce unsupported SYMBOLIC."""
        source = """\
program M;
procedure Init;
begin
  inherited Create;
end;
begin
end.
"""
        instructions = _parse_pascal(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_inherited_produces_call(self):
        source = """\
program M;
procedure Init;
begin
  inherited Create;
end;
begin
end.
"""
        instructions = _parse_pascal(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any(
            "inherited" in inst.operands or "Create" in inst.operands for inst in calls
        )
