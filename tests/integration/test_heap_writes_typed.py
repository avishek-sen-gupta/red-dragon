"""Integration tests for heap_writes TypedValue migration — end-to-end execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _run_python(source: str, max_steps: int = 200):
    """Run a Python program and return the VM."""
    return run(source, language=Language.PYTHON, max_steps=max_steps)


class TestStoreFieldLoadFieldRoundtrip:
    """End-to-end STORE_FIELD → LOAD_FIELD roundtrip via run()."""

    def test_object_field_int(self):
        """Assign int to object field, read it back."""
        vm = _run_python("""\
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
p = Point(3, 7)
result = p.x + p.y
""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["result"] == 10

    def test_object_field_string(self):
        """Assign string to object field, read it back."""
        vm = _run_python("""\
class Dog:
    def __init__(self, name):
        self.name = name
d = Dog("Rex")
result = d.name
""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["result"] == "Rex"

    def test_object_field_reassignment(self):
        """Reassign a field and verify the new value is stored."""
        vm = _run_python("""\
class Box:
    def __init__(self, val):
        self.val = val
b = Box(10)
b.val = 42
result = b.val
""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["result"] == 42


class TestStoreIndexLoadIndexRoundtrip:
    """End-to-end STORE_INDEX → LOAD_INDEX roundtrip via run()."""

    def test_array_index_int(self):
        """Write int to array index, read it back."""
        vm = _run_python("""\
arr = [0, 0, 0]
arr[1] = 99
result = arr[1]
""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["result"] == 99

    def test_array_index_string(self):
        """Write string to array index, read it back."""
        vm = _run_python("""\
arr = ["a", "b", "c"]
arr[0] = "z"
result = arr[0]
""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["result"] == "z"
