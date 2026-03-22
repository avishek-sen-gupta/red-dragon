# RedDragon MCP Server Design

**Date:** 2026-03-22
**Status:** Accepted
**Issue:** red-dragon-8ya1

## Context

RedDragon's compilation pipeline (15 language frontends → 32-opcode IR → VM execution) and interprocedural dataflow analysis (call graphs, per-function summaries, whole-program flow graphs) are currently only accessible programmatically via Python imports or through the TUI. Exposing these capabilities as an MCP (Model Context Protocol) server would allow LLMs to analyze, execute, and inspect programs across all supported languages.

## Decision

Build an MCP server using stdio transport that exposes 8 tools (3 stateless analysis, 5 stateful execution) and 3 resources. Single-session model — one program loaded at a time.

## Design

### Transport

stdio only. The server is launched per-client and communicates via stdin/stdout. Entry point: `poetry run python -m mcp_server`. Clients (Claude Code, Cursor, Cline) configure it in their MCP settings.

### Tools

#### Analysis Tools (stateless — each takes source + language, no session required)

**`analyze_program(source: str, language: str) → dict`**

Run the full pipeline (lower → CFG → registry → interprocedural analysis). Returns:
```json
{
  "functions": [{"label": "func_add_0", "params": ["a", "b"]}, ...],
  "call_graph": [{"caller": "func_g_2", "callees": ["func_f_0"]}, ...],
  "summary_counts": {"func_add_0": 2, "func_g_2": 1},
  "whole_program_edge_count": 9,
  "ir_instruction_count": 42,
  "cfg_block_count": 8
}
```

Uses `get_frontend`, `build_cfg`, `build_registry`, `analyze_interprocedural` — the same pipeline as `run_pipeline()` in `viz/pipeline.py` but without execution.

**`get_call_chain(source: str, language: str, function_name: str | None) → dict`**

Build the call-chain tree (same logic as `DataflowGraphPanel`). If `function_name` is provided, look up the `FunctionEntry` by label (or by name via the function registry) and build the callee tree rooted at that function — showing what it calls and how params flow. If `function_name` is omitted, build from top-level call sites. Returns nested JSON:
```json
{
  "root": "quadruple(%19) → result",
  "children": [
    {
      "label": "n → func_double_2(x=n)",
      "children": [
        {"label": "x → func_add_0(a=x, b=x)", "children": [
          {"label": "a → return(func_add_0)", "children": []},
          {"label": "b → return(func_add_0)", "children": []}
        ]},
        {"label": "x → return(func_double_2)", "children": []}
      ]
    },
    {"label": "n → return(func_quadruple_4)", "children": []}
  ]
}
```

Uses `find_top_level_call_sites`, `build_call_chain` from `dataflow_graph_panel.py`.

**`get_function_summary(source: str, language: str, function_name: str) → dict`**

Return param→return/field flows for a specific function. Returns:
```json
{
  "function": "func_add_0",
  "params": ["a", "b"],
  "callers": ["func_double_2"],
  "callees": [],
  "flows": [
    {"source": "a", "destination": "return(func_add_0)", "type": "param_to_return"},
    {"source": "b", "destination": "return(func_add_0)", "type": "param_to_return"}
  ]
}
```

Uses `merge_flows_for_function`, `build_function_callers`, `build_function_callees` from `dataflow_summary_panel.py`.

#### Execution Tools (stateful — operate on single session)

**`load_program(source: str, language: str, max_steps: int = 300) → dict`**

Load source and run the full pipeline including execution. This eagerly executes the entire program via `execute_cfg_traced` and records the full trace. Creates (or replaces) the current session. Subsequent `step`/`run_to_end`/`get_state` calls replay the pre-recorded trace by advancing a step index — there is no pause/resume mechanism. Returns:
```json
{
  "functions": ["func_add_0", "func_double_2"],
  "ir_instruction_count": 42,
  "cfg_block_count": 8,
  "entry_block": "entry",
  "total_steps": 45,
  "max_steps": 300
}
```

Uses `get_frontend`, `build_cfg`, `build_registry`, `build_execution_strategies`, `execute_cfg_traced`, and `analyze_interprocedural`.

**`step(count: int = 1) → dict`**

Advance `count` steps through the pre-recorded execution trace. Returns:
```json
{
  "steps_executed": 3,
  "steps": [
    {
      "index": 0,
      "block": "entry",
      "instruction": "branch end_add_1  # 1:0-2:16",
      "deltas": {"next_block": "end_add_1"}
    },
    {
      "index": 1,
      "block": "end_add_1",
      "instruction": "%12 = const func_add_0",
      "deltas": {"registers": {"%12": "func_add_0"}}
    }
  ],
  "current_block": "end_add_1",
  "current_index": 2,
  "done": false
}
```

Replays from the trace recorded during `load_program`. Each step's deltas are extracted from the `TraceStep.update` field. The `update` object (`StateUpdate`) contains: register writes, variable writes, heap mutations, and control flow transitions — `formatting.py` serializes all non-empty fields.

**`run_to_end() → dict`**

Advance to the end of the pre-recorded trace. Returns the final VM state:
```json
{
  "steps_executed": 45,
  "variables": {"add": "func_add_0", "result": 20},
  "heap": {"arr_0": {"type": "Array", "fields": {"0": 1, "1": 2}}},
  "done": true
}
```

**`get_state() → dict`**

