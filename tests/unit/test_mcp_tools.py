"""Tests for MCP tool handler functions."""

from __future__ import annotations

import json

from mcp_server.tools import (
    handle_analyze_program,
    handle_get_function_summary,
    handle_get_call_chain,
    handle_load_program,
    handle_step,
    handle_run_to_end,
    handle_get_state,
    handle_get_ir,
)
from mcp_server.session import clear_session


class TestAnalyzeProgram:
    SOURCE = "def f(x):\n    return x + 1\ndef g(y):\n    return f(y)\nresult = g(5)\n"

    def test_returns_functions(self):
        result = handle_analyze_program(self.SOURCE, "python")
        assert len(result[VarName("functions")]) >= 2
        labels = [f["label"] for f in result[VarName("functions")]]
        assert any("f" in l for l in labels)
        assert any("g" in l for l in labels)

    def test_returns_call_graph(self):
        result = handle_analyze_program(self.SOURCE, "python")
        assert len(result[VarName("call_graph")]) >= 1

    def test_returns_counts(self):
        result = handle_analyze_program(self.SOURCE, "python")
        assert result[VarName("ir_instruction_count")] > 0
        assert result[VarName("cfg_block_count")] > 0
        assert result[VarName("whole_program_edge_count")] >= 0

    def test_invalid_language_returns_error(self):
        result = handle_analyze_program("x = 1", "klingon")
        assert VarName("error") in result


class TestGetFunctionSummary:
    SOURCE = "def add(a, b):\n    return a + b\nadd(1, 2)\n"

    def test_returns_flows(self):
        result = handle_get_function_summary(self.SOURCE, "python", "add")
        assert len(result[VarName("flows")]) == 2
        sources = {f["source"] for f in result[VarName("flows")]}
        assert sources == {"a", "b"}

    def test_unknown_function_returns_error(self):
        result = handle_get_function_summary(self.SOURCE, "python", "nonexistent")
        assert VarName("error") in result


class TestGetCallChain:
    SOURCE = (
        "def add(a, b):\n    return a + b\n"
        "def double(x):\n    return add(x, x)\n"
        "result = double(5)\n"
    )

    def test_returns_tree(self):
        result = handle_get_call_chain(self.SOURCE, "python")
        assert VarName("root") in result or VarName("chains") in result


class TestLoadProgram:
    def setup_method(self):
        clear_session()

    def test_loads_and_returns_overview(self):
        result = handle_load_program("def f(x):\n    return x\nf(5)\n", "python")
        assert result[VarName("total_steps")] > 0
        assert result[VarName("ir_instruction_count")] > 0

    def test_invalid_language(self):
        result = handle_load_program("x = 1", "klingon")
        assert VarName("error") in result


class TestStep:
    def setup_method(self):
        clear_session()

    def test_step_without_session_returns_error(self):
        result = handle_step(1)
        assert VarName("error") in result

    def test_step_after_load(self):
        handle_load_program("x = 1\ny = x + 1\n", "python")
        result = handle_step(1)
        assert result[VarName("steps_executed")] == 1
        assert len(result[VarName("steps")]) == 1

    def test_step_multiple(self):
        handle_load_program("x = 1\ny = x + 1\n", "python")
        result = handle_step(3)
        assert result[VarName("steps_executed")] <= 3

    def test_step_after_exhausted(self):
        handle_load_program("x = 1\n", "python")
        handle_run_to_end()
        result = handle_step(1)
        assert result[VarName("steps_executed")] == 0
        assert result[VarName("done")] is True


class TestRunToEnd:
    def setup_method(self):
        clear_session()

    def test_run_to_end(self):
        handle_load_program("x = 1\ny = x + 1\n", "python")
        result = handle_run_to_end()
        assert result[VarName("done")] is True
        assert VarName("variables") in result


class TestGetState:
    def setup_method(self):
        clear_session()

    def test_get_state_after_load(self):
        handle_load_program("x = 1\n", "python")
        result = handle_get_state()
        assert VarName("step_index") in result
        assert VarName("call_stack") in result


class TestGetIr:
    def setup_method(self):
        clear_session()

    def test_get_all_ir(self):
        handle_load_program("def f(x):\n    return x\nf(5)\n", "python")
        result = handle_get_ir()
        assert len(result[VarName("blocks")]) > 0

    def test_get_ir_for_function(self):
        handle_load_program("def f(x):\n    return x\nf(5)\n", "python")
        result = handle_get_ir("f")
        blocks = result[VarName("blocks")]
        assert len(blocks) >= 1
        assert any("f" in b["label"] for b in blocks)
