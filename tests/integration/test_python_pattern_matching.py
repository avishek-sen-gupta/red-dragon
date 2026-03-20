"""Integration tests: Python pattern matching through VM execution."""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


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

    @pytest.mark.xfail(
        reason="Positional class patterns require __match_args__ / index-based "
        "field access on user-defined classes, which the VM does not support yet. "
        "Filed as red-dragon issue for __match_args__ support."
    )
    def test_class_positional(self):
        _, local_vars = _run_python(
            """\
class Pair:
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
    @pytest.mark.xfail(reason="Star patterns not yet implemented (red-dragon-2uke)")
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

    @pytest.mark.xfail(
        reason="Or-patterns with bindings not yet implemented (red-dragon-fv2p)"
    )
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
