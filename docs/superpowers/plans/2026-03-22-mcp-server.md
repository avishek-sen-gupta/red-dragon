# RedDragon MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MCP server that exposes RedDragon's compilation pipeline, VM execution, and interprocedural dataflow analysis as tools and resources for LLMs.

**Architecture:** FastMCP server with stdio transport. 8 tools (3 stateless analysis, 5 stateful execution via trace replay), 3 resources. Single-session model. Pure formatting functions convert internal types to JSON. Session manages a pre-recorded execution trace.

**Tech Stack:** `mcp` Python SDK (FastMCP), existing `interpreter.*` and `viz.panels.*` modules.

**Spec:** `docs/superpowers/specs/2026-03-22-mcp-server-design.md`

---

### File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `pyproject.toml` | Modify | Add `mcp` dependency |
| `mcp_server/__init__.py` | Create | Package marker |
| `mcp_server/formatting.py` | Create | Convert TypedValue, StateUpdate, FlowEndpoint, ChainNode, VMState to JSON-friendly dicts |
| `mcp_server/session.py` | Create | Session dataclass + load_session factory |
| `mcp_server/tools.py` | Create | 8 tool handler functions (pure, testable) |
| `mcp_server/resources.py` | Create | 3 resource handler functions |
| `mcp_server/server.py` | Create | FastMCP server, register tools + resources |
| `mcp_server/__main__.py` | Create | Entry point: `asyncio.run(mcp.run())` |
| `tests/unit/test_mcp_formatting.py` | Create | Unit tests for formatting functions |
| `tests/unit/test_mcp_tools.py` | Create | Unit tests for tool handlers |
| `tests/integration/test_mcp_server.py` | Create | Integration tests: full round-trip |

---

### Task 1: Add `mcp` dependency and create package skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `mcp_server/__init__.py`
- Create: `mcp_server/__main__.py`

- [ ] **Step 1: Add mcp dependency**

```bash
poetry add "mcp[cli]"
```

- [ ] **Step 2: Create package directory and __init__.py**

Create `mcp_server/__init__.py`:
```python
"""RedDragon MCP Server — exposes compilation pipeline, VM, and dataflow analysis to LLMs."""
```

- [ ] **Step 3: Create minimal __main__.py entry point**

Create `mcp_server/__main__.py`:
```python
"""Entry point for the RedDragon MCP server: poetry run python -m mcp_server."""

import asyncio

from mcp_server.server import mcp

asyncio.run(mcp.run())
```

This will fail until `server.py` exists — that's fine, we'll create it in Task 6.

- [ ] **Step 4: Verify mcp import works**

```bash
poetry run python -c "from mcp.server.fastmcp import FastMCP; print('MCP SDK OK')"
```
Expected: `MCP SDK OK`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml poetry.lock mcp_server/__init__.py mcp_server/__main__.py
git commit -m "feat(mcp): add mcp dependency and package skeleton"
```

---

### Task 2: Create formatting module

**Files:**
- Create: `mcp_server/formatting.py`
- Create: `tests/unit/test_mcp_formatting.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_mcp_formatting.py`:

```python
"""Tests for MCP server formatting — converting internal types to JSON-friendly dicts."""

from __future__ import annotations

from interpreter.dataflow import Definition
from interpreter.interprocedural.types import (
    FieldEndpoint,
    FunctionEntry,
    InstructionLocation,
    NO_DEFINITION,
    ReturnEndpoint,
    VariableEndpoint,
)
from interpreter.ir import IRInstruction, Opcode
from interpreter.typed_value import TypedValue
from interpreter.type_expr import ScalarType, TypeName

from mcp_server.formatting import (
    format_typed_value,
    format_flow_endpoint,
    format_state_update,
    format_chain_node,
    format_vm_state_frame,
)


