"""Integration tests for Lua method_index_expression -- end-to-end execution.

Verifies that `obj:method()` colon-call syntax is lowered and executed
through the full parse -> lower -> execute pipeline.
"""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_lua(source: str, max_steps: int = 200):
    """Run a Lua program and return (vm, frame.local_vars)."""
    vm = run(source, language=Language.LUA, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestLuaMethodIndexExecution:
    def test_method_call_executes(self):
        """obj:method() should execute without errors."""
        _, local_vars = _run_lua("""\
local t = {}
t.greet = function(self) return "hello" end
local r = t:greet()
""")
        assert "r" in local_vars

    @pytest.mark.xfail(reason="Lua colon-call method returns produce symbolic values")
    def test_method_call_with_args_executes(self):
        """obj:method(arg) should pass arguments correctly."""
        _, local_vars = _run_lua("""\
local t = {}
t.add = function(self, x) return x end
local r = t:add(42)
""")
        assert local_vars["r"] == 42

    def test_method_call_chained(self):
        """obj:method1():method2() chained call should not crash."""
        _, local_vars = _run_lua("""\
local t = {}
t.get = function(self) return self end
t.val = function(self) return 42 end
local r = t:get():val()
""")
        assert "r" in local_vars
