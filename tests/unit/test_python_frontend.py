"""Tests for PythonFrontend — tree-sitter Python AST to IR lowering."""

from __future__ import annotations

from interpreter.frontends.python import PythonFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import (
    NO_SOURCE_LOCATION,
    IRInstruction,
    Opcode,
    SourceLocation,
    SpreadArguments,
    CodeLabel,
)
from interpreter.instructions import Label_


def _parse_python(source: str) -> list[IRInstruction]:
    frontend = PythonFrontend(TreeSitterParserFactory(), "python")
    return frontend.lower(source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [str(inst.label) for inst in instructions if inst.opcode == Opcode.LABEL]


class TestPythonSmoke:
    def test_empty_program(self):
        instructions = _parse_python("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_integer_literal(self):
        instructions = _parse_python("42")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)

    def test_string_literal(self):
        instructions = _parse_python('x = "hello"')
        consts = _find_all(instructions, Opcode.CONST)
        assert any('"hello"' in inst.operands for inst in consts)


class TestPythonVariables:
    def test_simple_assignment(self):
        instructions = _parse_python("x = 10")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_augmented_assignment(self):
        instructions = _parse_python("x += 1")
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestPythonExpressions:
    def test_arithmetic(self):
        instructions = _parse_python("y = x + 5")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.STORE_VAR in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_conditional_expression(self):
        instructions = _parse_python("y = 1 if x > 0 else 0")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes

    def test_list_literal(self):
        instructions = _parse_python("arr = [1, 2, 3]")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.STORE_INDEX in opcodes

    def test_dict_literal(self):
        instructions = _parse_python('d = {"a": 1, "b": 2}')
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes


class TestPythonControlFlow:
    def test_if_else(self):
        instructions = _parse_python("if x > 5:\n    y = 1\nelse:\n    y = 0")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        assert Opcode.BRANCH in opcodes

    def test_while_loop(self):
        instructions = _parse_python("while x > 0:\n    x = x - 1")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any(inst.label.contains("while") for inst in labels)

    def test_for_loop(self):
        instructions = _parse_python("for x in items:\n    y = x")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LOAD_INDEX in opcodes

    def test_if_elif_elif_else_all_branches_produce_ir(self):
        """All branches of if/elif/elif/else must produce IR — not just the first elif."""
        source = (
            "if x == 1:\n"
            "    y = 10\n"
            "elif x == 2:\n"
            "    y = 20\n"
            "elif x == 3:\n"
            "    y = 30\n"
            "else:\n"
            "    y = 40\n"
        )
        instructions = _parse_python(source)
        consts = _find_all(instructions, Opcode.CONST)
        const_values = [op for inst in consts for op in inst.operands]
        assert "10" in const_values, "if-branch value missing"
        assert "20" in const_values, "first elif-branch value missing"
        assert "30" in const_values, "second elif-branch value missing"
        assert "40" in const_values, "else-branch value missing"

    def test_if_elif_elif_else_branch_structure(self):
        """Multi-elif CFG must have correct BRANCH_IF count and all labels reachable."""
        source = (
            "if x == 1:\n"
            "    y = 10\n"
            "elif x == 2:\n"
            "    y = 20\n"
            "elif x == 3:\n"
            "    y = 30\n"
            "else:\n"
            "    y = 40\n"
        )
        instructions = _parse_python(source)
        branch_ifs = _find_all(instructions, Opcode.BRANCH_IF)
        # One BRANCH_IF for the if, one for each elif => 3 total
        assert len(branch_ifs) == 3

        labels = _labels_in_order(instructions)
        # Each BRANCH_IF target label must appear as a LABEL instruction
        branch_targets = {
            target for inst in branch_ifs for target in inst.branch_targets
        }
        label_set = set(labels)
        assert branch_targets.issubset(
            label_set
        ), f"Unreachable targets: {branch_targets - label_set}"

    def test_if_single_elif_no_else(self):
        """if/elif without else still lowers both branches."""
        source = "if a:\n    x = 1\nelif b:\n    x = 2\n"
        instructions = _parse_python(source)
        consts = _find_all(instructions, Opcode.CONST)
        const_values = [op for inst in consts for op in inst.operands]
        assert "1" in const_values
        assert "2" in const_values
        branch_ifs = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branch_ifs) == 2