class TestFormatTypedValue:
    def test_int_value(self):
        tv = TypedValue(value=42, type=ScalarType(name=TypeName.INT))
        result = format_typed_value(tv)
        assert result == 42

    def test_string_value(self):
        tv = TypedValue(value="hello", type=ScalarType(name=TypeName.STRING))
        result = format_typed_value(tv)
        assert result == "hello"

    def test_complex_value_returns_dict(self):
        tv = TypedValue(value={"key": "val"}, type=ScalarType(name=TypeName.ANY))
        result = format_typed_value(tv)
        assert isinstance(result, dict)


class TestFormatFlowEndpoint:
    def test_variable_endpoint(self):
        ep = VariableEndpoint(name="x", definition=NO_DEFINITION)
        result = format_flow_endpoint(ep)
        assert result == {"name": "x", "type": "variable"}

    def test_return_endpoint(self):
        func = FunctionEntry(label="func_f_0", params=("x",))
        loc = InstructionLocation(block_label="func_f_0", instruction_index=5)
        ep = ReturnEndpoint(function=func, location=loc)
        result = format_flow_endpoint(ep)
        assert result == {"function": "func_f_0", "type": "return"}

    def test_field_endpoint(self):
        base = VariableEndpoint(name="self", definition=NO_DEFINITION)
        loc = InstructionLocation(block_label="b", instruction_index=1)
        ep = FieldEndpoint(base=base, field="name", location=loc)
        result = format_flow_endpoint(ep)
        assert result == {"base": "self", "field": "name", "type": "field"}


class TestFormatChainNode:
    def test_leaf_node(self):
        from viz.panels.dataflow_graph_panel import ChainNode
        node = ChainNode(label="x → return(f)")
        result = format_chain_node(node)
        assert result == {"label": "x → return(f)", "children": []}

    def test_node_with_children(self):
        from viz.panels.dataflow_graph_panel import ChainNode
        child = ChainNode(label="a → return(add)")
        node = ChainNode(label="x → add(a=x)", children=[child])
        result = format_chain_node(node)
        assert result["label"] == "x → add(a=x)"
        assert len(result["children"]) == 1
        assert result["children"][0]["label"] == "a → return(add)"


class TestFormatStateUpdate:
    def test_empty_update(self):
        from interpreter.vm_types import StateUpdate
        update = StateUpdate()
        result = format_state_update(update)
        assert result == {}

    def test_register_write(self):
        from interpreter.vm_types import StateUpdate
        update = StateUpdate(register_writes={"%0": 42})
        result = format_state_update(update)
        assert result["registers"] == {"%0": 42}

    def test_var_write(self):
        from interpreter.vm_types import StateUpdate
        update = StateUpdate(var_writes={"x": 10})
        result = format_state_update(update)
        assert result["variables"] == {"x": 10}

    def test_next_label(self):
        from interpreter.vm_types import StateUpdate
        update = StateUpdate(next_label="func_f_0")
        result = format_state_update(update)
        assert result["next_block"] == "func_f_0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_mcp_formatting.py -x -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement formatting.py**

Create `mcp_server/formatting.py`:

