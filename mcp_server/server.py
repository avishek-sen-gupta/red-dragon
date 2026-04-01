# pyright: standard
"""RedDragon MCP server — registers tools and resources on a FastMCP instance."""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_server.resources import (
    handle_cfg_resource,
    handle_ir_resource,
    handle_source_resource,
)
from mcp_server.tools import (
    handle_analyze_program,
    handle_get_call_chain,
    handle_get_function_summary,
    handle_get_ir,
    handle_get_state,
    handle_load_program,
    handle_load_project,
    handle_run_to_end,
    handle_step,
)

logger = logging.getLogger(__name__)

mcp = FastMCP(name="red-dragon")


# ---------------------------------------------------------------------------
# Analysis tools (stateless)
# ---------------------------------------------------------------------------


@mcp.tool()
def analyze_program(source: str, language: str) -> dict[str, Any]:
    """Analyze a program: lower to IR, build CFG, run interprocedural dataflow analysis.

    Returns functions, call graph, flow summary counts, and metrics.
    Supported languages: python, javascript, typescript, java, csharp, cpp, c, go, rust, ruby, kotlin, scala, php, lua, pascal.
    """
    return handle_analyze_program(source, language)


@mcp.tool()
def get_function_summary(
    source: str, language: str, function_name: str
) -> dict[str, Any]:
    """Get dataflow summary for a specific function: which params flow to return/fields.

    Returns param list, callers, callees, and flow edges.
    """
    return handle_get_function_summary(source, language, function_name)


@mcp.tool()
def get_call_chain(
    source: str, language: str, function_name: str | None = None
) -> dict[str, Any]:
    """Trace data flow through call chains.

    If function_name is provided, shows how that function's params flow through its callees.
    If omitted, traces from top-level call sites through the entire program.
    Returns a nested tree structure.
    """
    return handle_get_call_chain(source, language, function_name)


# ---------------------------------------------------------------------------
# Execution tools (stateful — single session)
# ---------------------------------------------------------------------------


@mcp.tool()
def load_program(source: str, language: str, max_steps: int = 300) -> dict[str, Any]:
    """Load and execute a program, recording a step-by-step trace.

    Eagerly executes the entire program and records the trace. Use step() and
    get_state() to replay the execution. Replaces any previously loaded program.
    """
    return handle_load_program(source, language, max_steps)


@mcp.tool()
def step(count: int = 1) -> dict[str, Any]:
    """Advance through the execution trace by count steps.

    Returns the instructions executed, state deltas, and current position.
    Requires load_program to be called first.
    """
    return handle_step(count)


@mcp.tool()
def run_to_end() -> dict[str, Any]:
    """Advance to the end of execution. Returns final variable values and heap state.

    Requires load_program to be called first.
    """
    return handle_run_to_end()


@mcp.tool()
def get_state() -> dict[str, Any]:
    """Get the current VM state: call stack, variables, registers, heap.

    Returns a snapshot at the current step position without advancing.
    Requires load_program to be called first.
    """
    return handle_get_state()


@mcp.tool()
def get_ir(function_name: str | None = None) -> dict[str, Any]:
    """Get IR instructions for the loaded program.

    If function_name is provided, returns only that function's blocks.
    Requires load_program to be called first.
    """
    return handle_get_ir(function_name)


# ---------------------------------------------------------------------------
# Multi-file project tools
# ---------------------------------------------------------------------------


@mcp.tool()
def load_project(entry_file: str, language: str) -> dict[str, Any]:
    """Load a multi-file project: discover imports, compile all modules, link, and analyze.

    Starts from the entry file (e.g. main.py), recursively discovers local imports,
    compiles each file, links them into a merged program, and runs interprocedural analysis.

    Returns: module count, import graph, functions, classes, and unresolved imports.

    Supported languages: python, javascript, typescript, java, csharp, cpp, c, go, rust, ruby, kotlin, scala, php, lua, pascal.
    """
    return handle_load_project(entry_file, language)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("reddragon://source")
def source_resource() -> str:
    """The loaded program's source code."""
    return handle_source_resource()


@mcp.resource("reddragon://ir")
def ir_resource() -> str:
    """Full IR listing for the loaded program."""
    return handle_ir_resource()


@mcp.resource("reddragon://cfg")
def cfg_resource() -> str:
    """CFG block structure (labels, successors, instruction counts) as JSON."""
    return handle_cfg_resource()
