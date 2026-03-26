"""Integration tests for Lua method_index_expression -- end-to-end execution.

Verifies that `obj:method()` colon-call syntax is lowered and executed
through the full parse -> lower -> execute pipeline.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.var_name import VarName


def _run_lua(source: str, max_steps: int = 200):
    """Run a Lua program and return (vm, frame.local_vars)."""
    vm = run(source, language=Language.LUA, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestLuaMethodIndexExecution:
    def test_method_call_executes(self):
        """obj:method() should return the correct value."""
        _, local_vars = _run_lua("""\
local t = {}
t.greet = function(self) return "hello" end
local r = t:greet()
""")
        assert local_vars[VarName("r")] == "hello"

    def test_method_call_with_args_executes(self):
        """obj:method(arg) should pass arguments correctly."""
        _, local_vars = _run_lua("""\
local t = {}
t.add = function(self, x) return x end
local r = t:add(42)
""")
        assert local_vars[VarName("r")] == 42

    def test_method_call_chained(self):
        """obj:method1():method2() chained call should return correct value."""
        _, local_vars = _run_lua("""\
local t = {}
t.get = function(self) return self end
t.val = function(self) return 42 end
local r = t:get():val()
""")
        assert local_vars[VarName("r")] == 42
