"""Tests for RubyFrontend — tree-sitter Ruby AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.ruby import RubyFrontend
from interpreter.ir import IRInstruction, Opcode
from tests.unit.rosetta.conftest import execute_for_language, extract_answer


def _parse_ruby(source: str) -> list[IRInstruction]:
    parser = get_parser("ruby")
    tree = parser.parse(source.encode("utf-8"))
    frontend = RubyFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestRubySmoke:
    def test_empty_program(self):
        instructions = _parse_ruby("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_integer_literal(self):
        instructions = _parse_ruby("42")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)


class TestRubyVariables:
    def test_variable_assignment(self):
        instructions = _parse_ruby("x = 10")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_instance_variable_assignment(self):
        instructions = _parse_ruby("@name = 'hello'")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("@name" in inst.operands for inst in stores)

    def test_augmented_assignment(self):
        instructions = _parse_ruby("x += 1")
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestRubyExpressions:
    def test_arithmetic(self):
        instructions = _parse_ruby("y = x + 5")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_string_literal(self):
        instructions = _parse_ruby('s = "hello world"')
        consts = _find_all(instructions, Opcode.CONST)
        assert any('"hello world"' in inst.operands for inst in consts)


class TestRubyControlFlow:
    def test_if_elsif_else(self):
        source = """
if x > 10
  y = 1
elsif x > 5
  y = 2
else
  y = 0
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        assert Opcode.BRANCH in opcodes
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2

    def test_unless(self):
        source = """
unless x > 0
  y = -1
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.UNOP in opcodes
        assert Opcode.BRANCH_IF in opcodes
        unops = _find_all(instructions, Opcode.UNOP)
        assert any("!" in inst.operands for inst in unops)

    def test_while_loop(self):
        source = """
while x > 0
  x = x - 1
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("while" in (inst.label or "") for inst in labels)

    def test_until_loop(self):
        source = """
until x <= 0
  x = x - 1
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.UNOP in opcodes
        assert Opcode.BRANCH_IF in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("until" in (inst.label or "") for inst in labels)


class TestRubyMethods:
    def test_method_definition(self):
        source = """
def add(a, b)
  a + b
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("add" in inst.operands for inst in stores)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("a" in p for p in param_names)
        assert any("b" in p for p in param_names)

    def test_method_call_standalone(self):
        instructions = _parse_ruby("add(1, 2)")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) >= 1
        assert "add" in calls[0].operands

    def test_method_call_with_receiver(self):
        instructions = _parse_ruby("obj.bark")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1
        assert "bark" in calls[0].operands

    def test_method_call_with_receiver_and_args(self):
        instructions = _parse_ruby("obj.send(1, 2)")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1
        assert "send" in calls[0].operands

    def test_return_statement(self):
        source = """
def foo
  return 42
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes


class TestRubyClasses:
    def test_class_definition(self):
        source = """
class Dog
  def bark
    "woof"
  end
end
"""
        instructions = _parse_ruby(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

    def test_class_with_constructor(self):
        source = """
class Dog
  def initialize(name)
    @name = name
  end
end
"""
        instructions = _parse_ruby(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        assert any("@name" in inst.operands for inst in stores)


class TestRubySpecial:
    def test_array_literal(self):
        instructions = _parse_ruby("arr = [1, 2, 3]")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.STORE_INDEX in opcodes

    def test_hash_literal(self):
        instructions = _parse_ruby("h = {a: 1, b: 2}")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes

    def test_fallback_symbolic_for_unsupported(self):
        instructions = _parse_ruby("BEGIN { puts 'start' }")
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialRuby:
    def test_unless_with_early_return(self):
        source = """\
def validate(x)
  unless x > 0
    return -1
  end
  x * 2
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.UNOP in opcodes
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.RETURN in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("validate" in inst.operands for inst in stores)

    def test_until_loop_with_mutation(self):
        source = """\
x = 100
total = 0
until x <= 0
  total += x
  x -= 10
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.UNOP in opcodes
        assert Opcode.BRANCH_IF in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("total" in inst.operands for inst in stores)
        assert any("x" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        assert any("-" in inst.operands for inst in binops)
        assert len(instructions) > 15

    def test_elsif_chain(self):
        source = """\
if score > 90
  grade = 'A'
elsif score > 80
  grade = 'B'
