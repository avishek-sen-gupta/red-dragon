# Dataflow TUI Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a togglable Dataflow mode to PipelineApp that visualizes interprocedural call graph, per-function summaries, and whole-program flow graph alongside source and IR.

**Architecture:** Two new Textual panels (Tree widget for call graph + summaries, Static widget for whole-program graph) integrated into PipelineApp via a `d` keybinding mode toggle. `run_pipeline()` is extended to run `analyze_interprocedural()` and include the result in `PipelineResult`. Cross-highlighting connects function selection to Source/IR panels.

**Tech Stack:** Textual 8.1.0, Rich (text rendering), existing `interpreter.interprocedural` analysis module.

**Spec:** `docs/superpowers/specs/2026-03-22-dataflow-tui-panel-design.md`

---

### File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `viz/pipeline.py` | Modify | Add `interprocedural` field to `PipelineResult`, run analysis in `run_pipeline()` |
| `viz/panels/dataflow_summary_panel.py` | Create | Tree widget: call graph + per-function summaries, `FunctionSelected` message |
| `viz/panels/dataflow_graph_panel.py` | Create | Static widget: whole-program graph with annotated register edges |
| `viz/panels/ir_panel.py` | Modify | Add `highlight_block(label)` method |
| `viz/app.py` | Modify | `d` keybinding, mode toggle, compose new panels, CSS, message handling |
| `tests/unit/test_dataflow_summary_panel.py` | Create | Unit tests for summary panel rendering logic |
| `tests/unit/test_dataflow_graph_panel.py` | Create | Unit tests for graph panel rendering logic |
| `tests/integration/test_dataflow_tui.py` | Create | Integration test: pipeline produces `InterproceduralResult` |

---

### Task 1: Extend PipelineResult with interprocedural analysis

**Files:**
- Modify: `viz/pipeline.py`
- Test: `tests/integration/test_dataflow_tui.py`

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/test_dataflow_tui.py
"""Integration tests for dataflow TUI pipeline extension."""

from __future__ import annotations

from interpreter.interprocedural.types import InterproceduralResult
from viz.pipeline import run_pipeline


class TestPipelineInterproceduralResult:
    SOURCE = """\
def f(x):
    return x + 1

def g(y):
    return f(y) + 2

result = g(10)
"""

    def test_pipeline_result_has_interprocedural_field(self):
        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        assert result.interprocedural is not None
        assert isinstance(result.interprocedural, InterproceduralResult)

    def test_interprocedural_has_call_graph(self):
        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        assert len(result.interprocedural.call_graph.functions) > 0

    def test_interprocedural_has_summaries(self):
        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        assert len(result.interprocedural.summaries) > 0

    def test_interprocedural_has_whole_program_graph(self):
        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        assert len(result.interprocedural.whole_program_graph) > 0

    def test_pipeline_no_functions_still_works(self):
        result = run_pipeline("x = 1\ny = x + 1\n", language="python", max_steps=50)
        assert result.interprocedural is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/integration/test_dataflow_tui.py -x -v`
Expected: FAIL — `PipelineResult` has no `interprocedural` attribute.

- [ ] **Step 3: Implement — extend PipelineResult and run_pipeline**

In `viz/pipeline.py`:

1. Add imports at top:
```python
from interpreter.frontend import get_frontend
from interpreter.interprocedural.analyze import analyze_interprocedural
from interpreter.interprocedural.types import InterproceduralResult
```

2. Add field to `PipelineResult`:
```python
@dataclass(frozen=True)
class PipelineResult:
    """All stage outputs from a single pipeline run."""
    source: str
    language: str
    ast: ASTNode | None = None
    ir: list[IRInstruction] = field(default_factory=list)
    cfg: CFG = field(default_factory=CFG)
    trace: ExecutionTrace = field(default_factory=ExecutionTrace)
    interprocedural: InterproceduralResult | None = None