class TestPythonFunctions:
    def test_function_definition(self):
        instructions = _parse_python("def add(a, b):\n    return a + b")
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("add" in inst.operands for inst in stores)

    def test_function_call(self):
        instructions = _parse_python("add(1, 2)")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) >= 1
        assert "add" in calls[0].operands

    def test_method_call(self):
        instructions = _parse_python('obj.method("arg")')
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(calls) >= 1
        assert "method" in calls[0].operands


class TestPythonClasses:
    def test_class_definition(self):
        instructions = _parse_python("class Dog:\n    pass")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)


class TestPythonSpecial:
    def test_raise_statement(self):
        instructions = _parse_python('raise ValueError("fail")')
        opcodes = _opcodes(instructions)
        assert Opcode.THROW in opcodes

    def test_tuple_literal(self):
        instructions = _parse_python("t = (1, 2, 3)")
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.STORE_INDEX in opcodes


class TestNonTrivialPython:
    def test_for_loop_with_conditional_accumulator(self):
        source = """\
total = 0
for item in items:
    if item > 10:
        total += item
    else:
        total += 1
"""
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LOAD_INDEX in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("total" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        assert len(instructions) > 15

    def test_nested_if_elif_else_chain(self):
        source = """\
if x > 100:
    grade = "A"
elif x > 50:
    grade = "B"
elif x > 25:
    grade = "C"
else:
    grade = "F"
"""
        instructions = _parse_python(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("grade" in inst.operands for inst in stores)
        labels = _labels_in_order(instructions)
        assert len(labels) >= 4

    def test_function_with_conditional_return(self):
        source = """\
def safe_divide(a, b):
    if b == 0:
        return 0
    return a / b
"""
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 2
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("/" in inst.operands for inst in binops)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("safe_divide" in inst.operands for inst in stores)

    def test_class_with_init_and_method(self):
        source = """\
class Counter:
    def __init__(self, start):
        self.count = start
    def increment(self):
        self.count = self.count + 1
"""
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Counter" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("count" in inst.operands for inst in store_fields)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        assert len(instructions) > 20

    def test_nested_for_loops_with_index_access(self):
        source = """\
result = 0
for row in matrix:
    for col in row:
        result += col
"""
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LOAD_INDEX in opcodes
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)
        assert len(instructions) > 20

    def test_conditional_expression_in_assignment(self):
        source = """\
x = 10
y = 20
result = x if x > y else y
"""
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)
        assert any("x" in inst.operands for inst in stores)
        assert any("y" in inst.operands for inst in stores)
        labels = _labels_in_order(instructions)
        assert any("ternary" in lbl for lbl in labels)

    def test_method_chaining(self):
        source = """\
result = data.get("key").strip().lower()
"""
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        assert "get" in method_names
        assert "strip" in method_names
        assert "lower" in method_names
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)

    def test_while_with_nested_if_and_mutation(self):
        source = """\
count = 0
total = 0
while count < 100:
    if count % 2 == 0:
        total += count
    else:
        total -= 1
    count += 1
"""
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("count" in inst.operands for inst in stores)
        assert any("total" in inst.operands for inst in stores)
        labels = _labels_in_order(instructions)
        assert any("while" in lbl for lbl in labels)
        assert len(instructions) > 20

    def test_function_calling_function(self):
        source = """\
def double(x):
    return x * 2

def quadruple(x):
    return double(double(x))
"""
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("double" in inst.operands for inst in stores)
        assert any("quadruple" in inst.operands for inst in stores)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("double" in inst.operands for inst in calls)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 2

    def test_raise_in_conditional(self):
        source = """\
def validate(x):
    if x < 0:
        raise ValueError("negative")
    return x
"""
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.THROW in opcodes
        assert Opcode.RETURN in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("validate" in inst.operands for inst in stores)

    def test_augmented_assignment_operators(self):
        source = """\
x = 10
x += 5
x -= 3
x *= 2
"""
        instructions = _parse_python(source)
        binops = _find_all(instructions, Opcode.BINOP)
        operators = [inst.operands[0] for inst in binops if inst.operands]
        assert "+" in operators
        assert "-" in operators
        assert "*" in operators
        stores = _find_all(instructions, Opcode.STORE_VAR)
        x_stores = [inst for inst in stores if "x" in inst.operands]
        assert len(x_stores) >= 4

    def test_list_and_dict_construction(self):
        source = """\
items = [1, 2, 3]
lookup = {"a": 10, "b": 20}
val = lookup["a"]
"""
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.LOAD_INDEX in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("items" in inst.operands for inst in stores)
        assert any("lookup" in inst.operands for inst in stores)
        assert any("val" in inst.operands for inst in stores)