elsif score > 70
  grade = 'C'
else
  grade = 'F'
end
"""
        instructions = _parse_ruby(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 3
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("grade" in inst.operands for inst in stores)
        labels = _labels_in_order(instructions)
        assert len(labels) >= 4

    def test_class_with_initialize_and_method(self):
        source = """\
class Counter
  def initialize(start)
    @count = start
  end
  def increment
    @count = @count + 1
  end
  def value
    @count
  end
end
"""
        instructions = _parse_ruby(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Counter" in inst.operands for inst in stores)
        assert any("@count" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        assert len(instructions) > 20

    def test_hash_with_symbol_keys(self):
        source = """\
config = {name: 'app', version: 2, debug: true}
val = config[:name]
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("config" in inst.operands for inst in stores)
        assert any("val" in inst.operands for inst in stores)

    def test_while_with_nested_if_else(self):
        source = """\
count = 0
sum = 0
while count < 20
  if count % 2 == 0
    sum += count
  else
    sum -= 1
  end
  count += 1
end
"""
        instructions = _parse_ruby(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        labels = _labels_in_order(instructions)
        assert any("while" in lbl for lbl in labels)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("sum" in inst.operands for inst in stores)
        assert any("count" in inst.operands for inst in stores)
        assert len(instructions) > 20

    def test_method_chaining_on_array(self):
        source = """\
result = items.select { |x| x > 0 }.map { |x| x * 2 }.first
"""
        instructions = _parse_ruby(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)

    def test_block_call_with_do_end(self):
        source = """\
items.each do |item|
  puts item
end
"""
        instructions = _parse_ruby(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("each" in inst.operands for inst in calls)
        # Block is lowered as inline closure — expect RETURN and func: CONST
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any("func:" in str(inst.operands) for inst in consts)

    def test_block_curly_brace(self):
        source = "items.map { |x| x * 2 }"
        instructions = _parse_ruby(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("map" in inst.operands for inst in calls)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("func:" in str(inst.operands) for inst in consts)

    def test_do_block(self):
        source = """\
numbers.select do |n|
  n > 0
end
"""
        instructions = _parse_ruby(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("select" in inst.operands for inst in calls)
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes

    def test_block_no_params(self):
        source = "3.times { puts 'hello' }"
        instructions = _parse_ruby(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("times" in inst.operands for inst in calls)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("func:" in str(inst.operands) for inst in consts)

    def test_block_body_lowered(self):
        source = """\
items.each do |item|
  result = item + 1
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)


class TestRubySimpleSymbol:
    def test_simple_symbol(self):
        instructions = _parse_ruby("x = :hello")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(":hello" in inst.operands for inst in consts)

    def test_simple_symbol_in_call(self):
        instructions = _parse_ruby("foo(:bar)")
        consts = _find_all(instructions, Opcode.CONST)
        assert any(":bar" in inst.operands for inst in consts)

    def test_simple_symbol_stores(self):
        instructions = _parse_ruby("sym = :world")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("sym" in inst.operands for inst in stores)


class TestRubyRange:
    def test_range_inclusive(self):
        instructions = _parse_ruby("r = 1..10")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("range" in inst.operands for inst in calls)

    def test_range_exclusive(self):
        instructions = _parse_ruby("r = 1...10")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("range" in inst.operands for inst in calls)

    def test_range_stores_result(self):
        instructions = _parse_ruby("rng = 0..5")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("rng" in inst.operands for inst in stores)


class TestRubyRegex:
    def test_regex_literal(self):
        instructions = _parse_ruby("pat = /hello/")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("/hello/" in inst.operands for inst in consts)

    def test_regex_stores(self):
        instructions = _parse_ruby("re = /[0-9]+/")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("re" in inst.operands for inst in stores)


class TestRubyLambda:
    def test_lambda_basic(self):
        instructions = _parse_ruby("f = -> { 42 }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("function:" in str(inst.operands) for inst in consts)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("f" in inst.operands for inst in stores)

    def test_lambda_with_params(self):
        instructions = _parse_ruby("f = ->(x, y) { x + y }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("function:" in str(inst.operands) for inst in consts)
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes

    def test_lambda_has_return(self):
        instructions = _parse_ruby("f = -> { 1 }")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes


class TestRubyStringArray:
    def test_string_array(self):
        instructions = _parse_ruby("arr = %w[foo bar baz]")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.STORE_INDEX in opcodes

    def test_symbol_array(self):
        instructions = _parse_ruby("syms = %i[a b c]")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.STORE_INDEX in opcodes

    def test_string_array_stores(self):
        instructions = _parse_ruby("words = %w[hello world]")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("words" in inst.operands for inst in stores)


class TestRubyCase:
    def test_case_with_when(self):
        source = """\
case x
when 1
  y = 10
when 2
  y = 20
else
  y = 0
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)

    def test_case_produces_binop_eq(self):
        source = """\
case val
when 1
  a = 1
when 2
  a = 2
end
"""
        instructions = _parse_ruby(source)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("==" in inst.operands for inst in binops)

    def test_case_labels(self):
        source = """\
case x
when :a
  1
when :b
  2
end
"""
        instructions = _parse_ruby(source)
        labels = _labels_in_order(instructions)
        assert any("when" in lbl for lbl in labels)
        assert any("case_end" in lbl for lbl in labels)


class TestRubyModule:
    def test_module_definition(self):
        source = """\
module Greeter
  def greet
    "hello"
  end
end
"""
        instructions = _parse_ruby(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Greeter" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

    def test_module_labels(self):
        source = """\
module Utils
  def helper
    nil
  end
end
"""
        instructions = _parse_ruby(source)
        labels = _labels_in_order(instructions)
        assert any("class_Utils" in lbl for lbl in labels)

    def test_module_with_method(self):
        source = """\
module Math
  def add(a, b)
    a + b
  end
end
"""
        instructions = _parse_ruby(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Math" in inst.operands for inst in stores)
        assert any("add" in inst.operands for inst in stores)
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes


class TestRubyGlobalVariable:
    def test_global_variable_load(self):
        instructions = _parse_ruby("x = $count")
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("$count" in inst.operands for inst in loads)

    def test_global_variable_store(self):
        instructions = _parse_ruby("$count = 10")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("$count" in inst.operands for inst in stores)

    def test_global_variable_in_expression(self):
        instructions = _parse_ruby("y = $x + 1")
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("$x" in inst.operands for inst in loads)


class TestRubyClassVariable:
    def test_class_variable_load(self):
        instructions = _parse_ruby("x = @@count")
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("@@count" in inst.operands for inst in loads)

    def test_class_variable_store(self):
        instructions = _parse_ruby("@@count = 0")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("@@count" in inst.operands for inst in stores)

    def test_class_variable_in_class(self):
        source = """\
class Foo
  @@total = 0
end
"""
        instructions = _parse_ruby(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("@@total" in inst.operands for inst in stores)


class TestRubyHeredoc:
    def test_heredoc_body(self):
        source = "x = <<~HEREDOC\nhello world\nHEREDOC"
        instructions = _parse_ruby(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_heredoc_const(self):
        source = "msg = <<~TEXT\nsome text\nTEXT"
        instructions = _parse_ruby(source)
        consts = _find_all(instructions, Opcode.CONST)
        # heredoc body should appear as a CONST
        assert len(consts) >= 1


class TestRubyIfModifier:
    def test_if_modifier_basic(self):
        instructions = _parse_ruby("x = 1 if condition")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        labels = _labels_in_order(instructions)
        assert any("ifmod" in lbl for lbl in labels)

    def test_if_modifier_produces_store(self):
        instructions = _parse_ruby("x = 1 if true")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_if_modifier_with_method_call(self):
        instructions = _parse_ruby("puts x if x > 0")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("puts" in inst.operands for inst in calls)


class TestRubyUnlessModifier:
    def test_unless_modifier_basic(self):
        instructions = _parse_ruby("x = 1 unless condition")
        opcodes = _opcodes(instructions)
        assert Opcode.UNOP in opcodes
        assert Opcode.BRANCH_IF in opcodes
        labels = _labels_in_order(instructions)
        assert any("unlessmod" in lbl for lbl in labels)

    def test_unless_modifier_negates_condition(self):
        instructions = _parse_ruby("y = 0 unless flag")
        unops = _find_all(instructions, Opcode.UNOP)
        assert any("!" in inst.operands for inst in unops)

    def test_unless_modifier_produces_store(self):
        instructions = _parse_ruby("result = 42 unless done")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)


class TestRubyWhileModifier:
    def test_while_modifier_basic(self):
        instructions = _parse_ruby("x += 1 while x < 10")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        labels = _labels_in_order(instructions)
        assert any("whilemod" in lbl for lbl in labels)

    def test_while_modifier_has_loop_back(self):
        instructions = _parse_ruby("x += 1 while x < 10")
        branches = _find_all(instructions, Opcode.BRANCH)
        labels = _labels_in_order(instructions)
        cond_labels = [lbl for lbl in labels if "whilemod_cond" in lbl]
        assert any(b.label in cond_labels for b in branches)

    def test_while_modifier_produces_binop(self):
        instructions = _parse_ruby("x += 1 while x < 10")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestRubyUntilModifier:
    def test_until_modifier_basic(self):
        instructions = _parse_ruby("x -= 1 until x <= 0")
        opcodes = _opcodes(instructions)
        assert Opcode.UNOP in opcodes
        assert Opcode.BRANCH_IF in opcodes
        labels = _labels_in_order(instructions)
        assert any("untilmod" in lbl for lbl in labels)

    def test_until_modifier_negates_condition(self):
        instructions = _parse_ruby("x -= 1 until x <= 0")
        unops = _find_all(instructions, Opcode.UNOP)
        assert any("!" in inst.operands for inst in unops)

    def test_until_modifier_has_loop_back(self):
        instructions = _parse_ruby("x -= 1 until x <= 0")
        branches = _find_all(instructions, Opcode.BRANCH)
        labels = _labels_in_order(instructions)
        cond_labels = [lbl for lbl in labels if "untilmod_cond" in lbl]
        assert any(b.label in cond_labels for b in branches)


class TestRubyConditional:
    def test_conditional_ternary(self):
        instructions = _parse_ruby('x = a > 0 ? "pos" : "neg"')
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        labels = _labels_in_order(instructions)
        assert any("ternary" in lbl for lbl in labels)

    def test_conditional_stores_result(self):
        instructions = _parse_ruby('x = a > 0 ? "pos" : "neg"')
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_conditional_has_both_branches(self):
        instructions = _parse_ruby("y = cond ? 1 : 2")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("1" in inst.operands for inst in consts)
        assert any("2" in inst.operands for inst in consts)


class TestRubyUnary:
    def test_unary_negation(self):
        instructions = _parse_ruby("y = -x")
        opcodes = _opcodes(instructions)
        assert Opcode.UNOP in opcodes
        unops = _find_all(instructions, Opcode.UNOP)
        assert any("-" in inst.operands for inst in unops)

    def test_unary_not(self):
        instructions = _parse_ruby("y = !x")
        unops = _find_all(instructions, Opcode.UNOP)
        assert any("!" in inst.operands for inst in unops)

    def test_unary_stores_result(self):
        instructions = _parse_ruby("y = -x")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)


class TestRubySelf:
    def test_self_keyword(self):
        instructions = _parse_ruby("x = self")
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("self" in inst.operands for inst in loads)

    def test_self_in_method_call(self):
        instructions = _parse_ruby("self.foo")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("foo" in inst.operands for inst in calls)

    def test_self_stores(self):
        instructions = _parse_ruby("x = self")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestRubySingletonClass:
    def test_singleton_class_basic(self):
        source = """\
class << self
  def foo
    42
  end
end
"""
        instructions = _parse_ruby(source)
        labels = _labels_in_order(instructions)
        assert any("singleton_class" in lbl for lbl in labels)

    def test_singleton_class_contains_method(self):
        source = """\
class << self
  def bar
    1
  end
end
"""
        instructions = _parse_ruby(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("bar" in inst.operands for inst in stores)


class TestRubySingletonMethod:
    def test_singleton_method_basic(self):
        source = """\
def self.class_method
  "hello"
end
"""
        instructions = _parse_ruby(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("self.class_method" in inst.operands for inst in stores)

    def test_singleton_method_with_params(self):
        source = """\
def self.create(name)
  name
end
"""
        instructions = _parse_ruby(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("name" in p for p in param_names)

    def test_singleton_method_has_return(self):
        source = """\
def self.greet
  "hi"
end
"""
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes


class TestRubyOperatorExecution:
    """VM execution tests for Ruby-specific operators."""

    def test_logical_not_operator(self):
        source = """\
def negate(x)
    return !x
end

answer = negate(false)
"""
        vm, stats = execute_for_language("ruby", source)
        assert extract_answer(vm, "ruby") is True
        assert stats.llm_calls == 0

    def test_logical_not_truthy(self):
        source = """\
def negate(x)
    return !x
end

answer = negate(true)
"""
        vm, stats = execute_for_language("ruby", source)
        assert extract_answer(vm, "ruby") is False
        assert stats.llm_calls == 0


class TestRubyStringInterpolation:
    def test_interpolation_basic(self):
        instructions = _parse_ruby('"Hello #{name}"')
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.SYMBOLIC not in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("name" in inst.operands for inst in loads)

    def test_interpolation_expression(self):
        instructions = _parse_ruby('"#{x + 1}"')
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        # Inner arithmetic BINOP and concatenation BINOP
        assert any("+" in inst.operands for inst in binops)

    def test_interpolation_multiple(self):
        instructions = _parse_ruby('"#{a} and #{b}"')
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        load_names = [inst.operands[0] for inst in loads]
        assert "a" in load_names
        assert "b" in load_names
        binops = _find_all(instructions, Opcode.BINOP)
        concat_ops = [inst for inst in binops if inst.operands[0] == "+"]
        assert len(concat_ops) >= 2

    def test_no_interpolation_is_const(self):
        instructions = _parse_ruby('"hello"')
        consts = _find_all(instructions, Opcode.CONST)
        assert len(consts) >= 1
        binops = _find_all(instructions, Opcode.BINOP)
        assert not binops


class TestRubyHeredocInterpolation:
    def test_heredoc_interpolation_basic(self):
        source = "x = <<~HEREDOC\nHello #{name}\nHEREDOC"
        instructions = _parse_ruby(source)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("name" in inst.operands for inst in loads)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_heredoc_interpolation_expression(self):
        source = "x = <<~HEREDOC\nValue: #{arr[0]}\nHEREDOC"
        instructions = _parse_ruby(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_heredoc_interpolation_multiple_vars(self):
        source = "x = <<~HEREDOC\n#{a} and #{b}\nHEREDOC"
        instructions = _parse_ruby(source)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        load_names = [inst.operands[0] for inst in loads]
        assert "a" in load_names
        assert "b" in load_names
        binops = _find_all(instructions, Opcode.BINOP)
        concat_ops = [inst for inst in binops if inst.operands[0] == "+"]
        assert len(concat_ops) >= 2

    def test_heredoc_no_interpolation_fallback(self):
        source = "x = <<~HEREDOC\nplain text\nHEREDOC"
        instructions = _parse_ruby(source)
        consts = _find_all(instructions, Opcode.CONST)
        assert len(consts) >= 1
        binops = _find_all(instructions, Opcode.BINOP)
        # No concatenation for plain heredocs
        concat_ops = [inst for inst in binops if inst.operands[0] == "+"]
        assert not concat_ops


class TestRubyHashKeySymbol:
    def test_hash_key_symbol_no_symbolic(self):
        source = "h = { name: 'Alice' }"
        instructions = _parse_ruby(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("hash_key_symbol" in str(inst.operands) for inst in symbolics)

    def test_hash_key_symbol_lowered_as_const(self):
        source = "h = { age: 30 }"
        instructions = _parse_ruby(source)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("age" in str(inst.operands) for inst in consts)


class TestRubySuper:
    def test_super_no_args(self):
        source = "def greet\n  super\nend"
        instructions = _parse_ruby(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("super" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("super" in str(inst.operands) for inst in symbolics)

    def test_super_with_args(self):
        source = "def init(x)\n  super(x, 1)\nend"
        instructions = _parse_ruby(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        super_calls = [inst for inst in calls if "super" in inst.operands]
        assert len(super_calls) >= 1


class TestRubyYield:
    def test_yield_no_args(self):
        source = "def each\n  yield\nend"
        instructions = _parse_ruby(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("yield" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("yield" in str(inst.operands) for inst in symbolics)

    def test_yield_with_args(self):
        source = "def each\n  yield(item)\nend"
        instructions = _parse_ruby(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        yield_calls = [inst for inst in calls if "yield" in inst.operands]
        assert len(yield_calls) >= 1
