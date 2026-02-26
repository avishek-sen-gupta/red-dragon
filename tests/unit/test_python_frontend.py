"""Tests for PythonFrontend — tree-sitter Python AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.python import PythonFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_python(source: str) -> list[IRInstruction]:
    parser = get_parser("python")
    tree = parser.parse(source.encode("utf-8"))
    frontend = PythonFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


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
        assert any("while" in (inst.label or "") for inst in labels)

    def test_for_loop(self):
        instructions = _parse_python("for x in items:\n    y = x")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LOAD_INDEX in opcodes


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
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)


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
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Counter" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("f" in inst.operands for inst in stores)
        assert any("g" in inst.operands for inst in stores)


class TestPythonDecorators:
    def test_decorator_basic(self):
        source = "@my_dec\ndef foo():\n    return 1"
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("foo" in inst.operands for inst in stores)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        # Decorator call wraps foo
        assert len(calls) >= 1

    def test_decorator_stacked(self):
        source = "@dec1\n@dec2\ndef bar():\n    return 1"
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        foo_stores = [i for i in stores if "bar" in i.operands]
        # Initial store + 2 decorator re-stores
        assert len(foo_stores) >= 3
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) >= 2

    def test_decorator_on_class(self):
        source = "@register\nclass MyClass:\n    pass"
        instructions = _parse_python(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
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
        assert any("func:" in str(inst.operands) for inst in consts)

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
        labels = [i.label for i in instructions if i.opcode == Opcode.LABEL]
        comp_labels = [lbl for lbl in labels if "comp_cond" in lbl]
        assert len(comp_labels) >= 2

    def test_nested_comprehension_with_filter(self):
        source = "result = [x + y for x in xs for y in ys if x != y]"
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.BRANCH_IF in opcodes
        # filter branch
        labels = [i.label for i in instructions if i.opcode == Opcode.LABEL]
        assert any("comp_store" in lbl for lbl in labels)

    def test_single_comprehension_regression(self):
        source = "result = [x * 2 for x in items]"
        instructions = _parse_python(source)
        opcodes = _opcodes(instructions)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.STORE_INDEX in opcodes
        assert Opcode.LOAD_INDEX in opcodes
