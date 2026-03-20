"""Integration tests: Python pattern matching through VM execution."""

from __future__ import annotations

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