class TestPythonForBreakContinue:
    def test_for_with_break(self):
        source = """\
for x in items:
    if x > 10:
        break
"""
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_INDEX in opcodes
        assert Opcode.BRANCH_IF in opcodes
        # break should emit BRANCH to the for_end label
        labels = _labels_in_order(instructions)
        assert any("for_end" in lbl for lbl in labels)
        branches = _find_all(instructions, Opcode.BRANCH)
        end_labels = [lbl for lbl in labels if "for_end" in lbl]
        assert any(b.label in end_labels for b in branches)

    def test_for_with_continue(self):
        source = """\
for x in items:
    if x < 0:
        continue
    total += x
"""
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_INDEX in opcodes
        # continue should emit BRANCH to the for_update label
        labels = _labels_in_order(instructions)
        assert any("for_update" in lbl for lbl in labels)
        branches = _find_all(instructions, Opcode.BRANCH)
        update_labels = [lbl for lbl in labels if "for_update" in lbl]
        assert any(b.label in update_labels for b in branches)


class TestPythonListComprehension:
    def test_list_comp_basic(self):
        source = "result = [x * 2 for x in items]"
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.LOAD_INDEX in opcodes
        assert Opcode.STORE_INDEX in opcodes
        assert Opcode.BRANCH_IF in opcodes

    def test_list_comp_with_filter(self):
        source = "result = [x for x in items if x > 0]"
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        # Should have two BRANCH_IF: one for loop condition, one for filter
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2

    def test_list_comp_with_call(self):
        source = "result = [f(x) for x in items]"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        call_names = [c.operands[0] for c in calls if c.operands]
        assert "f" in call_names


class TestPythonDictComprehension:
    def test_dict_comp_basic(self):
        source = "result = {k: v for k, v in items}"
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.STORE_INDEX in opcodes
        assert Opcode.BRANCH_IF in opcodes

    def test_dict_comp_with_filter(self):
        source = "result = {k: v for k, v in items if v > 0}"
        instructions = _parse_python(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2


class TestPythonWithStatement:
    def test_with_basic(self):
        source = 'with open("f") as fh:\n    data = fh.read()'
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        assert "__enter__" in method_names
        assert "__exit__" in method_names
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("fh" in inst.operands for inst in stores)

    def test_with_no_as(self):
        source = "with lock:\n    x = 1"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        assert "__enter__" in method_names
        assert "__exit__" in method_names
        # No variable stored for 'as' target
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_with_body_lowered(self):
        source = 'with open("a") as f, open("b") as g:\n    f.write(g.read())'
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        # Two enters and two exits
        assert method_names.count("__enter__") == 2
        assert method_names.count("__exit__") == 2
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("f" in inst.operands for inst in stores)
        assert any("g" in inst.operands for inst in stores)


class TestPythonDecorators:
    def test_decorator_basic(self):
        source = "@my_dec\ndef foo():\n    return 1"
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("foo" in inst.operands for inst in stores)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) >= 1
        # Decorator my_dec must be loaded to call it
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any(
            "my_dec" in inst.operands for inst in loads
        ), f"my_dec not loaded, got {[l.operands for l in loads]}"

    def test_decorator_stacked(self):
        source = "@dec1\n@dec2\ndef bar():\n    return 1"
        instructions = _parse_python(source)
        decls = _find_all(instructions, Opcode.DECL_VAR)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        bar_decls = [i for i in decls if "bar" in i.operands]
        bar_stores = [i for i in stores if "bar" in i.operands]
        # Initial def is DECL_VAR, 2 decorator re-stores are STORE_VAR
        assert len(bar_decls) >= 1
        assert len(bar_stores) >= 2
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) >= 2

    def test_decorator_on_class(self):
        source = "@register\nclass MyClass:\n    pass"
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("MyClass" in inst.operands for inst in stores)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) >= 1