Return current VM state snapshot without advancing execution:
```json
{
  "step_index": 12,
  "current_block": "func_add_0",
  "current_instruction_index": 3,
  "call_stack": [
    {"function": "<main>", "variables": {"add": "func_add_0", "double": "func_double_2"}},
    {"function": "func_double_2", "variables": {"x": 5}}
  ],
  "registers": {"%8": 5, "%9": 5},
  "heap": {}
}
```

**`get_ir(function_name: str | None = None) → dict`**

Return IR instructions. If `function_name` is provided, return only that function's blocks (using `extract_sub_cfg`). Otherwise return all blocks.
```json
{
  "blocks": [
    {
      "label": "func_add_0",
      "successors": [],
      "instructions": [
        "%0 = symbolic param:a  # 1:8-1:9",
        "decl_var a %0",
        ...
      ]
    }
  ]
}
```

### Resources (3)

Available only after `load_program` has been called. If no session exists, return empty content with a note.

**`reddragon://source`** — the loaded program's source code as plain text.

**`reddragon://ir`** — the full IR listing, formatted as the TUI's IR panel renders it (block headers + instructions).

**`reddragon://cfg`** — the CFG structure as JSON:
```json
{
  "blocks": [
    {"label": "entry", "successors": ["end_add_1"], "instruction_count": 1},
    {"label": "func_add_0", "successors": [], "instruction_count": 8}
  ]
}
```

### Module Structure

```
mcp_server/
    __init__.py      — package marker
    __main__.py      — entry point: create server, run stdio transport
    server.py        — MCP server definition, tool/resource registration
    session.py       — Session dataclass (PipelineResult + VM state + execution position)
    tools.py         — tool handler implementations (analysis + execution)
    resources.py     — resource handler implementations
    formatting.py    — convert internal types (TypedValue, FlowEndpoint, etc.) to JSON-friendly dicts
```

### Session Management

`session.py` holds a module-level `Session` instance:

```python
@dataclass
class Session:
    source: str
    language: Language
    cfg: CFG
    registry: FunctionRegistry
    strategies: ExecutionStrategies
    interprocedural: InterproceduralResult
    vm_config: VMConfig
    vm: VMState
    trace: ExecutionTrace
    step_index: int  # current position in trace.steps
```

`load_program` creates a new `Session` (replacing any prior one). Analysis tools (`analyze_program`, `get_call_chain`, `get_function_summary`) are fully stateless — they build their own pipeline from the provided source. Execution tools require an active session.

### Formatting

`formatting.py` converts internal types to JSON-serializable dicts:
- `TypedValue` → `{"value": ..., "type": "Int"}` or just the raw value for simple types
- `FlowEndpoint` → `{"name": "x", "type": "variable"}` / `{"function": "func_f_0", "type": "return"}` / etc.
- `ChainNode` → `{"label": "...", "children": [...]}`
- `VMState` → nested dict of frames, variables, heap

### Error Handling

Tool handlers return structured error responses for:
- Invalid language name → `{"error": "Unknown language: xyz"}`
- Parse/lower failure → `{"error": "Parse error: ..."}`
- No active session (for execution tools) → `{"error": "No program loaded. Call load_program first."}`
- Execution already complete → `{"error": "Execution complete. Call load_program to restart."}`

### Dependencies

- `mcp` Python SDK (add to pyproject.toml: `mcp >= 1.0`)
- All existing `interpreter.*` modules
- `viz.panels.dataflow_graph_panel` and `viz.panels.dataflow_summary_panel` for call chain / summary helpers

### Configuration

Claude Code users add to `.claude/settings.json`:
```json
{
  "mcpServers": {
    "red-dragon": {
      "command": "poetry",
      "args": ["run", "python", "-m", "mcp_server"],
      "cwd": "/path/to/red-dragon"
    }
  }
}
```

### Files

| File | Action | Description |
|------|--------|-------------|
| `mcp_server/__init__.py` | Create | Package marker |
| `mcp_server/__main__.py` | Create | Entry point, stdio transport |
| `mcp_server/server.py` | Create | Server definition, tool/resource registration |
| `mcp_server/session.py` | Create | Session dataclass and management |
| `mcp_server/tools.py` | Create | 8 tool handler implementations |
| `mcp_server/resources.py` | Create | 3 resource handlers |
| `mcp_server/formatting.py` | Create | Type conversion to JSON-friendly dicts |
| `pyproject.toml` | Modify | Add `mcp` dependency |

### Accepted Languages

The `language` parameter accepts any value from the `Language` enum: `python`, `javascript`, `typescript`, `java`, `csharp`, `cpp`, `c`, `go`, `rust`, `ruby`, `kotlin`, `scala`, `php`, `lua`, `pascal`. Case-insensitive.

### Testing

**Unit tests** (`tests/unit/test_mcp_tools.py`): test each tool handler function directly with small Python programs. Verify JSON output shapes, error cases (no session, bad language), and formatting correctness. Use dependency injection — pass pipeline results to handlers, don't run the full MCP server.

**Integration tests** (`tests/integration/test_mcp_server.py`): test the full MCP server round-trip using the `mcp` SDK's test client. Load a program, step through it, verify state, run analysis tools. At least one multi-function program (like the `quadruple → double → add` chain) to verify call chains work end-to-end.

### What This Does NOT Include

- No HTTP/SSE transport — stdio only
- No prompt templates
- No authentication
- No concurrent sessions — single session per server process
- No breakpoints or conditional stepping
- No file-based program loading (source passed as string in tool calls)
