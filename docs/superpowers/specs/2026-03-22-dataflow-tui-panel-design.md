# Dataflow TUI Panel Design

**Date:** 2026-03-22
**Status:** Accepted
**Issue:** Visualize interprocedural dataflow analysis in the existing PipelineApp TUI

## Context

The PipelineApp TUI (`viz/app.py`) provides interactive step-through of the compilation pipeline with 6 synchronized panels in a 3x2 grid: Source, AST, IR, VM State (row-span 2), CFG, Step. The interprocedural dataflow analysis (`interpreter/interprocedural/`) produces call graphs, per-function summaries, and whole-program flow graphs. There is currently no way to visualize these results.

## Decision

Add a **Dataflow mode** to the existing PipelineApp, toggled via the `d` keybinding. In dataflow mode, Source and IR panels remain on the left; AST, VM State, CFG, and Step panels hide. The right side shows two new panels: Call Graph + Summaries (top) and Whole-Program Graph (bottom). The grid changes from 3x2 to 2x2.

## Design

### Mode Switching

- `d` keybinding toggles between Normal mode and Dataflow mode
- Normal mode: today's 3x2 grid (Source, AST, IR, VM State with `row-span: 2`, CFG, Step)
- Dataflow mode: 2x2 grid (Source, Call Graph + Summaries, IR, Whole-Program Graph)
- Panels hidden in dataflow mode: AST, VM State, CFG, Step
- Panels hidden in normal mode: Call Graph + Summaries, Whole-Program Graph
- Implementation: toggle a `.dataflow-mode` CSS class on Screen. The class hides normal-mode-only containers, shows dataflow containers, and switches the grid layout. The `row-span: 2` on `#vm-state-container` is part of the normal-mode CSS and naturally inactive when that container is hidden.
- When entering dataflow mode, set `SourcePanel.current_instruction = None` to clear step-based highlighting, so `highlight_lines()` for function-span highlighting works without interference. When returning to normal mode, clear the manual highlight state (`_highlight_start = -1`) and restore `current_instruction` from the current step.

### Data Pipeline

`PipelineResult` in `viz/pipeline.py` gains an `interprocedural` field of type `InterproceduralResult | None` (default `None`). `run_pipeline()` calls `analyze_interprocedural(cfg, registry)` after building the CFG and registry, wrapping the call in a try/except that logs errors and sets `interprocedural=None` on failure. The frozen `PipelineResult(...)` constructor call passes the result directly.

When `interprocedural is None` (analysis failed or program has no functions), both dataflow panels render a placeholder message: `[dim]No dataflow analysis available[/dim]`.

### Call Graph + Summaries Panel

**File:** `viz/panels/dataflow_summary_panel.py`
**Widget:** Textual `Tree` (same pattern as `ASTPanel`)

Structure:
```
▼ func_f (params: x)
    callers: func_g
    callees: (none)
  ▼ Flows (1)
      x → Return(func_f)
▼ func_g (params: y)
    callers: __main__
    callees: func_f
  ▼ Flows (1)
      y → Return(func_g)
```

Top-level nodes are functions from `call_graph.functions`. Each function node shows:
- Parameters from `FunctionEntry.params`
- Callers: derived from `call_graph.call_sites` (sites where this function appears in `callees`)
- Callees: derived from `call_graph.call_sites` (sites where this function is `caller`)
- Expandable child node "Flows" listing summary flows

**Merging contexts:** A function may have multiple `SummaryKey` entries (one per 1-CFA call context). All flows across all contexts for the same function are merged (set union) under a single "Flows" node. This keeps the tree flat and avoids exposing context internals in the UI.

Flow endpoint rendering:
- `VariableEndpoint` → variable name (e.g., `x`)
- `ReturnEndpoint` → `Return(func_label)`
- `FieldEndpoint` → `Field(base.field)` (e.g., `Field(self.name)`)

### Whole-Program Graph Panel

