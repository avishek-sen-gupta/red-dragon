"""Integration tests: Python pattern matching through VM execution."""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals
from interpreter.type_expr import scalar
from interpreter.vm import _heap_addr


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
        assert local_vars["y"] == 20

    def test_literal_str_match(self):
        _, local_vars = _run_python("""\
x = "hello"
match x:
    case "world":
        y = 1
    case "hello":
        y = 2
""")
        assert local_vars["y"] == 2


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
        assert local_vars["y"] == 99


class TestCaptureMatch:
    def test_capture_binds_value(self):
        _, local_vars = _run_python("""\
x = 42
match x:
    case val:
        y = val
""")
        assert local_vars["y"] == 42


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
        assert local_vars["y"] == 999

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
        assert local_vars["y"] == 0


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
        assert local_vars["z"] == 7


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
        assert local_vars["z"] == 30


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
        assert local_vars["z"] == 6


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
        assert local_vars["result"] == "Alice"


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
        assert local_vars["y"] == "yes"


class TestAsPattern:
    def test_as_pattern(self):
        _, local_vars = _run_python("""\
x = 42
match x:
    case val as name:
        y = name
""")
        assert local_vars["y"] == 42


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
        assert local_vars["y"] == "non-positive"


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
        assert local_vars["result"] == 4

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
        assert local_vars["result"] == 30


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
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 4

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
        assert isinstance(local_vars["ra"], int) and local_vars["ra"] == 3
        assert isinstance(local_vars["rb"], int) and local_vars["rb"] == 4

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
            isinstance(local_vars["result"], str) and local_vars["result"] == "default"
        )

    def test_class_positional_in_sequence_with_star(self):
        """Positional class patterns inside a list with star."""
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
""",
            max_steps=5000,
        )
        assert isinstance(local_vars["ra"], int) and local_vars["ra"] == 1
        assert isinstance(local_vars["rb"], int) and local_vars["rb"] == 2
        assert isinstance(local_vars["rest_len"], int) and local_vars["rest_len"] == 2


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
        assert local_vars["result"] == "no match"


class TestValuePattern:
    @pytest.mark.xfail(
        reason="Value patterns (dotted constants) not yet implemented (red-dragon-zuyo)"
    )
    def test_value_pattern_rejects_mismatch(self):
        """Color.RED pattern must reject non-matching value — currently captures anything."""
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
            max_steps=1000,
        )
        assert local_vars["result"] == "no match"


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
        assert local_vars["result"] == 1

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
        assert local_vars["result"] == 99


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
        assert local_vars["result"] == 6

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
        assert local_vars["result"] is True


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
        assert local_vars["result_first"] == 1
        assert local_vars["rest_len"] == 3
        assert local_vars["rest_0"] == 2
        assert local_vars["rest_1"] == 3
        assert local_vars["rest_2"] == 4

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
        assert local_vars["result_last"] == 3
        assert local_vars["head_len"] == 2
        assert local_vars["head_0"] == 1
        assert local_vars["head_1"] == 2

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
        assert local_vars["result_a"] == 1
        assert local_vars["result_z"] == 5
        assert local_vars["mid_len"] == 3
        assert local_vars["mid_0"] == 2
        assert local_vars["mid_1"] == 3
        assert local_vars["mid_2"] == 4

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
        assert local_vars["result_a"] == 1
        assert local_vars["result_b"] == 2
        assert local_vars["rest_len"] == 0

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
        assert local_vars["result"] == 10
        assert local_vars["rest_0"] == 20
        assert local_vars["rest_1"] == 30

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
        assert local_vars["result"] == "default"

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
        assert local_vars["result"] == 1

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
        assert local_vars["result_a"] == 1
        assert local_vars["result_b"] == 2
        assert local_vars["result_c"] == 5
        assert local_vars["inner_len"] == 2
        assert local_vars["inner_0"] == 3
        assert local_vars["inner_1"] == 4


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
        assert isinstance(local_vars["rx"], int) and local_vars["rx"] == 1
        assert isinstance(local_vars["ry"], int) and local_vars["ry"] == 2
        assert isinstance(local_vars["rest_len"], int) and local_vars["rest_len"] == 2
        assert isinstance(local_vars["r0x"], int) and local_vars["r0x"] == 3
        assert isinstance(local_vars["r0y"], int) and local_vars["r0y"] == 4
        assert isinstance(local_vars["r1x"], int) and local_vars["r1x"] == 5
        assert isinstance(local_vars["r1y"], int) and local_vars["r1y"] == 6
        # Verify rest elements are Point objects via heap type_hint
        rest_addr = _heap_addr(local_vars["rest"])
        r0_addr = _heap_addr(vm.heap[rest_addr].fields["0"].value)
        r1_addr = _heap_addr(vm.heap[rest_addr].fields["1"].value)
        assert vm.heap[r0_addr].type_hint == scalar("Point")
        assert vm.heap[r1_addr].type_hint == scalar("Point")

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
        assert isinstance(local_vars["rn"], str) and local_vars["rn"] == "Alice"
        assert isinstance(local_vars["ra"], int) and local_vars["ra"] == 30
        assert isinstance(local_vars["rest_len"], int) and local_vars["rest_len"] == 1
        assert (
            isinstance(local_vars["rest0_name"], str)
            and local_vars["rest0_name"] == "Bob"
        )
        assert (
            isinstance(local_vars["rest0_age"], int) and local_vars["rest0_age"] == 25
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
        assert isinstance(local_vars["result"], str) and local_vars["result"] == "small"
        assert isinstance(local_vars["ra"], int) and local_vars["ra"] == 10
        assert isinstance(local_vars["rb"], int) and local_vars["rb"] == 20

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
        assert isinstance(local_vars["result"], str) and local_vars["result"] == "small"
        assert isinstance(local_vars["rw"], int) and local_vars["rw"] == 10
        assert isinstance(local_vars["rh"], int) and local_vars["rh"] == 5
        # Verify r is a Rect via heap type_hint
        r_addr = _heap_addr(local_vars["r"])
        assert vm.heap[r_addr].type_hint == scalar("Rect")

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
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 7
        assert isinstance(local_vars["rt"], str) and local_vars["rt"] == "point"
        assert isinstance(local_vars["rx"], int) and local_vars["rx"] == 3
        assert isinstance(local_vars["ry"], int) and local_vars["ry"] == 4

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
        assert isinstance(local_vars["rn"], str) and local_vars["rn"] == "apple"
        assert isinstance(local_vars["rp"], int) and local_vars["rp"] == 1
        assert (
            isinstance(local_vars["others_len"], int) and local_vars["others_len"] == 2
        )
        assert (
            isinstance(local_vars["o0_name"], str) and local_vars["o0_name"] == "banana"
        )
        assert isinstance(local_vars["o0_price"], int) and local_vars["o0_price"] == 2
        assert (
            isinstance(local_vars["o1_name"], str) and local_vars["o1_name"] == "cherry"
        )
        assert isinstance(local_vars["o1_price"], int) and local_vars["o1_price"] == 3
        # Verify others elements are Item objects via heap type_hint
        others_addr = _heap_addr(local_vars["others"])
        o0_addr = _heap_addr(vm.heap[others_addr].fields["0"].value)
        o1_addr = _heap_addr(vm.heap[others_addr].fields["1"].value)
        assert vm.heap[o0_addr].type_hint == scalar("Item")
        assert vm.heap[o1_addr].type_hint == scalar("Item")

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
        assert local_vars["result"] == "b_bigger"
        assert local_vars["ra"] == 3
        assert local_vars["rb"] == 7


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
        assert isinstance(local_vars["rf"], int) and local_vars["rf"] == 10
        assert isinstance(local_vars["rn"], int) and local_vars["rn"] == 3
        assert isinstance(local_vars["rest_len"], int) and local_vars["rest_len"] == 2
        assert isinstance(local_vars["r0"], int) and local_vars["r0"] == 20
        assert isinstance(local_vars["r1"], int) and local_vars["r1"] == 30
        r_addr = _heap_addr(local_vars["resp"])
        assert vm.heap[r_addr].type_hint == scalar("Response")

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
        assert isinstance(local_vars["action"], str) and local_vars["action"] == "move"
        assert isinstance(local_vars["detail"], int) and local_vars["detail"] == 6
        cmd_addr = _heap_addr(local_vars["cmd"])
        assert vm.heap[cmd_addr].type_hint == scalar("Cmd")

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
        assert isinstance(local_vars["rb"], int) and local_vars["rb"] == 2
        assert isinstance(local_vars["rc"], int) and local_vars["rc"] == 3

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
        assert isinstance(local_vars["category"], str)
        assert local_vars["category"] == "client_error"

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
        assert isinstance(local_vars["rv"], int) and local_vars["rv"] == 1
        assert isinstance(local_vars["lv_val"], int) and local_vars["lv_val"] == 2
        assert isinstance(local_vars["llv"], int) and local_vars["llv"] == 4
        tree_addr = _heap_addr(local_vars["tree"])
        assert vm.heap[tree_addr].type_hint == scalar("Node")
        left_addr = _heap_addr(vm.heap[tree_addr].fields["left"].value)
        assert vm.heap[left_addr].type_hint == scalar("Node")
        ll_addr = _heap_addr(vm.heap[left_addr].fields["left"].value)
        assert vm.heap[ll_addr].type_hint == scalar("Node")

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
            isinstance(local_vars["label"], str) and local_vars["label"] == "boundary"
        )
        assert isinstance(local_vars["x"], int) and local_vars["x"] == 3
        assert isinstance(local_vars["y"], int) and local_vars["y"] == 4

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
        assert isinstance(local_vars["result"], str) and local_vars["result"] == "long"
        assert isinstance(local_vars["rf"], int) and local_vars["rf"] == 1
        assert isinstance(local_vars["rl"], int) and local_vars["rl"] == 4

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
        assert isinstance(local_vars["addr"], str) and local_vars["addr"] == "localhost"
        assert isinstance(local_vars["port"], int) and local_vars["port"] == 8080
        assert local_vars["is_debug"] is True


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
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 99

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
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 77

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
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 42

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
            isinstance(local_vars["result"], str) and local_vars["result"] == "default"
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
            isinstance(local_vars["result"], str) and local_vars["result"] == "Whiskers"
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
            isinstance(local_vars["first_rest"], int) and local_vars["first_rest"] == 10
        )
        assert isinstance(local_vars["rest_len"], int) and local_vars["rest_len"] == 3

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
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 404

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
        assert isinstance(local_vars["result"], str) and local_vars["result"] == "big"
        assert isinstance(local_vars["rv"], int) and local_vars["rv"] == 100

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
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 42

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
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 99