```

3. In `run_pipeline()`, replace `lower_source()` with `get_frontend()` + `frontend.lower(source_bytes)` so we get access to `frontend.func_symbol_table` and `frontend.class_symbol_table` (needed for proper call graph resolution). Note: `frontend.lower()` takes `bytes` (same `source_bytes` already computed for AST parsing) and returns `list[IRInstruction]`. Symbol tables are populated after `.lower()` is called. Then add interprocedural analysis:

```python
def run_pipeline(source, language="python", max_steps=300):
    # ... AST parsing unchanged ...

    frontend = get_frontend(Language(language))
    ir = frontend.lower(source_bytes)
    cfg = build_cfg(ir)
    registry = build_registry(
        ir, cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    config = VMConfig(max_steps=max_steps)
    _vm, trace = execute_cfg_traced(cfg, "", registry, config)

    try:
        interprocedural = analyze_interprocedural(cfg, registry)
    except Exception:
        logger.warning("Interprocedural analysis failed", exc_info=True)
        interprocedural = None

    return PipelineResult(
        source=source, language=language, ast=ast, ir=ir,
        cfg=cfg, trace=trace, interprocedural=interprocedural,
    )
```

Remove unused `lower_source` import. Add `Language` import from `interpreter.constants`.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/integration/test_dataflow_tui.py -x -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass (no regressions from pipeline change).

- [ ] **Step 6: Commit**

```bash
git add viz/pipeline.py tests/integration/test_dataflow_tui.py
git commit -m "feat(viz): extend PipelineResult with interprocedural analysis"
```

---

### Task 2: Create dataflow summary panel (Call Graph + Summaries)

**Files:**
- Create: `viz/panels/dataflow_summary_panel.py`
- Test: `tests/unit/test_dataflow_summary_panel.py`

- [ ] **Step 1: Write unit tests for rendering helper functions**

```python
# tests/unit/test_dataflow_summary_panel.py
"""Tests for dataflow summary panel rendering helpers."""

from __future__ import annotations

from interpreter.interprocedural.types import (
    CallGraph,
    CallSite,
    FieldEndpoint,
    FunctionEntry,
    FunctionSummary,
    InterproceduralResult,
    NO_DEFINITION,
    ReturnEndpoint,
    SummaryKey,
    VariableEndpoint,
    ROOT_CONTEXT,
    InstructionLocation,
)
from viz.panels.dataflow_summary_panel import (
    render_endpoint,
    build_function_callers,
    build_function_callees,
    merge_flows_for_function,
)


class TestRenderEndpoint:
    def test_variable_endpoint(self):
        ep = VariableEndpoint(name="x", definition=NO_DEFINITION)
        assert render_endpoint(ep) == "x"

    def test_return_endpoint(self):
        func = FunctionEntry(label="func_f_0", params=("x",))
        loc = InstructionLocation(block_label="func_f_0", instruction_index=5)
        ep = ReturnEndpoint(function=func, location=loc)
        assert render_endpoint(ep) == "Return(func_f_0)"

    def test_field_endpoint(self):
        base = VariableEndpoint(name="self", definition=NO_DEFINITION)
        loc = InstructionLocation(block_label="func_init_0", instruction_index=3)
        ep = FieldEndpoint(base=base, field="name", location=loc)
        assert render_endpoint(ep) == "Field(self.name)"


class TestBuildCallers:
    def test_function_with_caller(self):
        f = FunctionEntry(label="func_f_0", params=("x",))
        g = FunctionEntry(label="func_g_2", params=("y",))
        loc = InstructionLocation(block_label="func_g_2", instruction_index=3)
        site = CallSite(
            caller=g, location=loc,
            callees=frozenset({f}), arg_operands=("%7",),
        )
        call_graph = CallGraph(functions=frozenset({f, g}), call_sites=frozenset({site}))
        callers = build_function_callers(f, call_graph)
        assert callers == {"func_g_2"}

    def test_function_with_no_callers(self):
        f = FunctionEntry(label="func_f_0", params=("x",))
        call_graph = CallGraph(functions=frozenset({f}), call_sites=frozenset())
        callers = build_function_callers(f, call_graph)
        assert callers == set()


class TestBuildCallees:
    def test_function_with_callee(self):
        f = FunctionEntry(label="func_f_0", params=("x",))
        g = FunctionEntry(label="func_g_2", params=("y",))
        loc = InstructionLocation(block_label="func_g_2", instruction_index=3)
        site = CallSite(
            caller=g, location=loc,
            callees=frozenset({f}), arg_operands=("%7",),
        )
        call_graph = CallGraph(functions=frozenset({f, g}), call_sites=frozenset({site}))
        callees = build_function_callees(g, call_graph)
        assert callees == {"func_f_0"}


class TestMergeFlows:
    def test_merges_across_contexts(self):
        f = FunctionEntry(label="func_f_0", params=("x",))
        flow1 = (
            VariableEndpoint(name="x", definition=NO_DEFINITION),
            ReturnEndpoint(
                function=f,
                location=InstructionLocation(block_label="func_f_0", instruction_index=5),
            ),
        )
        summary1 = FunctionSummary(function=f, context=ROOT_CONTEXT, flows=frozenset({flow1}))
        key1 = SummaryKey(function=f, context=ROOT_CONTEXT)
        summaries = {key1: summary1}
        merged = merge_flows_for_function(f, summaries)
        assert len(merged) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_dataflow_summary_panel.py -x -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the panel**

Create `viz/panels/dataflow_summary_panel.py`:

```python
"""Dataflow summary panel — call graph + per-function flow summaries as a collapsible tree."""

from __future__ import annotations

import logging

from textual.message import Message
from textual.widgets import Tree

from interpreter.interprocedural.types import (
    CallGraph,
    CallSite,
    FieldEndpoint,
    FlowEndpoint,
    FunctionEntry,
    FunctionSummary,
    InterproceduralResult,
    ReturnEndpoint,
    SummaryKey,
    VariableEndpoint,
)

logger = logging.getLogger(__name__)


class FunctionSelected(Message):
    """Posted when a function node is selected in the tree."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label


def render_endpoint(ep: FlowEndpoint) -> str:
    """Render a FlowEndpoint as a human-readable string."""
    if isinstance(ep, VariableEndpoint):
        return ep.name
    if isinstance(ep, ReturnEndpoint):
        return f"Return({ep.function.label})"
    if isinstance(ep, FieldEndpoint):
        return f"Field({ep.base.name}.{ep.field})"
    return str(ep)


def build_function_callers(
    func: FunctionEntry, call_graph: CallGraph
) -> set[str]:
    """Find labels of all functions that call this function."""
    return {
        site.caller.label
        for site in call_graph.call_sites
        if func in site.callees
    }


def build_function_callees(
    func: FunctionEntry, call_graph: CallGraph
) -> set[str]:
    """Find labels of all functions called by this function."""
    return {
        callee.label
        for site in call_graph.call_sites
        if site.caller == func
        for callee in site.callees
    }


def merge_flows_for_function(
    func: FunctionEntry,
    summaries: dict[SummaryKey, FunctionSummary],
) -> set[tuple[FlowEndpoint, FlowEndpoint]]:
    """Merge flows across all call contexts for a function."""
    merged: set[tuple[FlowEndpoint, FlowEndpoint]] = set()
    for key, summary in summaries.items():
        if key.function == func:
            merged.update(summary.flows)
    return merged


class DataflowSummaryPanel(Tree):
    """Displays call graph and per-function summaries as a collapsible tree."""

    def __init__(self, result: InterproceduralResult | None = None, **kwargs) -> None:
        super().__init__("Dataflow", **kwargs)
        self._result = result

    def on_mount(self) -> None:
        if self._result is None:
            self.root.add_leaf("[dim]No dataflow analysis available[/dim]")
            return
        self._populate_tree()
        self.root.expand()

    def _populate_tree(self) -> None:
        result = self._result
        call_graph = result.call_graph
        sorted_functions = sorted(call_graph.functions, key=lambda f: f.label)

        for func in sorted_functions:
            params_str = ", ".join(func.params) if func.params else "(none)"
            func_node = self.root.add(
                f"{func.label} (params: {params_str})",
                data=func,
            )

            callers = build_function_callers(func, call_graph)
            callers_str = ", ".join(sorted(callers)) if callers else "(none)"
            func_node.add_leaf(f"callers: {callers_str}")

            callees = build_function_callees(func, call_graph)
            callees_str = ", ".join(sorted(callees)) if callees else "(none)"
            func_node.add_leaf(f"callees: {callees_str}")

            flows = merge_flows_for_function(func, result.summaries)
            flows_node = func_node.add(f"Flows ({len(flows)})")
            for src, dst in sorted(flows, key=lambda f: render_endpoint(f[0])):
                flows_node.add_leaf(f"{render_endpoint(src)} → {render_endpoint(dst)}")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """When a function node is clicked, post FunctionSelected message."""
        node = event.node
        if node.data is not None and isinstance(node.data, FunctionEntry):
            self.post_message(FunctionSelected(node.data.label))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_dataflow_summary_panel.py -x -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add viz/panels/dataflow_summary_panel.py tests/unit/test_dataflow_summary_panel.py
git commit -m "feat(viz): add dataflow summary panel with call graph and flow tree"
```

---

### Task 3: Create whole-program graph panel

**Files:**
- Create: `viz/panels/dataflow_graph_panel.py`
- Test: `tests/unit/test_dataflow_graph_panel.py`

- [ ] **Step 1: Write unit tests for annotation logic**

```python
# tests/unit/test_dataflow_graph_panel.py
"""Tests for whole-program graph panel rendering."""

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
from viz.panels.dataflow_graph_panel import annotate_endpoint, render_graph_lines


class TestAnnotateEndpoint:
    def test_named_variable_no_annotation(self):
        ep = VariableEndpoint(name="x", definition=NO_DEFINITION)
        assert annotate_endpoint(ep, None) == "x"

    def test_register_with_call_definition(self):
        inst = IRInstruction(
            opcode=Opcode.CALL_FUNCTION, result_reg="%8",
            operands=["f", "%7"],
        )
        defn = Definition(
            variable="%8", block_label="func_g_2",
            instruction_index=3, instruction=inst,
        )
        ep = VariableEndpoint(name="%8", definition=defn)
        assert annotate_endpoint(ep, None) == "%8 (call result: f)"

    def test_register_with_non_call_definition(self):
        inst = IRInstruction(
            opcode=Opcode.BINOP, result_reg="%3",
            operands=["+", "%1", "%2"],
        )
        defn = Definition(
            variable="%3", block_label="func_f_0",
            instruction_index=4, instruction=inst,
        )
        ep = VariableEndpoint(name="%3", definition=defn)
        assert annotate_endpoint(ep, None) == "%3"

    def test_return_endpoint(self):
        func = FunctionEntry(label="func_f_0", params=("x",))
        loc = InstructionLocation(block_label="func_f_0", instruction_index=5)
        ep = ReturnEndpoint(function=func, location=loc)
        assert annotate_endpoint(ep, None) == "Return(func_f_0)"

    def test_field_endpoint(self):
        base = VariableEndpoint(name="self", definition=NO_DEFINITION)
        loc = InstructionLocation(block_label="b", instruction_index=1)
        ep = FieldEndpoint(base=base, field="name", location=loc)
        assert annotate_endpoint(ep, None) == "Field(self.name)"


class TestRenderGraphLines:
    def test_renders_edges_grouped_by_source(self):
        f = FunctionEntry(label="func_f_0", params=("x",))
        loc = InstructionLocation(block_label="func_f_0", instruction_index=5)
        x_ep = VariableEndpoint(name="x", definition=NO_DEFINITION)
        ret_ep = ReturnEndpoint(function=f, location=loc)
        graph = {x_ep: frozenset({ret_ep})}
        lines = render_graph_lines(graph, None)
        assert any("x" in line and "Return(func_f_0)" in line for line in lines)

    def test_empty_graph(self):
        lines = render_graph_lines({}, None)
        assert len(lines) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_dataflow_graph_panel.py -x -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the panel**

Create `viz/panels/dataflow_graph_panel.py`:

```python
"""Whole-program graph panel — renders interprocedural flow edges with register annotations."""

from __future__ import annotations

import logging

from rich.text import Text
from textual.widgets import Static

from interpreter.cfg_types import CFG
from interpreter.interprocedural.types import (
    FlowEndpoint,
    InterproceduralResult,
    NO_DEFINITION,
    VariableEndpoint,
)
from interpreter.ir import Opcode
from viz.panels.dataflow_summary_panel import render_endpoint

logger = logging.getLogger(__name__)


def annotate_endpoint(ep: FlowEndpoint, cfg: CFG | None) -> str:
    """Render a FlowEndpoint with register annotation for VariableEndpoints.

    Reuses render_endpoint from the summary panel for non-register cases.
    """
    if isinstance(ep, VariableEndpoint):
        name = ep.name
        if name.startswith("%") and ep.definition != NO_DEFINITION:
            opcode = ep.definition.instruction.opcode
            if opcode in (Opcode.CALL_FUNCTION, Opcode.CALL_METHOD):
                callee_name = str(ep.definition.instruction.operands[0])
                return f"{name} (call result: {callee_name})"
        return name
    return render_endpoint(ep)


def render_graph_lines(
    graph: dict[FlowEndpoint, frozenset[FlowEndpoint]],
    cfg: CFG | None,
) -> list[str]:
    """Render graph edges as human-readable lines grouped by source."""
    lines: list[str] = []
    sorted_sources = sorted(graph.keys(), key=lambda ep: annotate_endpoint(ep, cfg))
    for src in sorted_sources:
        src_str = annotate_endpoint(src, cfg)
        dsts = sorted(graph[src], key=lambda ep: annotate_endpoint(ep, cfg))
        for dst in dsts:
            dst_str = annotate_endpoint(dst, cfg)
            lines.append(f"{src_str} → {dst_str}")
    return lines


class DataflowGraphPanel(Static):
    """Displays the whole-program flow graph with annotated edges."""

    def __init__(
        self,
        result: InterproceduralResult | None = None,
        cfg: CFG | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._result = result
        self._cfg = cfg

    def on_mount(self) -> None:
        self._render_graph()

    def _render_graph(self) -> None:
        if self._result is None:
            self.update("[dim]No dataflow analysis available[/dim]")
            return

        graph = self._result.whole_program_graph
        edge_count = sum(len(dsts) for dsts in graph.values())
        lines = render_graph_lines(graph, self._cfg)

        text = Text()
        text.append(
            f"WHOLE-PROGRAM GRAPH ({edge_count} edges)\n\n",
            style="bold magenta",
        )

        for line in lines:
            arrow_idx = line.index("→")
            src_part = line[:arrow_idx]
            dst_part = line[arrow_idx + 1 :].strip()
            text.append(src_part, style="cyan")
            text.append("→ ", style="dim")
            text.append(f"{dst_part}\n", style="yellow")

        self.update(text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_dataflow_graph_panel.py -x -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add viz/panels/dataflow_graph_panel.py tests/unit/test_dataflow_graph_panel.py
git commit -m "feat(viz): add whole-program graph panel with register annotations"
```

---

### Task 4: Add highlight_block to IRPanel

**Files:**
- Modify: `viz/panels/ir_panel.py`

- [ ] **Step 1: Add the `highlight_block` method and `_highlighted_block` state**

In `viz/panels/ir_panel.py`, add after the `__init__` method:

```python
    def __init__(self, cfg: CFG | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cfg = cfg
        self._highlighted_block: str | None = None
```

Add the method:
```python
    def highlight_block(self, label: str | None) -> None:
        """Highlight a named block (used by dataflow mode). Pass None to clear."""
        self._highlighted_block = label
        self._render_ir()
```

Update `_render_ir` to use `_highlighted_block` as fallback when `current_step` is None:

In `_render_ir`, after `current_block = step.block_label if step else ""`:
```python
        # In dataflow mode, current_step is not set; use highlighted block instead
        if not current_block and self._highlighted_block:
            current_block = self._highlighted_block
            current_idx = -1  # highlight block header only, not a specific instruction
```

- [ ] **Step 2: Run existing tests to check no regression**

Run: `poetry run python -m pytest tests/ -x --tb=short -q`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add viz/panels/ir_panel.py
git commit -m "feat(viz): add highlight_block to IRPanel for dataflow mode"
```

---

### Task 5: Integrate dataflow mode into PipelineApp

**Files:**
- Modify: `viz/app.py`

- [ ] **Step 1: Add imports**

```python
from viz.panels.dataflow_summary_panel import DataflowSummaryPanel, FunctionSelected
from viz.panels.dataflow_graph_panel import DataflowGraphPanel
```

- [ ] **Step 2: Update CSS**

Add to the CSS string after the existing rules:

```css
    #dataflow-summary-container {
        border: solid rgb(80,120,140);
        overflow-y: auto;
        display: none;
    }

    #dataflow-graph-container {
        border: solid rgb(140,80,140);
        overflow-y: auto;
        display: none;
    }

    Screen.dataflow-mode {
        grid-size: 2 2;
        grid-columns: 1fr 2fr;
        grid-rows: 1fr 1fr;
    }

    Screen.dataflow-mode #ast-container,
    Screen.dataflow-mode #vm-state-container,
    Screen.dataflow-mode #cfg-container {
        display: none;
    }

    Screen.dataflow-mode #dataflow-summary-container,
    Screen.dataflow-mode #dataflow-graph-container {
        display: block;
    }
```

- [ ] **Step 3: Add keybinding**

In `BINDINGS`, add:
```python
        Binding("d", "toggle_dataflow", "Dataflow", show=True),
```

- [ ] **Step 4: Add state tracking**

In `__init__`, add:
```python
        self._dataflow_mode = False
        self._saved_instruction: IRInstruction | None = None
```

- [ ] **Step 5: Compose the new panels**

In `compose()`, add the dataflow panels after the existing panels (before `yield Footer()`):

```python
        with Vertical(id="dataflow-summary-container"):
            yield Static(" Call Graph + Summaries", classes="panel-title")
            yield DataflowSummaryPanel(
                self._result.interprocedural, id="dataflow-summary-panel"
            )

        with Vertical(id="dataflow-graph-container"):
            yield Static(" Whole-Program Graph", classes="panel-title")
            yield DataflowGraphPanel(
                self._result.interprocedural,
                cfg=self._result.cfg,
                id="dataflow-graph-panel",
            )
```

- [ ] **Step 6: Implement mode toggle action**

```python
    def action_toggle_dataflow(self) -> None:
        self._dataflow_mode = not self._dataflow_mode
        self.screen.set_class(self._dataflow_mode, "dataflow-mode")

        source_panel = self.query_one("#source-panel", SourcePanel)
        ir_panel = self.query_one("#ir-panel", IRPanel)

        if self._dataflow_mode:
            # Save current instruction, clear for manual highlighting
            self._saved_instruction = source_panel.current_instruction
            source_panel.current_instruction = None
            ir_panel.highlight_block(None)
        else:
            # Restore step-based highlighting, clear manual highlight
            source_panel._highlight_start = -1
            source_panel._highlight_end = -1
            ir_panel.highlight_block(None)
            if self._saved_instruction:
                source_panel.current_instruction = self._saved_instruction
            self._update_panels()
```

- [ ] **Step 7: Handle FunctionSelected message**

```python
    def on_function_selected(self, message: FunctionSelected) -> None:
        """Cross-highlight source and IR when a function is selected in the dataflow tree."""
        cfg = self._result.cfg
        label = message.label

        # Highlight IR block
        ir_panel = self.query_one("#ir-panel", IRPanel)
        ir_panel.highlight_block(label)

        # Compute function source span from all blocks with matching prefix
        source_panel = self.query_one("#source-panel", SourcePanel)
        min_line = float("inf")
        max_line = 0
        for block_label, block in cfg.blocks.items():
            if block_label == label or block_label.startswith(label + "_"):
                for inst in block.instructions:
                    loc = inst.source_location
                    if loc.is_unknown():
                        continue
                    min_line = min(min_line, loc.start_line)
                    max_line = max(max_line, loc.end_line)

        if max_line > 0:
            source_panel.highlight_lines(int(min_line), int(max_line))
```

- [ ] **Step 8: Write integration test for mode toggle and cross-highlighting**

Add to `tests/integration/test_dataflow_tui.py`:

```python
class TestDataflowModeToggle:
    """Test mode toggle state transitions (non-async, tests PipelineApp state)."""

    SOURCE = "def f(x):\n    return x + 1\nf(1)\n"

    def test_function_source_span_computation(self):
        """Verify that function block prefix matching finds the right source lines."""
        from viz.pipeline import run_pipeline

        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        cfg = result.cfg

        # Find the function entry label
        func_labels = [l for l in cfg.blocks if l.startswith("func_f")]
        assert len(func_labels) >= 1
        label = func_labels[0]

        # Compute span using same logic as on_function_selected
        min_line = float("inf")
        max_line = 0
        for block_label, block in cfg.blocks.items():
            if block_label == label or block_label.startswith(label + "_"):
                for inst in block.instructions:
                    loc = inst.source_location
                    if loc.is_unknown():
                        continue
                    min_line = min(min_line, loc.start_line)
                    max_line = max(max_line, loc.end_line)

        assert max_line > 0, "Should find source lines for function f"
        assert min_line <= 2, "Function f starts at line 1 or 2"
```

- [ ] **Step 9: Verify the full TUI launches**

Run manually: `poetry run python -m viz viz/examples/factorial.py -l python`
- Press `d` → should switch to dataflow mode (2 panels on right)
- Press `d` again → should return to normal mode
- In dataflow mode, click a function → source/IR should highlight

- [ ] **Step 10: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 11: Run black formatter**

Run: `poetry run python -m black viz/ tests/unit/test_dataflow_summary_panel.py tests/unit/test_dataflow_graph_panel.py tests/integration/test_dataflow_tui.py`

- [ ] **Step 12: Commit**

```bash
git add viz/app.py
git commit -m "feat(viz): integrate dataflow mode into PipelineApp with d keybinding"
```

---

### Task 6: Final validation and cleanup

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass, no regressions.

- [ ] **Step 2: Run black on entire codebase**

Run: `poetry run python -m black .`

- [ ] **Step 3: Manual smoke test**

Test with multiple languages:
```bash
# Python
poetry run python -m viz viz/examples/factorial.py -l python
# Press d, explore, press d back

# Create a quick JS test file
echo 'function add(a, b) { return a + b; } var r = add(1, 2);' > /tmp/test.js
poetry run python -m viz /tmp/test.js -l javascript
```

- [ ] **Step 4: Update README if needed**

Add a bullet under VM features or a new section noting dataflow visualization:
> **Dataflow visualization** — press `d` in the pipeline TUI to toggle dataflow mode, showing the interprocedural call graph, per-function flow summaries, and whole-program dependency graph alongside source and IR

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(viz): dataflow TUI panel — call graph, summaries, whole-program graph"
```
