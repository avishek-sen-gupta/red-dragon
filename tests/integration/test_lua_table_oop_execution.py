"""Integration tests: Lua table-based OOP produces concrete results."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_lua(source: str, max_steps: int = 500):
    vm = run(source, language=Language.LUA, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestLuaTableMethodDispatch:
    def test_table_method_returns_concrete(self):
        """Counter.new() should return a concrete table, not symbolic."""
        result = _run_lua("""
Counter = {}

function Counter.new()
    local self = {count = 0}
    return self
end

counter = Counter.new()
""")
        counter = result["counter"]
        assert isinstance(counter, str) and counter.startswith(
            "obj_"
        ), f"counter should be a heap address, got {counter!r}"

    def test_method_chaining_produces_answer(self):
        """Full method chaining should produce answer = 6."""
        result = _run_lua("""
Counter = {}

function Counter.new()
    local self = {count = 0}
    return self
end

function Counter.increment(self)
    self.count = self.count + 1
    return self
end

function Counter.get_value(self)
    return self.count
end

counter = Counter.new()
Counter.increment(counter)
Counter.increment(counter)
Counter.increment(counter)
Counter.increment(counter)
Counter.increment(counter)
Counter.increment(counter)
answer = Counter.get_value(counter)
""")
        assert result["answer"] == 6

    def test_method_modifies_table_field(self):
        """Calling a method that modifies self.count should persist the change."""
        result = _run_lua("""
Box = {}

function Box.new(val)
    local self = {value = val}
    return self
end

function Box.get(self)
    return self.value
end

b = Box.new(42)
answer = Box.get(b)
""")
        assert result["answer"] == 42