class TestPythonLambda:
    def test_lambda_basic(self):
        source = "f = lambda x: x + 1"
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("f" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("func_" in str(inst.operands[0]) for inst in consts if inst.operands)

    def test_lambda_multi_param(self):
        source = "add = lambda a, b: a + b"
        instructions = _parse_python(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("a" in p for p in param_names)
        assert any("b" in p for p in param_names)

    def test_lambda_in_call(self):
        source = "result = map(lambda x: x * 2, items)"
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("map" in inst.operands for inst in calls)


class TestPythonNestedComprehension:
    def test_nested_comprehension_basic(self):
        source = "result = [x * y for x in xs for y in ys]"
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.STORE_INDEX in opcodes
        assert Opcode.LOAD_INDEX in opcodes
        # Should have multiple loop labels (at least 2 comp_cond)
        labels = [str(i.label) for i in instructions if i.opcode == Opcode.LABEL]
        comp_labels = [lbl for lbl in labels if "comp_cond" in lbl]
        assert len(comp_labels) >= 2

    def test_nested_comprehension_with_filter(self):
        source = "result = [x + y for x in xs for y in ys if x != y]"
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.BRANCH_IF in opcodes
        # filter branch
        labels = [str(i.label) for i in instructions if i.opcode == Opcode.LABEL]
        assert any("comp_store" in lbl for lbl in labels)

    def test_single_comprehension_regression(self):
        source = "result = [x * 2 for x in items]"
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.STORE_INDEX in opcodes
        assert Opcode.LOAD_INDEX in opcodes


class TestPythonGeneratorExpression:
    def test_generator_basic(self):
        source = "g = (x * 2 for x in items)"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("generator" in inst.operands for inst in calls)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("g" in inst.operands for inst in stores)

    def test_generator_with_filter(self):
        source = "g = (x for x in items if x > 0)"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("generator" in inst.operands for inst in calls)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        # loop condition + filter condition
        assert len(branches) >= 2

    def test_generator_in_call(self):
        source = "result = sum(x * x for x in nums)"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        call_names = [c.operands[0] for c in calls if c.operands]
        assert "sum" in call_names
        assert "generator" in call_names


class TestPythonSetComprehension:
    def test_set_comp_basic(self):
        source = "s = {x * 2 for x in items}"
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_OBJECT in opcodes
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("set" in inst.operands for inst in new_objs)
        assert Opcode.STORE_INDEX in opcodes

    def test_set_comp_with_filter(self):
        source = "s = {x for x in items if x > 0}"
        instructions = _parse_python(source)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("set" in inst.operands for inst in new_objs)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2


class TestPythonSetLiteral:
    def test_set_literal_basic(self):
        source = "s = {1, 2, 3}"
        instructions = _parse_python(source)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("set" in inst.operands for inst in new_objs)
        store_idxs = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(store_idxs) >= 3

    def test_set_literal_single(self):
        source = "s = {42}"
        instructions = _parse_python(source)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("set" in inst.operands for inst in new_objs)
        store_idxs = _find_all(instructions, Opcode.STORE_INDEX)
        assert len(store_idxs) >= 1

    def test_set_literal_with_expressions(self):
        source = "s = {a + 1, b * 2}"
        instructions = _parse_python(source)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("set" in inst.operands for inst in new_objs)
        binops = _find_all(instructions, Opcode.BINOP)
        assert len(binops) >= 2


class TestPythonYield:
    def test_yield_with_value(self):
        source = "def gen():\n    yield 42"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("yield" in inst.operands for inst in calls)

    def test_yield_bare(self):
        source = "def gen():\n    yield"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("yield" in inst.operands for inst in calls)

    def test_yield_with_variable(self):
        source = "def gen(items):\n    for x in items:\n        yield x"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("yield" in inst.operands for inst in calls)
        assert Opcode.LOAD_INDEX in _opcodes(instructions)


class TestPythonAwait:
    def test_await_basic(self):
        source = "async def f():\n    await coro()"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("await" in inst.operands for inst in calls)

    def test_await_assignment(self):
        source = "async def f():\n    result = await fetch(url)"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("await" in inst.operands for inst in calls)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)


class TestPythonNamedExpression:
    def test_walrus_basic(self):
        source = "if (n := len(data)) > 10:\n    print(n)"
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("n" in inst.operands for inst in stores)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("len" in inst.operands for inst in calls)

    def test_walrus_in_while(self):
        source = 'while (line := readline()) != "":\n    process(line)'
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("line" in inst.operands for inst in stores)

    def test_walrus_standalone(self):
        source = "(y := x + 1)"
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("y" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestPythonAssertStatement:
    def test_assert_simple(self):
        source = "assert x > 0"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("assert" in inst.operands for inst in calls)

    def test_assert_with_message(self):
        source = 'assert x > 0, "must be positive"'
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert_calls = [c for c in calls if "assert" in c.operands]
        assert len(assert_calls) >= 1
        # Should have 2 arguments (condition + message)
        assert len(assert_calls[0].operands) >= 3

    def test_assert_complex_condition(self):
        source = "assert len(items) == expected"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("assert" in inst.operands for inst in calls)
        assert any("len" in inst.operands for inst in calls)


class TestPythonGlobalNonlocal:
    def test_global_no_op(self):
        source = "global x\nx = 10"
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_nonlocal_no_op(self):
        source = "def outer():\n    x = 1\n    def inner():\n        nonlocal x\n        x = 2"
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestPythonDeleteStatement:
    def test_delete_single(self):
        source = "del x"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("del" in inst.operands for inst in calls)

    def test_delete_multiple(self):
        source = "del x, y"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        del_calls = [c for c in calls if "del" in c.operands]
        assert len(del_calls) >= 2

    def test_delete_attribute(self):
        source = "del obj.attr"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("del" in inst.operands for inst in calls)


class TestPythonImportStatement:
    def test_import_simple(self):
        source = "import os"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("import" in inst.operands for inst in calls)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("os" in inst.operands for inst in stores)

    def test_import_dotted(self):
        source = "import os.path"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("os.path" in inst.operands for inst in calls)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("os" in inst.operands for inst in stores)

    def test_import_from_basic(self):
        source = "from os import path"
        instructions = _parse_python(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("import" in inst.operands for inst in calls)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("path" in inst.operands for inst in stores)

    def test_import_from_multiple(self):
        source = "from os import path, getcwd"
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("path" in inst.operands for inst in stores)
        assert any("getcwd" in inst.operands for inst in stores)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        import_calls = [c for c in calls if "import" in c.operands]
        assert len(import_calls) >= 2


class TestPythonMatchStatement:
    def test_match_basic(self):
        source = "match x:\n    case 1:\n        y = 1\n    case 2:\n        y = 2"
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        assert Opcode.BRANCH_IF in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("==" in inst.operands for inst in binops)

    def test_match_with_wildcard(self):
        source = "match cmd:\n    case 1:\n        y = 1\n    case _:\n        y = 0"
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)
        labels = _labels_in_order(instructions)
        assert any("match_end" in lbl for lbl in labels)

    def test_match_multiple_cases(self):
        source = 'match status:\n    case 200:\n        msg = "ok"\n    case 404:\n        msg = "not found"\n    case _:\n        msg = "error"'
        instructions = _parse_python(source)
        binops = _find_all(instructions, Opcode.BINOP)
        eq_ops = [b for b in binops if "==" in b.operands]
        assert len(eq_ops) >= 2
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("msg" in inst.operands for inst in stores)


class TestPythonTypeAlias:
    def test_type_alias_no_op(self):
        source = "type Point = tuple[int, int]\nx = 1"
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_type_alias_does_not_emit_ir(self):
        source = "type Vector = list[float]"
        instructions = _parse_python(source)
        # Only entry label should exist, no variable stores
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert len(stores) == 0


class TestPythonSlice:
    def test_slice_basic(self):
        """a[1:3] should emit CALL_FUNCTION('slice', collection, start, stop, step)."""
        instructions = _parse_python("a[1:3]")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        slice_calls = [c for c in calls if "slice" in c.operands]
        assert len(slice_calls) == 1
        # Should have 5 operands: 'slice', collection_reg, start, stop, step
        assert len(slice_calls[0].operands) == 5
        # Should NOT have LOAD_INDEX — slice is handled directly
        assert Opcode.LOAD_INDEX not in _opcodes(instructions)

    def test_slice_with_step(self):
        """a[1:3:2] should lower slice with collection, start=1, stop=3, step=2."""
        instructions = _parse_python("a[1:3:2]")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        slice_calls = [c for c in calls if "slice" in c.operands]
        assert len(slice_calls) == 1
        # Should have 5 operands: 'slice', collection_reg, start, stop, step
        assert len(slice_calls[0].operands) == 5

    def test_slice_no_start(self):
        """a[:3] should lower slice with start=None, stop=3."""
        instructions = _parse_python("a[:3]")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        slice_calls = [c for c in calls if "slice" in c.operands]
        assert len(slice_calls) == 1
        # No SYMBOLIC should be emitted for slice
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        unsupported_slices = [
            s for s in symbolics if any("slice" in str(op) for op in s.operands)
        ]
        assert len(unsupported_slices) == 0

    def test_slice_no_stop(self):
        """a[1:] should lower slice with start=1, stop=None."""
        instructions = _parse_python("a[1:]")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        slice_calls = [c for c in calls if "slice" in c.operands]
        assert len(slice_calls) == 1

    def test_slice_assignment(self):
        """result = a[::2] should store to result."""
        instructions = _parse_python("result = a[::2]")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        slice_calls = [c for c in calls if "slice" in c.operands]
        assert len(slice_calls) == 1
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)

    def test_simple_index_still_uses_load_index(self):
        """a[0] should still use LOAD_INDEX, not slice."""
        instructions = _parse_python("a[0]")
        assert Opcode.LOAD_INDEX in _opcodes(instructions)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        slice_calls = [c for c in calls if "slice" in c.operands]
        assert len(slice_calls) == 0


class TestPythonParamSeparators:
    def test_keyword_separator_no_op(self):
        """def f(a, *, b): ... should not emit SYMBOLIC for *."""
        instructions = _parse_python("def f(a, *, b): pass")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_symbolics = [
            s for s in symbolics if any("param:" in str(op) for op in s.operands)
        ]
        # Should have params a and b, but no unsupported entries
        param_names = [s.operands[0] for s in param_symbolics]
        assert any("a" in p for p in param_names)
        assert any("b" in p for p in param_names)
        unsupported = [
            s for s in symbolics if any("unsupported" in str(op) for op in s.operands)
        ]
        assert len(unsupported) == 0

    def test_positional_separator_no_op(self):
        """def f(a, /, b): ... should not emit SYMBOLIC for /."""
        instructions = _parse_python("def f(a, /, b): pass")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_symbolics = [
            s for s in symbolics if any("param:" in str(op) for op in s.operands)
        ]
        param_names = [s.operands[0] for s in param_symbolics]
        assert any("a" in p for p in param_names)
        assert any("b" in p for p in param_names)
        unsupported = [
            s for s in symbolics if any("unsupported" in str(op) for op in s.operands)
        ]
        assert len(unsupported) == 0

    def test_both_separators(self):
        """def f(a, /, b, *, c): ... should handle both separators."""
        instructions = _parse_python("def f(a, /, b, *, c): pass")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_symbolics = [
            s for s in symbolics if any("param:" in str(op) for op in s.operands)
        ]
        param_names = [s.operands[0] for s in param_symbolics]
        assert any("a" in p for p in param_names)
        assert any("b" in p for p in param_names)
        assert any("c" in p for p in param_names)


class TestPythonListPattern:
    def test_list_pattern_basic(self):
        """match x: case [1, 2]: ... should emit len check + LOAD_INDEX for each element."""
        source = "match x:\n    case [1, 2]:\n        pass"
        instructions = _parse_python(source)
        # New Pattern ADT: emits CALL_FUNCTION len + LOAD_INDEX per element
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("len" in str(inst.operands) for inst in calls)
        load_idxs = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(load_idxs) >= 2

    def test_list_pattern_no_symbolic(self):
        """list_pattern should not emit SYMBOLIC unsupported:list_pattern."""
        source = "match x:\n    case [1, 2]:\n        pass"
        instructions = _parse_python(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        unsupported = [
            s for s in symbolics if any("list_pattern" in str(op) for op in s.operands)
        ]
        assert len(unsupported) == 0

    def test_list_pattern_with_body(self):
        """List pattern match with body should lower body."""
        source = "match x:\n    case [1, 2]:\n        y = 1"
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)
        # New Pattern ADT: emits CALL_FUNCTION len instead of NEW_ARRAY
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("len" in str(inst.operands) for inst in calls)

    def test_list_pattern_empty(self):
        """match x: case []: ... should check len == 0."""
        source = "match x:\n    case []:\n        pass"
        instructions = _parse_python(source)
        # Empty SequencePattern: len == 0 check
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("len" in str(inst.operands) for inst in calls)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("0" in str(inst.operands) for inst in consts)


class TestPythonInterpolation:
    def test_interpolation_basic(self):
        """f'hello {name}' decomposes into CONST + LOAD_VAR + BINOP concatenation."""
        instructions = _parse_python('x = f"hello {name}"')
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("hello" in str(inst.operands) for inst in consts)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("name" in inst.operands for inst in loads)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_interpolation_no_symbolic(self):
        """f-string should not emit unsupported:interpolation."""
        instructions = _parse_python('f"hello {name}"')
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        unsupported = [
            s for s in symbolics if any("interpolation" in str(op) for op in s.operands)
        ]
        assert len(unsupported) == 0

    def test_interpolation_handler_directly(self):
        """interpolation node lowered directly should lower the inner expression."""
        from tree_sitter_language_pack import get_parser
        from interpreter.frontends.python.expressions import lower_interpolation
        from interpreter.frontends.python.frontend import PythonFrontend
        from interpreter.frontends.context import TreeSitterEmitContext
        from interpreter.frontend_observer import NullFrontendObserver

        parser = get_parser("python")
        source = b'f"{x + 1}"'
        tree = parser.parse(source)
        # string is a direct child of module
        string_node = tree.root_node.children[0]
        interp_node = next(
            (c for c in string_node.children if c.type == "interpolation"),
            string_node,
        )
        fe = PythonFrontend(TreeSitterParserFactory(), "python")
        ctx = TreeSitterEmitContext(
            source=source,
            language="python",
            observer=NullFrontendObserver(),
            constants=fe._build_constants(),
            stmt_dispatch=fe._build_stmt_dispatch(),
            expr_dispatch=fe._build_expr_dispatch(),
        )
        ctx.emit_inst(Label_(label=CodeLabel("entry")))
        reg = lower_interpolation(ctx, interp_node)
        assert reg.name.startswith("%")
        # Should have lowered the binary_operator inside
        binops = _find_all(ctx.instructions, Opcode.BINOP)
        assert len(binops) >= 1


class TestSourceLocationModel:
    def test_source_location_str(self):
        loc = SourceLocation(start_line=3, start_col=8, end_line=3, end_col=10)
        assert str(loc) == "3:8-3:10"

    def test_source_location_fields_accessible(self):
        loc = SourceLocation(start_line=1, start_col=0, end_line=5, end_col=12)
        assert loc.start_line == 1
        assert loc.start_col == 0
        assert loc.end_line == 5
        assert loc.end_col == 12

    def test_no_source_location_is_unknown(self):
        assert NO_SOURCE_LOCATION.is_unknown()
        assert str(NO_SOURCE_LOCATION) == "<unknown>"

    def test_real_source_location_is_not_unknown(self):
        loc = SourceLocation(start_line=1, start_col=0, end_line=1, end_col=5)
        assert not loc.is_unknown()


class TestSourceLocationTraceability:
    def test_every_non_label_instruction_has_real_source_location(self):
        """Every non-LABEL instruction from a simple program should have a real source_location."""
        source = "x = 10\ny = x + 1"
        instructions = _parse_python(source)
        for inst in instructions:
            if inst.opcode == Opcode.LABEL:
                continue
            assert not inst.source_location.is_unknown(), (
                f"Instruction {inst.opcode.value} (operands={inst.operands}) "
                f"has unknown source_location"
            )

    def test_source_location_is_structured(self):
        """source_location should be a SourceLocation object, not a string."""
        instructions = _parse_python("x = 42")
        for inst in instructions:
            assert isinstance(
                inst.source_location, SourceLocation
            ), f"Expected SourceLocation, got {type(inst.source_location)}"

    def test_source_location_line_numbers_correct(self):
        """Line numbers should be 1-based and match source positions."""
        source = "x = 10\ny = 20"
        instructions = _parse_python(source)
        # x = 10 is on line 1
        stores = _find_all(instructions, Opcode.STORE_VAR)
        x_store = next(s for s in stores if "x" in s.operands)
        assert x_store.source_location.start_line == 1
        # y = 20 is on line 2
        y_store = next(s for s in stores if "y" in s.operands)
        assert y_store.source_location.start_line == 2

    def test_instruction_str_includes_source_location(self):
        """str(instruction) should include # line:col-line:col when source_location is set."""
        instructions = _parse_python("x = 42")
        const_inst = next(i for i in instructions if i.opcode == Opcode.CONST)
        text = str(const_inst)
        assert "  # " in text
        assert ":" in text.split("# ")[1]

    def test_label_str_without_source_location(self):
        """LABEL instructions should not have a source location comment."""
        instructions = _parse_python("x = 1")
        label_inst = instructions[0]
        assert label_inst.opcode == Opcode.LABEL
        text = str(label_inst)
        assert "#" not in text

    def test_function_instructions_have_locations(self):
        """Instructions inside a function body should have source locations."""
        source = "def add(a, b):\n    return a + b"
        instructions = _parse_python(source)
        returns = _find_all(instructions, Opcode.RETURN)
        explicit_return = next(r for r in returns if not r.source_location.is_unknown())
        assert explicit_return.source_location.start_line == 2


class TestPythonEllipsis:
    def test_ellipsis_no_symbolic(self):
        source = "x = ..."
        instructions = _parse_python(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("ellipsis" in str(inst.operands) for inst in symbolics)

    def test_ellipsis_as_const(self):
        source = "x = ..."
        instructions = _parse_python(source)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("..." in str(inst.operands) for inst in consts)


class TestPythonListSplat:
    def test_list_splat_no_symbolic(self):
        source = "x = [*a, 1]"
        instructions = _parse_python(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("list_splat" in str(inst.operands) for inst in symbolics)

    def test_list_splat_produces_spread_arguments(self):
        source = "x = [*items, 1]"
        instructions = _parse_python(source)
        spread_ops = [
            op
            for inst in instructions
            for op in inst.operands
            if isinstance(op, SpreadArguments)
        ]
        assert len(spread_ops) >= 1

    def test_dict_splat_no_symbolic(self):
        source = "x = {**defaults, 'key': 1}"
        instructions = _parse_python(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("dictionary_splat" in str(inst.operands) for inst in symbolics)


class TestPythonExpressionList:
    def test_expression_list_no_symbolic(self):
        source = "a, b = 2, 3"
        instructions = _parse_python(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("expression_list" in str(inst.operands) for inst in symbolics)


class TestPythonDictPattern:
    def test_dict_pattern_no_symbolic(self):
        source = 'match data:\n    case {"text": message}:\n        pass'
        instructions = _parse_python(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("dict_pattern" in str(inst.operands) for inst in symbolics)

    def test_dict_pattern_load_field(self):
        source = 'match data:\n    case {"key": val}:\n        pass'
        instructions = _parse_python(source)
        # New Pattern ADT: MappingPattern emits LOAD_FIELD per key
        load_fields = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("key" in str(inst.operands) for inst in load_fields)


class TestPythonSplatPattern:
    def test_splat_pattern_no_symbolic(self):
        source = "match items:\n    case [first, *rest]:\n        pass"
        instructions = _parse_python(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("splat_pattern" in str(inst.operands) for inst in symbolics)


class TestPythonDottedName:
    def test_dotted_name_in_expression(self):
        """dotted_name like os.path.join should lower without unsupported SYMBOLIC."""
        instructions = _parse_python("result = os.path.join(a, b)")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_dotted_name_attribute_access(self):
        """Accessing a module attribute via dotted name should produce LOAD_FIELD."""
        instructions = _parse_python("x = os.path.sep")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert len(loads) >= 1


class TestPythonFutureImportStatement:
    def test_future_import_no_symbolic(self):
        """from __future__ import annotations should not produce SYMBOLIC."""
        ir = _parse_python("from __future__ import annotations\nx = 42")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "future_import_statement" in str(inst.operands) for inst in symbolics
        )

    def test_future_import_does_not_block(self):
        """Code after future import should still execute."""
        ir = _parse_python("from __future__ import annotations\nx = 42")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
