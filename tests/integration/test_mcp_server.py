"""Integration tests for RedDragon MCP server — full round-trip tool calls."""

from __future__ import annotations

from mcp_server.resources import (
    handle_cfg_resource,
    handle_ir_resource,
    handle_source_resource,
)
from mcp_server.session import clear_session
from mcp_server.tools import (
    handle_get_ir,
    handle_get_state,
    handle_load_program,
    handle_run_to_end,
    handle_step,
)

MULTI_FUNC_SOURCE = """\
def add(a, b):
    return a + b

def double(x):
    return add(x, x)

def quadruple(n):
    return double(double(n))

result = quadruple(5)
"""


class TestFullRoundTrip:
    def setup_method(self):
        clear_session()

    def test_load_step_and_verify_result(self):
        """Load quadruple program, run to end, verify result == 20."""
        load_result = handle_load_program(MULTI_FUNC_SOURCE, "python", max_steps=300)
        assert load_result["total_steps"] > 0

        end_result = handle_run_to_end()
        assert end_result["done"] is True
        assert end_result["variables"]["result"] == 20

    def test_load_then_step(self):
        handle_load_program(MULTI_FUNC_SOURCE, "python")
        step_result = handle_step(5)
        assert step_result["steps_executed"] == 5

        state = handle_get_state()
        assert state["step_index"] == 5

    def test_get_ir_for_function(self):
        handle_load_program(MULTI_FUNC_SOURCE, "python")
        ir = handle_get_ir("add")
        assert [str(b["label"]) for b in ir["blocks"]] == ["func_add_0"]

    def test_resources_after_load(self):
        handle_load_program(MULTI_FUNC_SOURCE, "python")
        source = handle_source_resource()
        assert "quadruple" in source

        ir = handle_ir_resource()
        assert "func_add" in ir or "symbolic" in ir

        cfg = handle_cfg_resource()
        assert "entry" in cfg

    def test_resources_before_load(self):
        source = handle_source_resource()
        assert "No program loaded" in source
