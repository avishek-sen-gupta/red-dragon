"""Integration tests: Python pattern matching through VM execution."""

from __future__ import annotations

import pytest

from interpreter.field_name import FieldName, FieldKind
from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.types.type_expr import scalar
from interpreter.vm.vm import _heap_addr


def _run_python(source: str, max_steps: int = 500):
    vm = run(source, language=Language.PYTHON, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestLiteralMatch:
    def test_literal_int_match(self):
        _, local_vars = _run_python("""\
x = 2
match x:
    case 1:
        y = 10
    case 2:
        y = 20
    case 3:
        y = 30
""")
        assert local_vars[VarName("y")] == 20

    def test_literal_str_match(self):
        _, local_vars = _run_python("""\
x = "hello"
match x:
    case "world":
        y = 1
    case "hello":
        y = 2
""")
        assert local_vars[VarName("y")] == 2


class TestWildcardMatch:
    def test_wildcard_default(self):
        _, local_vars = _run_python("""\
x = 99
match x:
    case 1:
        y = 10
    case _:
        y = 99
""")
        assert local_vars[VarName("y")] == 99


class TestCaptureMatch:
    def test_capture_binds_value(self):
        _, local_vars = _run_python("""\
x = 42
match x:
    case val:
        y = val
""")
        assert local_vars[VarName("y")] == 42


class TestFallThrough:
    def test_fall_through_to_default(self):
        _, local_vars = _run_python("""\
x = 100
y = 0
match x:
    case 1:
        y = 10
    case 2:
        y = 20
    case _:
        y = 999
""")
        assert local_vars[VarName("y")] == 999

    def test_no_match_no_crash(self):
        _, local_vars = _run_python("""\
x = 100
y = 0
match x:
    case 1:
        y = 10
    case 2:
        y = 20
""")
        assert local_vars[VarName("y")] == 0


class TestTupleDestructure:
    def test_tuple_destructure(self):
        _, local_vars = _run_python(
            """\
point = (3, 4)
match point:
    case (a, b):
        z = a + b
""",
            max_steps=1000,
        )
        assert local_vars[VarName("z")] == 7


class TestListDestructure:
    def test_list_destructure(self):
        _, local_vars = _run_python(
            """\
items = [10, 20]
match items:
    case [a, b]:
        z = a + b
""",
            max_steps=1000,
        )
        assert local_vars[VarName("z")] == 30


class TestNestedSequence:
    def test_nested_sequence(self):
        _, local_vars = _run_python(
            """\
data = (1, (2, 3))
match data:
    case (a, (b, c)):
        z = a + b + c
""",
            max_steps=1000,
        )
        assert local_vars[VarName("z")] == 6


class TestDictPattern:
    def test_dict_pattern(self):
        _, local_vars = _run_python(
            """\
d = {"name": "Alice", "age": 30}
match d:
    case {"name": name}:
        result = name
""",
            max_steps=1000,
        )
        assert local_vars[VarName("result")] == "Alice"


class TestOrPattern:
    def test_or_pattern(self):
        _, local_vars = _run_python("""\
x = 2
match x:
    case 1 | 2:
        y = "yes"
    case _:
        y = "no"
""")
        assert local_vars[VarName("y")] == "yes"


class TestAsPattern:
    def test_as_pattern(self):
        _, local_vars = _run_python("""\
x = 42
match x:
    case val as name:
        y = name
""")
        assert local_vars[VarName("y")] == 42


class TestGuard:
    def test_guard_filters(self):
        _, local_vars = _run_python("""\
x = -5
match x:
    case val if val > 0:
        y = "positive"
    case _:
        y = "non-positive"
""")
        assert local_vars[VarName("y")] == "non-positive"


class TestClassPattern:
    def test_class_keyword(self):
        _, local_vars = _run_python(
            """\
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

p = Point(3, 4)
match p:
    case Point(x=3, y=y_val):
        result = y_val
""",
            max_steps=2000,
        )
        assert local_vars[VarName("result")] == 4

    def test_class_positional(self):
        _, local_vars = _run_python(
            """\
class Pair:
    __match_args__ = ("a", "b")
    def __init__(self, a, b):
        self.a = a
        self.b = b

p = Pair(10, 20)
match p:
    case Pair(a, b):
        result = a + b
""",
            max_steps=2000,
        )
        assert local_vars[VarName("result")] == 30


class TestPositionalClassPattern:
    def test_class_positional_with_match_args(self):
        """Point(3, b) with __match_args__ — b bound to 4."""
        _, local_vars = _run_python(
            """\
class Point:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

p = Point(3, 4)
match p:
    case Point(3, b):
        result = b
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 4
        )

    def test_class_positional_two_captures(self):
        """Point(a, b) captures both fields via __match_args__."""
        _, local_vars = _run_python(
            """\
class Point:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

p = Point(3, 4)
match p:
    case Point(a, b):
        ra = a
        rb = b
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("ra")], int)
            and local_vars[VarName("ra")] == 3
        )
        assert (
            isinstance(local_vars[VarName("rb")], int)
            and local_vars[VarName("rb")] == 4
        )

    def test_class_positional_literal_rejects(self):
        """Point(99, b) with non-matching x — falls to default."""
        _, local_vars = _run_python(
            """\
class Point:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

p = Point(3, 4)
result = "default"
match p:
    case Point(99, b):
        result = "matched"
    case _:
        result = "default"
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "default"
        )

    def test_class_positional_in_sequence_with_star(self):
        """Positional class patterns inside a list with star — verify rest element fields+types."""
        vm, local_vars = _run_python(
            """\
class Point:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

points = [Point(1, 2), Point(3, 4), Point(5, 6)]
match points:
    case [Point(a, b), *rest]:
        ra = a
        rb = b
        rest_len = len(rest)
        r0x = rest[0].x
        r0y = rest[0].y
        r1x = rest[1].x
        r1y = rest[1].y
""",
            max_steps=5000,
        )
        assert (
            isinstance(local_vars[VarName("ra")], int)
            and local_vars[VarName("ra")] == 1
        )
        assert (
            isinstance(local_vars[VarName("rb")], int)
            and local_vars[VarName("rb")] == 2
        )
        assert (
            isinstance(local_vars[VarName("rest_len")], int)
            and local_vars[VarName("rest_len")] == 2
        )
        assert (
            isinstance(local_vars[VarName("r0x")], int)
            and local_vars[VarName("r0x")] == 3
        )
        assert (
            isinstance(local_vars[VarName("r0y")], int)
            and local_vars[VarName("r0y")] == 4
        )
        assert (
            isinstance(local_vars[VarName("r1x")], int)
            and local_vars[VarName("r1x")] == 5
        )
        assert (
            isinstance(local_vars[VarName("r1y")], int)
            and local_vars[VarName("r1y")] == 6
        )
        rest_addr = _heap_addr(local_vars[VarName("rest")])
        r0_addr = _heap_addr(
            vm.heap[str(rest_addr)].fields[FieldName("0", FieldKind.INDEX)].value
        )
        r1_addr = _heap_addr(
            vm.heap[str(rest_addr)].fields[FieldName("1", FieldKind.INDEX)].value
        )
        assert vm.heap[str(r0_addr)].type_hint == scalar("Point")
        assert vm.heap[str(r1_addr)].type_hint == scalar("Point")

    def test_nested_positional_line_of_points(self):
        """Line(Point(x1,y1), Point(x2,y2)) — nested positional resolution."""
        _, local_vars = _run_python(
            """\
class Point:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

class Line:
    __match_args__ = ("start", "end")
    def __init__(self, start, end):
        self.start = start
        self.end = end

line = Line(Point(0, 0), Point(3, 4))
match line:
    case Line(Point(x1, y1), Point(x2, y2)):
        dx = x2 - x1
        dy = y2 - y1
""",
            max_steps=5000,
        )
        assert (
            isinstance(local_vars[VarName("dx")], int)
            and local_vars[VarName("dx")] == 3
        )
        assert (
            isinstance(local_vars[VarName("dy")], int)
            and local_vars[VarName("dy")] == 4
        )

    def test_positional_with_guard_pythagorean(self):
        """Positional capture + guard using x*x + y*y."""
        _, local_vars = _run_python(
            """\
class Point:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

p = Point(3, 4)
match p:
    case Point(x, y) if x == 0 and y == 0:
        result = "origin"
    case Point(x, y) if x * x + y * y <= 25:
        result = "near"
    case Point(x, y):
        result = "far"
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "near"
        )
        assert (
            isinstance(local_vars[VarName("x")], int) and local_vars[VarName("x")] == 3
        )
        assert (
            isinstance(local_vars[VarName("y")], int) and local_vars[VarName("y")] == 4
        )

    def test_or_pattern_with_positional_class_alternatives(self):
        """Or-pattern across Success(v) | Error(v) — positional on both."""
        _, local_vars = _run_python(
            """\
class Success:
    __match_args__ = ("value",)
    def __init__(self, value):
        self.value = value

class Error:
    __match_args__ = ("value",)
    def __init__(self, value):
        self.value = value

result_obj = Error("not found")
match result_obj:
    case Success(v) | Error(v):
        extracted = v
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("extracted")], str)
            and local_vars[VarName("extracted")] == "not found"
        )

    def test_positional_in_or_inside_list_with_star(self):
        """Point(a,b) | Vec(a,b) as first element of list with star — verify rest contents."""
        vm, local_vars = _run_python(
            """\
class Point:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

class Vec:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

items = [Vec(10, 20), Point(3, 4), Point(5, 6)]
match items:
    case [Point(a, b) | Vec(a, b), *rest]:
        ra = a
        rb = b
        rest_len = len(rest)
        r0x = rest[0].x
        r0y = rest[0].y
        r1x = rest[1].x
        r1y = rest[1].y
""",
            max_steps=5000,
        )
        assert (
            isinstance(local_vars[VarName("ra")], int)
            and local_vars[VarName("ra")] == 10
        )
        assert (
            isinstance(local_vars[VarName("rb")], int)
            and local_vars[VarName("rb")] == 20
        )
        assert (
            isinstance(local_vars[VarName("rest_len")], int)
            and local_vars[VarName("rest_len")] == 2
        )
        assert (
            isinstance(local_vars[VarName("r0x")], int)
            and local_vars[VarName("r0x")] == 3
        )
        assert (
            isinstance(local_vars[VarName("r0y")], int)
            and local_vars[VarName("r0y")] == 4
        )
        assert (
            isinstance(local_vars[VarName("r1x")], int)
            and local_vars[VarName("r1x")] == 5
        )
        assert (
            isinstance(local_vars[VarName("r1y")], int)
            and local_vars[VarName("r1y")] == 6
        )
        rest_addr = _heap_addr(local_vars[VarName("rest")])
        r0_addr = _heap_addr(
            vm.heap[str(rest_addr)].fields[FieldName("0", FieldKind.INDEX)].value
        )
        r1_addr = _heap_addr(
            vm.heap[str(rest_addr)].fields[FieldName("1", FieldKind.INDEX)].value
        )
        assert vm.heap[str(r0_addr)].type_hint == scalar("Point")
        assert vm.heap[str(r1_addr)].type_hint == scalar("Point")

    def test_three_level_deep_tree_positional(self):
        """Node(Node(Leaf(a), Leaf(b)), Leaf(c)) — 3 levels deep."""
        vm, local_vars = _run_python(
            """\
class Leaf:
    __match_args__ = ("val",)
    def __init__(self, val):
        self.val = val

class Node:
    __match_args__ = ("left", "right")
    def __init__(self, left, right):
        self.left = left
        self.right = right

tree = Node(Node(Leaf(1), Leaf(2)), Leaf(3))
match tree:
    case Node(Node(Leaf(a), Leaf(b)), Leaf(c)):
        result = a + b + c
""",
            max_steps=5000,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 6
        )
        tree_addr = _heap_addr(local_vars[VarName("tree")])
        assert vm.heap[str(tree_addr)].type_hint == scalar("Node")


class TestComplexLiteralPattern:
    @pytest.mark.xfail(
        reason="Complex literal patterns not yet implemented (red-dragon-2qem)"
    )
    def test_complex_pattern_rejects_mismatch(self):
        """1+2j pattern must reject 3+4j — currently matches anything."""
        _, local_vars = _run_python(
            """\
z = 3+4j
result = "no match"
match z:
    case 1+2j:
        result = "match"
    case _:
        result = "no match"
""",
            max_steps=500,
        )
        assert local_vars[VarName("result")] == "no match"


class TestValuePatterns:
    def test_value_pattern_class_constant(self):
        """case Color.RED: with matching value."""
        _, local_vars = _run_python(
            """\
class Color:
    RED = 0
    GREEN = 1
    BLUE = 2

c = 0
match c:
    case Color.RED:
        result = "red"
    case Color.GREEN:
        result = "green"
    case _:
        result = "other"
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "red"
        )

    def test_value_pattern_rejects_mismatch(self):
        """case Color.RED: with non-matching value — falls to default."""
        _, local_vars = _run_python(
            """\
class Color:
    RED = 0
    GREEN = 1

c = 999
result = "no match"
match c:
    case Color.RED:
        result = "red"
    case _:
        result = "no match"
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "no match"
        )

    def test_value_pattern_multi_level(self):
        """Three-level dotted lookup."""
        _, local_vars = _run_python(
            """\
class HTTP:
    class Status:
        OK = 200
        NOT_FOUND = 404

code = 200
match code:
    case HTTP.Status.OK:
        result = "ok"
    case HTTP.Status.NOT_FOUND:
        result = "not found"
    case _:
        result = "other"
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "ok"
        )

    def test_value_pattern_in_or(self):
        """case Color.RED | Color.GREEN: with matching value."""
        _, local_vars = _run_python(
            """\
class Color:
    RED = 0
    GREEN = 1
    BLUE = 2

c = 1
match c:
    case Color.RED | Color.GREEN:
        result = "warm"
    case _:
        result = "other"
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "warm"
        )

    def test_value_pattern_inside_tuple(self):
        """Value pattern as element of a tuple pattern."""
        _, local_vars = _run_python(
            """\
class Direction:
    UP = 1
    DOWN = 2

data = ("move", 1)
match data:
    case ("move", Direction.UP):
        result = "moving up"
    case ("move", Direction.DOWN):
        result = "moving down"
    case _:
        result = "unknown"
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "moving up"
        )

    def test_value_pattern_with_guard(self):
        """Value pattern combined with guard on a separate variable."""
        _, local_vars = _run_python(
            """\
class Level:
    WARN = 1
    ERROR = 2
    FATAL = 3

severity = 2
count = 5
match severity:
    case Level.ERROR if count > 10:
        result = "escalate"
    case Level.ERROR:
        result = "log"
    case _:
        result = "ignore"
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "log"
        )

    def test_value_pattern_in_list_with_star(self):
        """Value pattern as first element of list with star capture."""
        _, local_vars = _run_python(
            """\
class Op:
    ADD = "add"
    MUL = "mul"

instructions = ["add", 1, 2, 3]
match instructions:
    case [Op.ADD, *operands]:
        result = "addition"
        op_len = len(operands)
        op_0 = operands[0]
        op_1 = operands[1]
        op_2 = operands[2]
    case [Op.MUL, *operands]:
        result = "multiply"
        op_len = len(operands)
    case _:
        result = "unknown"
        op_len = 0
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "addition"
        )
        assert (
            isinstance(local_vars[VarName("op_len")], int)
            and local_vars[VarName("op_len")] == 3
        )
        assert (
            isinstance(local_vars[VarName("op_0")], int)
            and local_vars[VarName("op_0")] == 1
        )
        assert (
            isinstance(local_vars[VarName("op_1")], int)
            and local_vars[VarName("op_1")] == 2
        )
        assert (
            isinstance(local_vars[VarName("op_2")], int)
            and local_vars[VarName("op_2")] == 3
        )

    def test_value_pattern_as_class_keyword(self):
        """Value pattern used as keyword argument in class pattern."""
        _, local_vars = _run_python(
            """\
class Color:
    RED = 0
    GREEN = 1

class Shape:
    __match_args__ = ("kind", "color")
    def __init__(self, kind, color):
        self.kind = kind
        self.color = color

s = Shape("circle", 0)
match s:
    case Shape(kind="circle", color=Color.RED):
        result = "red circle"
    case Shape(kind="circle", color=Color.GREEN):
        result = "green circle"
    case _:
        result = "other"
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "red circle"
        )

    def test_value_or_pattern_http_status(self):
        """Multiple value patterns in or-pattern across cases."""
        _, local_vars = _run_python(
            """\
class Status:
    OK = 200
    CREATED = 201
    BAD_REQUEST = 400
    NOT_FOUND = 404
    SERVER_ERROR = 500

code = 404
match code:
    case Status.OK | Status.CREATED:
        category = "success"
    case Status.BAD_REQUEST | Status.NOT_FOUND:
        category = "client_error"
    case Status.SERVER_ERROR:
        category = "server_error"
    case _:
        category = "unknown"
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("category")], str)
            and local_vars[VarName("category")] == "client_error"
        )

    def test_value_pattern_in_positional_class(self):
        """Value pattern as positional arg in class pattern via __match_args__."""
        _, local_vars = _run_python(
            """\
class Axis:
    X = 0
    Y = 1

class Move:
    __match_args__ = ("axis", "distance")
    def __init__(self, axis, distance):
        self.axis = axis
        self.distance = distance

m = Move(0, 42)
match m:
    case Move(Axis.X, d):
        result = d
        direction = "horizontal"
    case Move(Axis.Y, d):
        result = d
        direction = "vertical"
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 42
        )
        assert (
            isinstance(local_vars[VarName("direction")], str)
            and local_vars[VarName("direction")] == "horizontal"
        )

    def test_value_pattern_head_with_star_of_typed_objects(self):
        """Value pattern as list head + star rest of class instances — verify all fields and types."""
        vm, local_vars = _run_python(
            """\
class Action:
    MOVE = "move"
    ATTACK = "attack"

class Target:
    __match_args__ = ("name", "hp")
    def __init__(self, name, hp):
        self.name = name
        self.hp = hp

commands = ["move", Target("goblin", 30), Target("dragon", 100)]
match commands:
    case [Action.MOVE, *targets]:
        action = "move"
        t_len = len(targets)
        t0_name = targets[0].name
        t0_hp = targets[0].hp
        t1_name = targets[1].name
        t1_hp = targets[1].hp
    case _:
        action = "unknown"
""",
            max_steps=5000,
        )
        assert (
            isinstance(local_vars[VarName("action")], str)
            and local_vars[VarName("action")] == "move"
        )
        assert (
            isinstance(local_vars[VarName("t_len")], int)
            and local_vars[VarName("t_len")] == 2
        )
        assert (
            isinstance(local_vars[VarName("t0_name")], str)
            and local_vars[VarName("t0_name")] == "goblin"
        )
        assert (
            isinstance(local_vars[VarName("t0_hp")], int)
            and local_vars[VarName("t0_hp")] == 30
        )
        assert (
            isinstance(local_vars[VarName("t1_name")], str)
            and local_vars[VarName("t1_name")] == "dragon"
        )
        assert (
            isinstance(local_vars[VarName("t1_hp")], int)
            and local_vars[VarName("t1_hp")] == 100
        )
        rest_addr = _heap_addr(local_vars[VarName("targets")])
        t0_addr = _heap_addr(
            vm.heap[str(rest_addr)].fields[FieldName("0", FieldKind.INDEX)].value
        )
        t1_addr = _heap_addr(
            vm.heap[str(rest_addr)].fields[FieldName("1", FieldKind.INDEX)].value
        )
        assert vm.heap[str(t0_addr)].type_hint == scalar("Target")
        assert vm.heap[str(t1_addr)].type_hint == scalar("Target")


class TestOutOfScopePatterns:
    def test_star_pattern_in_list(self):
        _, local_vars = _run_python(
            """\
items = [1, 2, 3, 4]
match items:
    case [first, *rest]:
        result = first
""",
            max_steps=1000,
        )
        assert local_vars[VarName("result")] == 1

    def test_or_pattern_with_captures(self):
        _, local_vars = _run_python(
            """\
data = (2, 99)
match data:
    case (1, x) | (2, x):
        result = x
""",
            max_steps=1000,
        )
        assert local_vars[VarName("result")] == 99


class TestNestedCrossPattern:
    def test_nested_class_in_sequence(self):
        _, local_vars = _run_python(
            """\
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

data = (Point(1, 2), Point(3, 4))
match data:
    case (Point(x=1, y=a), Point(x=3, y=b)):
        result = a + b
""",
            max_steps=3000,
        )
        assert local_vars[VarName("result")] == 6

    def test_nested_mapping_in_class(self):
        _, local_vars = _run_python(
            """\
class Config:
    def __init__(self, settings):
        self.settings = settings

cfg = Config({"debug": True})
match cfg:
    case Config(settings={"debug": val}):
        result = val
""",
            max_steps=3000,
        )
        assert local_vars[VarName("result")] is True


class TestStarPatterns:
    def test_star_at_end(self):
        vm, local_vars = _run_python(
            """\
items = [1, 2, 3, 4]
match items:
    case [first, *rest]:
        result_first = first
        rest_len = len(rest)
        rest_0 = rest[0]
        rest_1 = rest[1]
        rest_2 = rest[2]
""",
            max_steps=1000,
        )
        assert local_vars[VarName("result_first")] == 1
        assert local_vars[VarName("rest_len")] == 3
        assert local_vars[VarName("rest_0")] == 2
        assert local_vars[VarName("rest_1")] == 3
        assert local_vars[VarName("rest_2")] == 4

    def test_star_at_beginning(self):
        _, local_vars = _run_python(
            """\
items = [1, 2, 3]
match items:
    case [*head, last]:
        result_last = last
        head_len = len(head)
        head_0 = head[0]
        head_1 = head[1]
""",
            max_steps=1000,
        )
        assert local_vars[VarName("result_last")] == 3
        assert local_vars[VarName("head_len")] == 2
        assert local_vars[VarName("head_0")] == 1
        assert local_vars[VarName("head_1")] == 2

    def test_star_in_middle(self):
        _, local_vars = _run_python(
            """\
items = [1, 2, 3, 4, 5]
match items:
    case [a, *mid, z]:
        result_a = a
        result_z = z
        mid_len = len(mid)
        mid_0 = mid[0]
        mid_1 = mid[1]
        mid_2 = mid[2]
""",
            max_steps=1000,
        )
        assert local_vars[VarName("result_a")] == 1
        assert local_vars[VarName("result_z")] == 5
        assert local_vars[VarName("mid_len")] == 3
        assert local_vars[VarName("mid_0")] == 2
        assert local_vars[VarName("mid_1")] == 3
        assert local_vars[VarName("mid_2")] == 4

    def test_star_empty_rest(self):
        _, local_vars = _run_python(
            """\
items = [1, 2]
match items:
    case [a, b, *rest]:
        result_a = a
        result_b = b
        rest_len = len(rest)
""",
            max_steps=1000,
        )
        assert local_vars[VarName("result_a")] == 1
        assert local_vars[VarName("result_b")] == 2
        assert local_vars[VarName("rest_len")] == 0

    def test_star_in_tuple(self):
        _, local_vars = _run_python(
            """\
data = (10, 20, 30)
match data:
    case (first, *rest):
        result = first
        rest_0 = rest[0]
        rest_1 = rest[1]
""",
            max_steps=1000,
        )
        assert local_vars[VarName("result")] == 10
        assert local_vars[VarName("rest_0")] == 20
        assert local_vars[VarName("rest_1")] == 30

    def test_star_minimum_length_rejects(self):
        _, local_vars = _run_python(
            """\
items = [1]
result = "default"
match items:
    case [a, b, *rest]:
        result = "matched"
    case _:
        result = "default"
""",
            max_steps=1000,
        )
        assert local_vars[VarName("result")] == "default"

    def test_wildcard_star_no_binding(self):
        _, local_vars = _run_python(
            """\
items = [1, 2, 3]
match items:
    case [first, *_]:
        result = first
""",
            max_steps=1000,
        )
        assert local_vars[VarName("result")] == 1

    def test_nested_star_pattern(self):
        _, local_vars = _run_python(
            """\
data = [1, [2, 3, 4], 5]
match data:
    case [a, [b, *inner], c]:
        result_a = a
        result_b = b
        result_c = c
        inner_len = len(inner)
        inner_0 = inner[0]
        inner_1 = inner[1]
""",
            max_steps=2000,
        )
        assert local_vars[VarName("result_a")] == 1
        assert local_vars[VarName("result_b")] == 2
        assert local_vars[VarName("result_c")] == 5
        assert local_vars[VarName("inner_len")] == 2
        assert local_vars[VarName("inner_0")] == 3
        assert local_vars[VarName("inner_1")] == 4


class TestCompoundPatterns:
    """Complex scenarios combining multiple pattern types."""

    def test_array_of_points_with_star(self):
        """Class patterns inside a list with star — verify types + field values of rest."""
        vm, local_vars = _run_python(
            """\
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

points = [Point(1, 2), Point(3, 4), Point(5, 6)]
match points:
    case [Point(x=first_x, y=first_y), *rest]:
        rx = first_x
        ry = first_y
        rest_len = len(rest)
        r0x = rest[0].x
        r0y = rest[0].y
        r1x = rest[1].x
        r1y = rest[1].y
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("rx")], int)
            and local_vars[VarName("rx")] == 1
        )
        assert (
            isinstance(local_vars[VarName("ry")], int)
            and local_vars[VarName("ry")] == 2
        )
        assert (
            isinstance(local_vars[VarName("rest_len")], int)
            and local_vars[VarName("rest_len")] == 2
        )
        assert (
            isinstance(local_vars[VarName("r0x")], int)
            and local_vars[VarName("r0x")] == 3
        )
        assert (
            isinstance(local_vars[VarName("r0y")], int)
            and local_vars[VarName("r0y")] == 4
        )
        assert (
            isinstance(local_vars[VarName("r1x")], int)
            and local_vars[VarName("r1x")] == 5
        )
        assert (
            isinstance(local_vars[VarName("r1y")], int)
            and local_vars[VarName("r1y")] == 6
        )
        # Verify rest elements are Point objects via heap type_hint
        rest_addr = _heap_addr(local_vars[VarName("rest")])
        r0_addr = _heap_addr(
            vm.heap[str(rest_addr)].fields[FieldName("0", FieldKind.INDEX)].value
        )
        r1_addr = _heap_addr(
            vm.heap[str(rest_addr)].fields[FieldName("1", FieldKind.INDEX)].value
        )
        assert vm.heap[str(r0_addr)].type_hint == scalar("Point")
        assert vm.heap[str(r1_addr)].type_hint == scalar("Point")

    def test_dict_inside_sequence_with_star(self):
        """Dict pattern inside list with star — verify extracted fields + rest element fields."""
        _, local_vars = _run_python(
            """\
data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
match data:
    case [{"name": first_name, "age": first_age}, *rest]:
        rn = first_name
        ra = first_age
        rest_len = len(rest)
        rest0_name = rest[0]["name"]
        rest0_age = rest[0]["age"]
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("rn")], str)
            and local_vars[VarName("rn")] == "Alice"
        )
        assert (
            isinstance(local_vars[VarName("ra")], int)
            and local_vars[VarName("ra")] == 30
        )
        assert (
            isinstance(local_vars[VarName("rest_len")], int)
            and local_vars[VarName("rest_len")] == 1
        )
        assert (
            isinstance(local_vars[VarName("rest0_name")], str)
            and local_vars[VarName("rest0_name")] == "Bob"
        )
        assert (
            isinstance(local_vars[VarName("rest0_age")], int)
            and local_vars[VarName("rest0_age")] == 25
        )

    def test_guard_with_sequence_captures(self):
        """Guard referencing captured variables from a tuple pattern."""
        _, local_vars = _run_python(
            """\
data = (10, 20)
match data:
    case (a, b) if a + b > 50:
        result = "big"
        ra = a
        rb = b
    case (a, b) if a + b <= 50:
        result = "small"
        ra = a
        rb = b
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "small"
        )
        assert (
            isinstance(local_vars[VarName("ra")], int)
            and local_vars[VarName("ra")] == 10
        )
        assert (
            isinstance(local_vars[VarName("rb")], int)
            and local_vars[VarName("rb")] == 20
        )

    def test_class_pattern_with_guard(self):
        """Class keyword pattern with guard on field product — verify matched object type."""
        vm, local_vars = _run_python(
            """\
class Rect:
    def __init__(self, w, h):
        self.w = w
        self.h = h

r = Rect(10, 5)
match r:
    case Rect(w=w, h=h) if w * h > 100:
        result = "large"
        rw = w
        rh = h
    case Rect(w=w, h=h):
        result = "small"
        rw = w
        rh = h
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "small"
        )
        assert (
            isinstance(local_vars[VarName("rw")], int)
            and local_vars[VarName("rw")] == 10
        )
        assert (
            isinstance(local_vars[VarName("rh")], int)
            and local_vars[VarName("rh")] == 5
        )
        # Verify r is a Rect via heap type_hint
        r_addr = _heap_addr(local_vars[VarName("r")])
        assert vm.heap[str(r_addr)].type_hint == scalar("Rect")

    def test_mixed_pattern_types_across_cases(self):
        """Dict matches before list — verify each captured field individually."""
        _, local_vars = _run_python(
            """\
data = {"type": "point", "x": 3, "y": 4}
match data:
    case [a, b]:
        result = "list"
    case {"type": t, "x": x, "y": y}:
        result = x + y
        rt = t
        rx = x
        ry = y
    case _:
        result = "other"
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 7
        )
        assert (
            isinstance(local_vars[VarName("rt")], str)
            and local_vars[VarName("rt")] == "point"
        )
        assert (
            isinstance(local_vars[VarName("rx")], int)
            and local_vars[VarName("rx")] == 3
        )
        assert (
            isinstance(local_vars[VarName("ry")], int)
            and local_vars[VarName("ry")] == 4
        )

    def test_star_with_class_field_access(self):
        """Star captures rest of array after class-pattern head — verify types + all fields."""
        vm, local_vars = _run_python(
            """\
class Item:
    def __init__(self, name, price):
        self.name = name
        self.price = price

cart = [Item("apple", 1), Item("banana", 2), Item("cherry", 3)]
match cart:
    case [Item(name=first_name, price=first_price), *others]:
        rn = first_name
        rp = first_price
        others_len = len(others)
        o0_name = others[0].name
        o0_price = others[0].price
        o1_name = others[1].name
        o1_price = others[1].price
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("rn")], str)
            and local_vars[VarName("rn")] == "apple"
        )
        assert (
            isinstance(local_vars[VarName("rp")], int)
            and local_vars[VarName("rp")] == 1
        )
        assert (
            isinstance(local_vars[VarName("others_len")], int)
            and local_vars[VarName("others_len")] == 2
        )
        assert (
            isinstance(local_vars[VarName("o0_name")], str)
            and local_vars[VarName("o0_name")] == "banana"
        )
        assert (
            isinstance(local_vars[VarName("o0_price")], int)
            and local_vars[VarName("o0_price")] == 2
        )
        assert (
            isinstance(local_vars[VarName("o1_name")], str)
            and local_vars[VarName("o1_name")] == "cherry"
        )
        assert (
            isinstance(local_vars[VarName("o1_price")], int)
            and local_vars[VarName("o1_price")] == 3
        )
        # Verify others elements are Item objects via heap type_hint
        others_addr = _heap_addr(local_vars[VarName("others")])
        o0_addr = _heap_addr(
            vm.heap[str(others_addr)].fields[FieldName("0", FieldKind.INDEX)].value
        )
        o1_addr = _heap_addr(
            vm.heap[str(others_addr)].fields[FieldName("1", FieldKind.INDEX)].value
        )
        assert vm.heap[str(o0_addr)].type_hint == scalar("Item")
        assert vm.heap[str(o1_addr)].type_hint == scalar("Item")

    def test_guard_rejects_then_next_case_matches(self):
        """First case guard fails, second case (same pattern, different guard) matches."""
        _, local_vars = _run_python(
            """\
data = (3, 7)
match data:
    case (a, b) if a > b:
        result = "a_bigger"
    case (a, b) if b > a:
        result = "b_bigger"
        ra = a
        rb = b
    case _:
        result = "equal"
""",
            max_steps=2000,
        )
        assert local_vars[VarName("result")] == "b_bigger"
        assert local_vars[VarName("ra")] == 3
        assert local_vars[VarName("rb")] == 7


class TestStressPatterns:
    """Complex compound scenarios that stress the pattern matching infrastructure."""

    def test_class_containing_dict_containing_list_with_star(self):
        """3-level nesting: Class -> dict -> list with star capture."""
        vm, local_vars = _run_python(
            """\
class Response:
    def __init__(self, data):
        self.data = data

resp = Response({"users": [10, 20, 30], "count": 3})
match resp:
    case Response(data={"users": [first, *rest], "count": n}):
        rf = first
        rn = n
        rest_len = len(rest)
        r0 = rest[0]
        r1 = rest[1]
""",
            max_steps=5000,
        )
        assert (
            isinstance(local_vars[VarName("rf")], int)
            and local_vars[VarName("rf")] == 10
        )
        assert (
            isinstance(local_vars[VarName("rn")], int)
            and local_vars[VarName("rn")] == 3
        )
        assert (
            isinstance(local_vars[VarName("rest_len")], int)
            and local_vars[VarName("rest_len")] == 2
        )
        assert (
            isinstance(local_vars[VarName("r0")], int)
            and local_vars[VarName("r0")] == 20
        )
        assert (
            isinstance(local_vars[VarName("r1")], int)
            and local_vars[VarName("r1")] == 30
        )
        r_addr = _heap_addr(local_vars[VarName("resp")])
        assert vm.heap[str(r_addr)].type_hint == scalar("Response")

    def test_multi_case_dispatch_with_guards(self):
        """Multiple cases with different pattern shapes + guards + fall-through."""
        vm, local_vars = _run_python(
            """\
class Cmd:
    def __init__(self, kind, args):
        self.kind = kind
        self.args = args

cmd = Cmd("move", [1, 2, 3])
match cmd:
    case Cmd(kind="quit", args=[]):
        action = "quit"
        detail = 0
    case Cmd(kind="move", args=[x, y, z]) if x + y + z > 100:
        action = "big_move"
        detail = x + y + z
    case Cmd(kind="move", args=[x, y, z]):
        action = "move"
        detail = x + y + z
    case _:
        action = "unknown"
        detail = -1
""",
            max_steps=5000,
        )
        assert (
            isinstance(local_vars[VarName("action")], str)
            and local_vars[VarName("action")] == "move"
        )
        assert (
            isinstance(local_vars[VarName("detail")], int)
            and local_vars[VarName("detail")] == 6
        )
        cmd_addr = _heap_addr(local_vars[VarName("cmd")])
        assert vm.heap[str(cmd_addr)].type_hint == scalar("Cmd")

    def test_as_pattern_wrapping_sequence(self):
        """As-pattern captures the whole subject after structural match succeeds."""
        _, local_vars = _run_python(
            """\
data = (1, 2, 3)
match data:
    case (1, b, c) as whole:
        rb = b
        rc = c
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("rb")], int)
            and local_vars[VarName("rb")] == 2
        )
        assert (
            isinstance(local_vars[VarName("rc")], int)
            and local_vars[VarName("rc")] == 3
        )

    def test_many_alternative_or_pattern(self):
        """Or-pattern with 4+ alternatives per case across multiple cases."""
        _, local_vars = _run_python(
            """\
status = 404
match status:
    case 200 | 201 | 204:
        category = "success"
    case 301 | 302 | 307:
        category = "redirect"
    case 400 | 401 | 403 | 404:
        category = "client_error"
    case 500 | 502 | 503:
        category = "server_error"
    case _:
        category = "unknown"
""",
            max_steps=2000,
        )
        assert isinstance(local_vars[VarName("category")], str)
        assert local_vars[VarName("category")] == "client_error"

    def test_binary_tree_nested_class_patterns(self):
        """3-level deep nested class patterns on a binary tree."""
        vm, local_vars = _run_python(
            """\
class Node:
    def __init__(self, val, left, right):
        self.val = val
        self.left = left
        self.right = right

tree = Node(1, Node(2, Node(4, 0, 0), Node(5, 0, 0)), Node(3, 0, 0))
match tree:
    case Node(val=root_val, left=Node(val=left_val, left=Node(val=ll_val))):
        rv = root_val
        lv_val = left_val
        llv = ll_val
""",
            max_steps=5000,
        )
        assert (
            isinstance(local_vars[VarName("rv")], int)
            and local_vars[VarName("rv")] == 1
        )
        assert (
            isinstance(local_vars[VarName("lv_val")], int)
            and local_vars[VarName("lv_val")] == 2
        )
        assert (
            isinstance(local_vars[VarName("llv")], int)
            and local_vars[VarName("llv")] == 4
        )
        tree_addr = _heap_addr(local_vars[VarName("tree")])
        assert vm.heap[str(tree_addr)].type_hint == scalar("Node")
        left_addr = _heap_addr(vm.heap[str(tree_addr)].fields[FieldName("left")].value)
        assert vm.heap[str(left_addr)].type_hint == scalar("Node")
        ll_addr = _heap_addr(vm.heap[str(left_addr)].fields[FieldName("left")].value)
        assert vm.heap[str(ll_addr)].type_hint == scalar("Node")

    def test_guard_with_pythagorean_computation(self):
        """Guard uses x*x + y*y == 25 on destructured class fields."""
        _, local_vars = _run_python(
            """\
class Vec:
    def __init__(self, x, y):
        self.x = x
        self.y = y

v = Vec(3, 4)
match v:
    case Vec(x=x, y=y) if x * x + y * y > 25:
        label = "far"
    case Vec(x=x, y=y) if x * x + y * y == 25:
        label = "boundary"
    case Vec(x=x, y=y):
        label = "near"
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("label")], str)
            and local_vars[VarName("label")] == "boundary"
        )
        assert (
            isinstance(local_vars[VarName("x")], int) and local_vars[VarName("x")] == 3
        )
        assert (
            isinstance(local_vars[VarName("y")], int) and local_vars[VarName("y")] == 4
        )

    def test_star_with_guard_on_rest_length(self):
        """Star capture with guard checking len(rest) > threshold."""
        _, local_vars = _run_python(
            """\
items = [1, 2, 3, 4, 5]
match items:
    case [first, *rest] if len(rest) > 3:
        result = "long"
        rf = first
        rl = len(rest)
    case [first, *rest]:
        result = "short"
        rf = first
        rl = len(rest)
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "long"
        )
        assert (
            isinstance(local_vars[VarName("rf")], int)
            and local_vars[VarName("rf")] == 1
        )
        assert (
            isinstance(local_vars[VarName("rl")], int)
            and local_vars[VarName("rl")] == 4
        )

    def test_dict_pattern_all_fields_extracted(self):
        """Dict pattern matching and extracting all keys."""
        _, local_vars = _run_python(
            """\
config = {"host": "localhost", "port": 8080, "debug": True}
match config:
    case {"host": h, "port": p, "debug": d}:
        addr = h
        port = p
        is_debug = d
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("addr")], str)
            and local_vars[VarName("addr")] == "localhost"
        )
        assert (
            isinstance(local_vars[VarName("port")], int)
            and local_vars[VarName("port")] == 8080
        )
        assert local_vars[VarName("is_debug")] is True


class TestOrPatternWithBindings:
    def test_or_pattern_tuple_with_captures(self):
        """case (1, x) | (2, x): with (2, 99) — x bound to 99."""
        _, local_vars = _run_python(
            """\
data = (2, 99)
match data:
    case (1, x) | (2, x):
        result = x
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 99
        )

    def test_or_pattern_first_alternative_binds(self):
        """case (1, x) | (2, x): with (1, 77) — first alt matches, x bound to 77."""
        _, local_vars = _run_python(
            """\
data = (1, 77)
match data:
    case (1, x) | (2, x):
        result = x
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 77
        )

    def test_or_pattern_list_with_captures(self):
        """case [1, y] | [2, y]: with [2, 42] — y bound to 42."""
        _, local_vars = _run_python(
            """\
data = [2, 42]
match data:
    case [1, y] | [2, y]:
        result = y
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 42
        )

    def test_or_pattern_no_match_falls_through(self):
        """Neither alternative matches — falls to default."""
        _, local_vars = _run_python(
            """\
data = (3, 50)
result = "default"
match data:
    case (1, x) | (2, x):
        result = x
    case _:
        result = "default"
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "default"
        )

    def test_or_pattern_with_class_alternatives(self):
        """Or-pattern across different class types sharing a field name."""
        _, local_vars = _run_python(
            """\
class Dog:
    def __init__(self, name):
        self.name = name

class Cat:
    def __init__(self, name):
        self.name = name

pet = Cat("Whiskers")
match pet:
    case Dog(name=n) | Cat(name=n):
        result = n
    case _:
        result = "unknown"
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "Whiskers"
        )

    def test_or_pattern_with_star_in_alternatives(self):
        """Or-pattern where each alternative uses star capture."""
        _, local_vars = _run_python(
            """\
data = [0, 10, 20, 30]
match data:
    case [1, *rest] | [0, *rest]:
        first_rest = rest[0]
        rest_len = len(rest)
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("first_rest")], int)
            and local_vars[VarName("first_rest")] == 10
        )
        assert (
            isinstance(local_vars[VarName("rest_len")], int)
            and local_vars[VarName("rest_len")] == 3
        )

    def test_or_pattern_nested_inside_sequence(self):
        """Or-pattern as an element inside a tuple pattern."""
        _, local_vars = _run_python(
            """\
data = ("error", 404)
match data:
    case ("error" | "fail", code):
        result = code
    case _:
        result = 0
""",
            max_steps=2000,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 404
        )

    def test_or_pattern_with_guard_on_capture(self):
        """Or-pattern with guard referencing the captured variable."""
        _, local_vars = _run_python(
            """\
data = (2, 100)
match data:
    case (1, x) | (2, x) if x > 50:
        result = "big"
        rv = x
    case (1, x) | (2, x):
        result = "small"
        rv = x
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], str)
            and local_vars[VarName("result")] == "big"
        )
        assert (
            isinstance(local_vars[VarName("rv")], int)
            and local_vars[VarName("rv")] == 100
        )

    def test_or_pattern_with_mapping_alternatives(self):
        """Or-pattern across dict patterns sharing a key."""
        _, local_vars = _run_python(
            """\
event = {"type": "click", "x": 42}
match event:
    case {"type": "click", "x": val} | {"type": "tap", "x": val}:
        result = val
    case _:
        result = -1
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 42
        )

    def test_three_way_or_pattern(self):
        """Three alternatives in an or-pattern, third matches."""
        _, local_vars = _run_python(
            """\
data = (3, 99)
match data:
    case (1, x) | (2, x) | (3, x):
        result = x
    case _:
        result = 0
""",
            max_steps=3000,
        )
        assert (
            isinstance(local_vars[VarName("result")], int)
            and local_vars[VarName("result")] == 99
        )
