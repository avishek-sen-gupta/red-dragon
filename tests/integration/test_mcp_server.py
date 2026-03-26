"""Integration tests for RedDragon MCP server — full round-trip tool calls."""

from __future__ import annotations

from mcp_server.session import clear_session
from mcp_server.tools import (
    handle_analyze_program,
    handle_get_call_chain,
    handle_get_function_summary,
    handle_get_ir,
    handle_get_state,
    handle_load_program,
    handle_run_to_end,
    handle_step,
)
from interpreter.var_name import VarName
from mcp_server.resources import (
    handle_source_resource,
    handle_ir_resource,
    handle_cfg_resource,
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
        assert load_result[VarName("total_steps")] > 0

        end_result = handle_run_to_end()
        assert end_result[VarName("done")] is True
        assert end_result[VarName("variables")]["result"] == 20

    def test_analyze_then_load_and_step(self):
        """Analysis tools work independently of execution session."""
        analysis = handle_analyze_program(MULTI_FUNC_SOURCE, "python")
        assert len(analysis["functions"]) >= 3

        handle_load_program(MULTI_FUNC_SOURCE, "python")
        step_result = handle_step(5)
        assert step_result[VarName("steps_executed")] == 5

        state = handle_get_state()
        assert state["step_index"] == 5

    def test_call_chain_matches_execution(self):
        """Call chain shows n -> double -> add, execution produces result == 20."""
        chain = handle_get_call_chain(MULTI_FUNC_SOURCE, "python")
        assert len(chain["chains"]) >= 1

        handle_load_program(MULTI_FUNC_SOURCE, "python")
        end = handle_run_to_end()
        assert end["variables"]["result"] == 20

    def test_function_summary_for_add(self):
        summary = handle_get_function_summary(MULTI_FUNC_SOURCE, "python", "add")
        assert summary["params"] == ["a", "b"]
        assert len(summary["flows"]) == 2

    def test_get_ir_for_function(self):
        handle_load_program(MULTI_FUNC_SOURCE, "python")
        ir = handle_get_ir("add")
        assert len(ir["blocks"]) >= 1

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