```python
"""Convert internal RedDragon types to JSON-serializable dicts for MCP tool responses."""

from __future__ import annotations

from typing import Any

from interpreter.interprocedural.types import (
    FieldEndpoint,
    FlowEndpoint,
    ReturnEndpoint,
    VariableEndpoint,
)
from interpreter.typed_value import TypedValue
from interpreter.vm_types import StateUpdate


def format_typed_value(tv: Any) -> Any:
    """Convert a TypedValue to a JSON-friendly representation.

    Simple scalars (int, float, str, bool) return the raw value.
    Everything else returns {"value": str(v), "type": str(t)}.
    """
    if not isinstance(tv, TypedValue):
        return str(tv)
    if isinstance(tv.value, (int, float, str, bool)):
        return tv.value
    return {"value": str(tv.value), "type": str(tv.type)}


def format_flow_endpoint(ep: FlowEndpoint) -> dict[str, str]:
    """Convert a FlowEndpoint to a JSON dict."""
    if isinstance(ep, VariableEndpoint):
        return {"name": ep.name, "type": "variable"}
    if isinstance(ep, ReturnEndpoint):
        return {"function": ep.function.label, "type": "return"}
    if isinstance(ep, FieldEndpoint):
        return {"base": ep.base.name, "field": ep.field, "type": "field"}
    return {"value": str(ep), "type": "unknown"}


def format_chain_node(node) -> dict:
    """Convert a ChainNode tree to nested JSON."""
    return {
        "label": node.label,
        "children": [format_chain_node(c) for c in node.children],
    }


def format_state_update(update: StateUpdate) -> dict[str, Any]:
    """Convert a StateUpdate to a dict with only non-empty fields."""
    result: dict[str, Any] = {}
    if update.register_writes:
        result["registers"] = {
            k: format_typed_value(v) for k, v in update.register_writes.items()
        }
    if update.var_writes:
        result["variables"] = {
            k: format_typed_value(v) for k, v in update.var_writes.items()
        }
    if update.heap_writes:
        result["heap_writes"] = [
            {"address": hw.address, "field": hw.field, "value": format_typed_value(hw.value)}
            for hw in update.heap_writes
        ]
    if update.new_objects:
        result["new_objects"] = [
            {"address": no.address, "class_name": no.class_name}
            for no in update.new_objects
        ]
    if update.next_label:
        result["next_block"] = update.next_label
    if update.call_push:
        result["call_push"] = update.call_push.function_name
    if update.call_pop:
        result["call_pop"] = True
    if update.reasoning:
        result["reasoning"] = update.reasoning
    return result


def format_vm_state_frame(frame) -> dict[str, Any]:
    """Convert a StackFrame to a JSON dict."""
    return {
        "function": frame.function_name,
        "variables": {
            k: format_typed_value(v) for k, v in frame.local_vars.items()
        },
        "registers": {
            k: format_typed_value(v) for k, v in frame.registers.items()
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_mcp_formatting.py -x -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/formatting.py tests/unit/test_mcp_formatting.py
git commit -m "feat(mcp): add formatting module for JSON serialization"
```

---

### Task 3: Create session module

**Files:**
- Create: `mcp_server/session.py`

- [ ] **Step 1: Implement session.py**

Create `mcp_server/session.py`:

```python
"""Session management for the RedDragon MCP server.

Single-session model: one program loaded at a time. load_session()
eagerly executes the program and records the full trace. Subsequent
step/get_state calls replay the pre-recorded trace.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from interpreter.cfg import build_cfg
from interpreter.cfg_types import CFG
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.interprocedural.analyze import analyze_interprocedural
from interpreter.interprocedural.types import InterproceduralResult
from interpreter.ir import IRInstruction
from interpreter.registry import FunctionRegistry, build_registry
from interpreter.run import ExecutionStrategies, build_execution_strategies, execute_cfg_traced
from interpreter.run_types import VMConfig
from interpreter.trace_types import ExecutionTrace
from interpreter.vm_types import VMState

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """A loaded program with its pre-recorded execution trace."""

    source: str
    language: Language
    ir: list[IRInstruction]
    cfg: CFG
    registry: FunctionRegistry
    interprocedural: InterproceduralResult
    vm: VMState
    trace: ExecutionTrace
    step_index: int


def load_session(source: str, language: str, max_steps: int = 300) -> Session:
    """Load, compile, execute, and analyze a program. Returns a ready-to-replay Session."""
    lang = Language(language)
    frontend = get_frontend(lang)
    ir = frontend.lower(source.encode("utf-8"))
    cfg = build_cfg(ir)
    registry = build_registry(
        ir, cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    strategies = build_execution_strategies(frontend, ir, registry, lang)
    config = VMConfig(max_steps=max_steps, source_language=lang)
    vm, trace = execute_cfg_traced(cfg, "", registry, config, strategies)
    interprocedural = analyze_interprocedural(cfg, registry)

    return Session(
        source=source,
        language=lang,
        ir=ir,
        cfg=cfg,
        registry=registry,
        interprocedural=interprocedural,
        vm=vm,
        trace=trace,
        step_index=0,
    )


# Module-level session state — single session per server process.
_current_session: Session | None = None


def get_session() -> Session:
    """Get the current session. Raises if no program is loaded."""
    if _current_session is None:
        raise RuntimeError("No program loaded. Call load_program first.")
    return _current_session


def set_session(session: Session) -> None:
    """Set the current session (replaces any prior session)."""
    global _current_session
    _current_session = session


def clear_session() -> None:
    """Clear the current session."""
    global _current_session
    _current_session = None
```