**File:** `viz/panels/dataflow_graph_panel.py`
**Widget:** Textual `Static` (same pattern as `CFGPanel`)

Renders all edges from `InterproceduralResult.whole_program_graph` as `source → destination` lines grouped by source endpoint. Register-only destinations get context annotations:

```
WHOLE-PROGRAM GRAPH (4 edges)

y → Return(func_g)
y → %8 (call result: f)
x → Return(func_f)
%13 → result
```

**Register annotation logic:** When a destination `VariableEndpoint` has a name starting with `%` (register convention in our IR), check `definition.instruction.opcode` directly (the `Definition` dataclass already carries the `IRInstruction`). If the opcode is `CALL_FUNCTION` or `CALL_METHOD`, annotate with `(call result: <callee_name>)`. If `definition == NO_DEFINITION` (the sentinel with `block_label=""`, `instruction_index=-1`), fall back to scanning the CFG for a `result_reg` match. Register-prefixed **source** endpoints are not annotated — they represent intermediate computation results and the source context is less useful than the destination context.

### Source/IR Cross-Highlighting

When a function node is selected in the Call Graph tree:

1. **SourcePanel**: highlight the source lines for that function's full span. The function's span is determined by collecting all CFG blocks belonging to the function (entry block + all blocks with matching prefix, using the same logic as `extract_sub_cfg` in `summaries.py`), then taking `min(start_line)` / `max(end_line)` across all instructions' `source_location` fields in those blocks (skipping unknown locations where all fields are 0).

2. **IRPanel**: scroll to and highlight the function's entry block. The block label is `FunctionEntry.label`. IRPanel needs a new `highlight_block(label: str)` method that re-renders with that block visually marked (bold yellow, same style as current-step highlighting).

Communication: the dataflow summary panel posts a Textual `Message` (e.g., `FunctionSelected(label: str)`) when a tree node is selected. PipelineApp handles the message and updates Source/IR panels.

### New Files

| File | Type | Description |
|------|------|-------------|
| `viz/panels/dataflow_summary_panel.py` | Tree widget | Call graph + per-function summaries |
| `viz/panels/dataflow_graph_panel.py` | Static widget | Whole-program graph with annotated edges |

### Modified Files

| File | Change |
|------|--------|
| `viz/pipeline.py` | Add `interprocedural: InterproceduralResult \| None = None` to `PipelineResult`; import `analyze_interprocedural` from `interpreter.interprocedural.analyze`; call it in `run_pipeline()` with try/except error handling; pass result to `PipelineResult(...)` constructor |
| `viz/app.py` | Add `d` keybinding; add dataflow mode toggle with `.dataflow-mode` CSS class; compose new panels (hidden by default); CSS for 2x2 dataflow grid; handle `FunctionSelected` message; manage `SourcePanel.current_instruction` across mode transitions |
| `viz/panels/ir_panel.py` | Add `highlight_block(label: str)` method |

### CSS Layout

Normal mode (unchanged):
```css
Screen {
    grid-size: 3 2;
    grid-columns: 1fr 1fr 1fr;
    grid-rows: 2fr 1fr;
}
#vm-state-container { row-span: 2; }
```

Dataflow mode:
```css
Screen.dataflow-mode {
    grid-size: 2 2;
    grid-columns: 1fr 2fr;
    grid-rows: 1fr 1fr;
}
Screen.dataflow-mode #ast-container,
Screen.dataflow-mode #vm-state-container,
Screen.dataflow-mode #cfg-container { display: none; }
```

The wider right column (2fr) gives the dataflow panels more room for flow text.

## What This Does NOT Include

- No new CLI subcommand — dataflow mode is accessed via keybinding within PipelineApp
- No interactive graph navigation (clicking edges, following flows) — future enhancement
- No filtering or search within the dataflow panels
- No taint tracking or program slicing queries — just visualization of the raw analysis results
- No per-context summary breakdown — contexts are merged per function for simplicity