- [ ] **Step 2: Verify it imports correctly**

```bash
poetry run python -c "from mcp_server.session import Session, load_session; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add mcp_server/session.py
git commit -m "feat(mcp): add session module with load_session and trace replay state"
```

---

### Task 4: Create tools module

**Files:**
- Create: `mcp_server/tools.py`
- Create: `tests/unit/test_mcp_tools.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_mcp_tools.py`:

```python
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
        assert len(result["functions"]) >= 2
        labels = [f["label"] for f in result["functions"]]
        assert any("f" in l for l in labels)
        assert any("g" in l for l in labels)

    def test_returns_call_graph(self):
        result = handle_analyze_program(self.SOURCE, "python")
        assert len(result["call_graph"]) >= 1

    def test_returns_counts(self):
        result = handle_analyze_program(self.SOURCE, "python")
        assert result["ir_instruction_count"] > 0
        assert result["cfg_block_count"] > 0
        assert result["whole_program_edge_count"] >= 0

    def test_invalid_language_returns_error(self):
        result = handle_analyze_program("x = 1", "klingon")
        assert "error" in result


class TestGetFunctionSummary:
    SOURCE = "def add(a, b):\n    return a + b\nadd(1, 2)\n"

    def test_returns_flows(self):
        result = handle_get_function_summary(self.SOURCE, "python", "add")
        assert len(result["flows"]) == 2
        sources = {f["source"] for f in result["flows"]}
        assert sources == {"a", "b"}

    def test_unknown_function_returns_error(self):
        result = handle_get_function_summary(self.SOURCE, "python", "nonexistent")
        assert "error" in result


class TestGetCallChain:
    SOURCE = (
        "def add(a, b):\n    return a + b\n"
        "def double(x):\n    return add(x, x)\n"
        "result = double(5)\n"
    )

    def test_returns_tree(self):
        result = handle_get_call_chain(self.SOURCE, "python")
        assert "root" in result or "chains" in result


class TestLoadProgram:
    def setup_method(self):
        clear_session()

    def test_loads_and_returns_overview(self):
        result = handle_load_program("def f(x):\n    return x\nf(5)\n", "python")
        assert result["total_steps"] > 0
        assert result["ir_instruction_count"] > 0

    def test_invalid_language(self):
        result = handle_load_program("x = 1", "klingon")
        assert "error" in result


class TestStep:
    def setup_method(self):
        clear_session()

    def test_step_without_session_returns_error(self):
        result = handle_step(1)
        assert "error" in result

    def test_step_after_load(self):
        handle_load_program("x = 1\ny = x + 1\n", "python")
        result = handle_step(1)
        assert result["steps_executed"] == 1
        assert len(result["steps"]) == 1

    def test_step_multiple(self):
        handle_load_program("x = 1\ny = x + 1\n", "python")
        result = handle_step(3)
        assert result["steps_executed"] <= 3

    def test_step_after_exhausted(self):
        handle_load_program("x = 1\n", "python")
        handle_run_to_end()
        result = handle_step(1)
        assert result["steps_executed"] == 0
        assert result["done"] is True


class TestRunToEnd:
    def setup_method(self):
        clear_session()

    def test_run_to_end(self):
        handle_load_program("x = 1\ny = x + 1\n", "python")
        result = handle_run_to_end()
        assert result["done"] is True
        assert "variables" in result


class TestGetState:
    def setup_method(self):
        clear_session()

    def test_get_state_after_load(self):
        handle_load_program("x = 1\n", "python")
        result = handle_get_state()
        assert "step_index" in result
        assert "call_stack" in result


class TestGetIr:
    def setup_method(self):
        clear_session()

    def test_get_all_ir(self):
        handle_load_program("def f(x):\n    return x\nf(5)\n", "python")
        result = handle_get_ir()
        assert len(result["blocks"]) > 0

    def test_get_ir_for_function(self):
        handle_load_program("def f(x):\n    return x\nf(5)\n", "python")
        result = handle_get_ir("f")
        blocks = result["blocks"]
        assert len(blocks) >= 1
        assert any("f" in b["label"] for b in blocks)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_mcp_tools.py -x -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement tools.py**

Create `mcp_server/tools.py`:

```python
"""Tool handler implementations for the RedDragon MCP server.

Each handle_* function is a pure function that returns a JSON-serializable dict.
The server module registers these as MCP tools.
"""

from __future__ import annotations

import logging
from typing import Any

from interpreter.cfg import build_cfg
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.interprocedural.analyze import analyze_interprocedural
from interpreter.interprocedural.summaries import extract_sub_cfg
from interpreter.interprocedural.types import (
    FunctionEntry,
    ReturnEndpoint,
    FieldEndpoint,
    VariableEndpoint,
)
from interpreter.registry import build_registry
from mcp_server.formatting import (
    format_chain_node,
    format_flow_endpoint,
    format_state_update,
    format_typed_value,
    format_vm_state_frame,
)
from mcp_server.session import Session, get_session, load_session, set_session
from viz.panels.dataflow_graph_panel import (
    ChainNode,
    build_call_chain,
    find_top_level_call_sites,
)
from viz.panels.dataflow_summary_panel import (
    build_function_callers,
    build_function_callees,
    merge_flows_for_function,
    render_endpoint,
)

logger = logging.getLogger(__name__)


def _run_analysis(source: str, language: str):
    """Run pipeline + interprocedural analysis. Returns (cfg, registry, interprocedural)."""
    lang = Language(language)
    frontend = get_frontend(lang)
    ir = frontend.lower(source.encode("utf-8"))
    cfg = build_cfg(ir)
    registry = build_registry(
        ir, cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    interprocedural = analyze_interprocedural(cfg, registry)
    return cfg, registry, interprocedural, ir


def _find_function_entry(
    name: str, interprocedural,
) -> FunctionEntry:
    """Find a FunctionEntry by name or label. Raises ValueError if not found."""
    for f in interprocedural.call_graph.functions:
        if f.label == name:
            return f
    # Try name-based lookup: "add" → "func_add_0"
    for f in interprocedural.call_graph.functions:
        if f.label.startswith("func_") and "_" in f.label[5:]:
            func_name = f.label.split("_")[1]
            if func_name == name:
                return f
    raise ValueError(f"Function not found: {name}")


# ---------------------------------------------------------------------------
# Analysis tools (stateless)
# ---------------------------------------------------------------------------


def handle_analyze_program(source: str, language: str) -> dict[str, Any]:
    """Run full pipeline + analysis, return program overview."""
    try:
        cfg, registry, interprocedural, ir = _run_analysis(source, language)
    except Exception as e:
        return {"error": str(e)}

    call_graph = interprocedural.call_graph
    return {
        "functions": [
            {"label": f.label, "params": list(f.params)}
            for f in sorted(call_graph.functions, key=lambda f: f.label)
        ],
        "call_graph": [
            {"caller": s.caller.label, "callees": sorted(c.label for c in s.callees)}
            for s in call_graph.call_sites
        ],
        "summary_counts": {
            f.label: len(merge_flows_for_function(f, interprocedural.summaries))
            for f in call_graph.functions
        },
        "whole_program_edge_count": sum(
            len(dsts) for dsts in interprocedural.whole_program_graph.values()
        ),
        "ir_instruction_count": len(ir),
        "cfg_block_count": len(cfg.blocks),
    }


def handle_get_function_summary(
    source: str, language: str, function_name: str,
) -> dict[str, Any]:
    """Return param→return/field flows for a specific function."""
    try:
        cfg, registry, interprocedural, ir = _run_analysis(source, language)
        func_entry = _find_function_entry(function_name, interprocedural)
    except Exception as e:
        return {"error": str(e)}

    call_graph = interprocedural.call_graph
    flows = merge_flows_for_function(func_entry, interprocedural.summaries)

    def _flow_type(src, dst) -> str:
        if isinstance(dst, ReturnEndpoint):
            return "param_to_return"
        if isinstance(dst, FieldEndpoint):
            return "param_to_field"
        return "other"

    return {
        "function": func_entry.label,
        "params": list(func_entry.params),
        "callers": sorted(build_function_callers(func_entry, call_graph)),
        "callees": sorted(build_function_callees(func_entry, call_graph)),
        "flows": [
            {
                "source": render_endpoint(src),
                "destination": render_endpoint(dst),
                "type": _flow_type(src, dst),
            }
            for src, dst in sorted(flows, key=lambda f: render_endpoint(f[0]))
        ],
    }


def handle_get_call_chain(
    source: str, language: str, function_name: str | None = None,
) -> dict[str, Any]:
    """Build call-chain tree from top-level calls or a specific function."""
    try:
        cfg, registry, interprocedural, ir = _run_analysis(source, language)
    except Exception as e:
        return {"error": str(e)}

    if function_name:
        try:
            func_entry = _find_function_entry(function_name, interprocedural)
        except ValueError as e:
            return {"error": str(e)}
        nodes = build_call_chain(
            func_entry, interprocedural.call_graph,
            interprocedural.summaries, cfg, set(),
        )
        return {
            "root": f"{func_entry.label}({', '.join(func_entry.params)})",
            "children": [format_chain_node(n) for n in nodes],
        }

    top_calls = find_top_level_call_sites(cfg, interprocedural.call_graph)
    chains = []
    func_by_label = {f.label: f for f in interprocedural.call_graph.functions}
    for call in top_calls:
        callee = func_by_label.get(call.callee_label)
        if not callee:
            callee = next(
                (f for f in interprocedural.call_graph.functions
                 if f.label.startswith("func_") and f.label.split("_")[1] == call.callee_label),
                None,
            )
        if callee:
            nodes = build_call_chain(
                callee, interprocedural.call_graph,
                interprocedural.summaries, cfg, set(),  # fresh visited per chain
            )
            chains.append({
                "root": f"{call.callee_label}({', '.join(call.arg_operands)}) → {call.result_var}",
                "children": [format_chain_node(n) for n in nodes],
            })

    return {"chains": chains}


# ---------------------------------------------------------------------------
# Execution tools (stateful)
# ---------------------------------------------------------------------------


def handle_load_program(
    source: str, language: str, max_steps: int = 300,
) -> dict[str, Any]:
    """Load, compile, execute, and analyze a program."""
    try:
        session = load_session(source, language, max_steps)
    except Exception as e:
        return {"error": str(e)}

    set_session(session)

    return {
        "functions": sorted(
            f.label for f in session.interprocedural.call_graph.functions
        ),
        "ir_instruction_count": len(session.ir),
        "cfg_block_count": len(session.cfg.blocks),
        "entry_block": session.cfg.entry,
        "total_steps": len(session.trace.steps),
        "max_steps": max_steps,
    }


def handle_step(count: int = 1) -> dict[str, Any]:
    """Advance through the pre-recorded execution trace."""
    try:
        session = get_session()
    except RuntimeError as e:
        return {"error": str(e)}

    trace = session.trace
    remaining = len(trace.steps) - session.step_index
    actual_count = min(count, remaining)

    steps_data = []
    for i in range(actual_count):
        step = trace.steps[session.step_index + i]
        steps_data.append({
            "index": step.step_index,
            "block": step.block_label,
            "instruction": str(step.instruction),
            "deltas": format_state_update(step.update),
        })

    session.step_index += actual_count
    done = session.step_index >= len(trace.steps)

    current_step = trace.steps[session.step_index - 1] if session.step_index > 0 else None
    return {
        "steps_executed": actual_count,
        "steps": steps_data,
        "current_block": current_step.block_label if current_step else "",
        "current_index": session.step_index,
        "done": done,
    }


def handle_run_to_end() -> dict[str, Any]:
    """Advance to the end of the pre-recorded trace."""
    try:
        session = get_session()
    except RuntimeError as e:
        return {"error": str(e)}

    remaining = len(session.trace.steps) - session.step_index
    session.step_index = len(session.trace.steps)

    # Return final VM state
    frame = session.vm.current_frame
    return {
        "steps_executed": remaining,
        "variables": {
            k: format_typed_value(v) for k, v in frame.local_vars.items()
        },
        "heap": {
            addr: {
                "type": str(obj.type_hint),
                "fields": {k: format_typed_value(v) for k, v in obj.fields.items()},
            }
            for addr, obj in session.vm.heap.items()
        },
        "done": True,
    }


def handle_get_state() -> dict[str, Any]:
    """Return current VM state snapshot."""
    try:
        session = get_session()
    except RuntimeError as e:
        return {"error": str(e)}

    # Get state from the trace at current step_index
    if session.step_index > 0:
        vm_state = session.trace.steps[session.step_index - 1].vm_state
    else:
        vm_state = session.trace.initial_state

    return {
        "step_index": session.step_index,
        "current_block": (
            session.trace.steps[session.step_index - 1].block_label
            if session.step_index > 0 else session.cfg.entry
        ),
        "current_instruction_index": (
            session.trace.steps[session.step_index - 1].instruction_index
            if session.step_index > 0 else 0
        ),
        "call_stack": [
            format_vm_state_frame(f) for f in vm_state.call_stack
        ],
        "heap": {
            addr: {
                "type": str(obj.type_hint),
                "fields": {k: format_typed_value(v) for k, v in obj.fields.items()},
            }
            for addr, obj in vm_state.heap.items()
        },
    }


def handle_get_ir(function_name: str | None = None) -> dict[str, Any]:
    """Return IR instructions, optionally filtered to one function."""
    try:
        session = get_session()
    except RuntimeError as e:
        return {"error": str(e)}

    cfg = session.cfg

    if function_name:
        try:
            func_entry = _find_function_entry(function_name, session.interprocedural)
        except ValueError as e:
            return {"error": str(e)}
        sub_cfg = extract_sub_cfg(cfg, func_entry)
        cfg = sub_cfg

    return {
        "blocks": [
            {
                "label": label,
                "successors": list(block.successors),
                "instructions": [str(inst) for inst in block.instructions],
            }
            for label, block in cfg.blocks.items()
        ],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_mcp_tools.py -x -v`
Expected: All tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/tools.py tests/unit/test_mcp_tools.py
git commit -m "feat(mcp): add 8 tool handler implementations with tests"
```

---

### Task 5: Create resources module

**Files:**
- Create: `mcp_server/resources.py`

- [ ] **Step 1: Implement resources.py**

Create `mcp_server/resources.py`:

```python
"""Resource handler implementations for the RedDragon MCP server."""

from __future__ import annotations

import json

import mcp_server.session as session_module


def handle_source_resource() -> str:
    """Return the loaded program's source code."""
    current = session_module._current_session
    if current is None:
        return "No program loaded. Call load_program first."
    return current.source


def handle_ir_resource() -> str:
    """Return the full IR listing."""
    current = session_module._current_session
    if current is None:
        return "No program loaded. Call load_program first."

    lines = []
    for label, block in current.cfg.blocks.items():
        lines.append(f"{label}:  → {', '.join(block.successors)}")
        for inst in block.instructions:
            lines.append(f"  {inst}")
        lines.append("")
    return "\n".join(lines)


def handle_cfg_resource() -> str:
    """Return the CFG structure as JSON."""
    current = session_module._current_session
    if current is None:
        return json.dumps({"error": "No program loaded. Call load_program first."})

    blocks = [
        {
            "label": label,
            "successors": list(block.successors),
            "instruction_count": len(block.instructions),
        }
        for label, block in current.cfg.blocks.items()
    ]
    return json.dumps({"blocks": blocks}, indent=2)
```

- [ ] **Step 2: Commit**

```bash
git add mcp_server/resources.py
git commit -m "feat(mcp): add resource handlers for source, IR, and CFG"
```

---

### Task 6: Create server module and wire everything together

**Files:**
- Create: `mcp_server/server.py`
- Create: `tests/integration/test_mcp_server.py`

- [ ] **Step 1: Implement server.py**

Create `mcp_server/server.py`:

```python
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
def get_function_summary(source: str, language: str, function_name: str) -> dict[str, Any]:
    """Get dataflow summary for a specific function: which params flow to return/fields.

    Returns param list, callers, callees, and flow edges.
    """
    return handle_get_function_summary(source, language, function_name)


@mcp.tool()
def get_call_chain(source: str, language: str, function_name: str | None = None) -> dict[str, Any]:
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
```

- [ ] **Step 2: Write integration test**

Create `tests/integration/test_mcp_server.py`:

```python
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
        assert load_result["total_steps"] > 0

        end_result = handle_run_to_end()
        assert end_result["done"] is True
        assert end_result["variables"]["result"] == 20

    def test_analyze_then_load_and_step(self):
        """Analysis tools work independently of execution session."""
        analysis = handle_analyze_program(MULTI_FUNC_SOURCE, "python")
        assert len(analysis["functions"]) >= 3

        handle_load_program(MULTI_FUNC_SOURCE, "python")
        step_result = handle_step(5)
        assert step_result["steps_executed"] == 5

        state = handle_get_state()
        assert state["step_index"] == 5

    def test_call_chain_matches_execution(self):
        """Call chain shows n → double → add, execution produces result == 20."""
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
```

- [ ] **Step 3: Run integration tests**

Run: `poetry run python -m pytest tests/integration/test_mcp_server.py -x -v`
Expected: All tests PASS.

- [ ] **Step 4: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All pass.

- [ ] **Step 5: Verify server launches**

```bash
timeout 3 poetry run python -m mcp_server 2>&1 || true
```
Expected: Server starts (may hang waiting for stdio input — that's correct). No import errors.

- [ ] **Step 6: Run black**

Run: `poetry run python -m black mcp_server/ tests/unit/test_mcp_formatting.py tests/unit/test_mcp_tools.py tests/integration/test_mcp_server.py`

- [ ] **Step 7: Commit**

```bash
git add mcp_server/server.py tests/integration/test_mcp_server.py
git commit -m "feat(mcp): create MCP server with tools, resources, and integration tests"
```

---

### Task 7: Final validation and push

**Files:**
- All

- [ ] **Step 1: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All pass.

- [ ] **Step 2: Run black on entire codebase**

Run: `poetry run python -m black .`

- [ ] **Step 3: Verify MCP server starts cleanly**

```bash
timeout 2 poetry run python -m mcp_server 2>/dev/null; echo "exit code: $?"
```

- [ ] **Step 4: Push**

```bash
git push origin main
```
