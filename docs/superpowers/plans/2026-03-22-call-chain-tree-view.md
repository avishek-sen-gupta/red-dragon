# Call-Chain Tree View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat edge list in `DataflowGraphPanel` with a collapsible call-chain tree that traces data flow from top-level call sites through the call chain, showing per-param paths at each level.

**Architecture:** Pure helper functions build a `ChainNode` tree (data model) from the interprocedural analysis result, then the panel renders it as a Textual `Tree` widget. Top-level calls are found by scanning `end_*` blocks in the CFG (not from `call_graph.call_sites`, which skips top-level code). Inner call connections are found by tracing arg registers back to named variables.

**Tech Stack:** Textual 8.1.0 `Tree` widget, existing `InterproceduralResult` data.

**Spec:** `docs/superpowers/specs/2026-03-22-call-chain-tree-view-design.md`

---

### File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `viz/panels/dataflow_graph_panel.py` | Modify | Add `TopLevelCall`, `ChainNode` dataclasses; add `find_top_level_call_sites`, `trace_reg_to_var`, `build_call_chain` pure functions; change base class from `Static` to `Tree`; add `_populate_tree`; keep existing `annotate_endpoint`/`render_graph_lines` |
| `tests/unit/test_dataflow_graph_panel.py` | Modify | Add tests for new functions; keep existing `annotate_endpoint`/`render_graph_lines` tests |
| `tests/integration/test_dataflow_tui.py` | Modify | Add integration test: multi-function program produces non-empty call-chain tree |

---

### Task 1: Add data model and `find_top_level_call_sites`

**Files:**
- Modify: `viz/panels/dataflow_graph_panel.py`
- Modify: `tests/unit/test_dataflow_graph_panel.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_dataflow_graph_panel.py`:

```python
from interpreter.cfg import build_cfg
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.interprocedural.analyze import analyze_interprocedural
from interpreter.registry import build_registry
from viz.panels.dataflow_graph_panel import (
    TopLevelCall,
    ChainNode,
    find_top_level_call_sites,
    trace_reg_to_var,
)


def _analyze(source: str, language: Language = Language.PYTHON):
    """Helper: run full pipeline and return (cfg, result)."""
    frontend = get_frontend(language)
    ir = frontend.lower(source.encode())
    cfg = build_cfg(ir)
    registry = build_registry(
        ir, cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    result = analyze_interprocedural(cfg, registry)
    return cfg, result


class TestFindTopLevelCallSites:
    def test_single_top_level_call(self):
        source = "def f(x):\n    return x\nresult = f(5)\n"
        cfg, result = _analyze(source)
        top_calls = find_top_level_call_sites(cfg, result.call_graph)
        assert len(top_calls) >= 1
        call = top_calls[0]
        assert "f" in call.callee_label or "func_f" in call.callee_label
        assert call.result_var == "result"

    def test_no_functions_no_top_level_calls(self):
        source = "x = 1\ny = x + 1\n"
        cfg, result = _analyze(source)
        top_calls = find_top_level_call_sites(cfg, result.call_graph)
        assert len(top_calls) == 0

    def test_multi_function_finds_outermost_call(self):
        source = (
            "def add(a, b):\n    return a + b\n"
            "def double(x):\n    return add(x, x)\n"
            "result = double(5)\n"
        )
        cfg, result = _analyze(source)
        top_calls = find_top_level_call_sites(cfg, result.call_graph)
        assert len(top_calls) >= 1
        # The top-level call should be to double, not add
        assert any("double" in c.callee_label for c in top_calls)


class TestTraceRegToVar:
    def test_traces_load_var(self):
        source = "def f(x):\n    return x\nresult = f(5)\n"
        cfg, _ = _analyze(source)
        # Find a block with LOAD_VAR
        for label, block in cfg.blocks.items():
            for inst in block.instructions:
                if inst.opcode == Opcode.LOAD_VAR and inst.result_reg:
                    traced = trace_reg_to_var(inst.result_reg, cfg, label)
                    assert traced == str(inst.operands[0])
                    return
        raise AssertionError("No LOAD_VAR found in test program")

    def test_traces_store_var_consumer(self):
        source = "def f(x):\n    return x\nresult = f(5)\n"
        cfg, _ = _analyze(source)
        # Find the call_function result_reg and check it traces to 'result'
        for label, block in cfg.blocks.items():
            for inst in block.instructions:
                if inst.opcode == Opcode.CALL_FUNCTION and inst.result_reg:
                    traced = trace_reg_to_var(inst.result_reg, cfg, label)
                    # Should trace to 'result' (store_var result %reg)
                    if traced != inst.result_reg:
                        assert traced == "result"
                        return
        # If call result isn't in same block as store_var, that's OK
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_dataflow_graph_panel.py::TestFindTopLevelCallSites -x -v`
Expected: FAIL — `TopLevelCall` not defined.

- [ ] **Step 3: Implement data model and functions**

Add to `viz/panels/dataflow_graph_panel.py` (after existing imports, before `annotate_endpoint`):

```python
from dataclasses import dataclass, field
from functools import reduce

from interpreter.interprocedural.call_graph import (
    CALL_OPCODES,
    _build_block_to_function,
    build_function_entries,
)
from interpreter.interprocedural.types import (
    CallGraph,
    FunctionEntry,
    FunctionSummary,
    SummaryKey,
)
from interpreter.ir import IRInstruction, VAR_DEFINITION_OPCODES


@dataclass(frozen=True)
class TopLevelCall:
    """A call instruction in top-level code (not inside any function)."""
    callee_label: str
    arg_operands: tuple[str, ...]
    result_var: str
    block_label: str
    instruction_index: int


@dataclass
class ChainNode:
    """Intermediate tree node for call-chain rendering."""
    label: str
    children: list[ChainNode] = field(default_factory=list)


def trace_reg_to_var(reg: str, cfg: CFG, block_label: str) -> str:
    """Trace a register back to its named variable by scanning the block.

    If the register was produced by LOAD_VAR x → %reg, return "x".
    If a STORE_VAR/DECL_VAR consumes the register, return that variable name.
    Falls back to the register name itself.
    """
    block = cfg.blocks[block_label]
    load_match = next(
        (str(inst.operands[0]) for inst in block.instructions
         if inst.opcode == Opcode.LOAD_VAR and inst.result_reg == reg),
        "",
    )
    if load_match:
        return load_match
    store_match = next(
        (str(inst.operands[0]) for inst in block.instructions
         if inst.opcode in VAR_DEFINITION_OPCODES
         and len(inst.operands) >= 2
         and str(inst.operands[1]) == reg),
        "",
    )
    return store_match if store_match else reg


def _resolve_callee_label(
    callee_name: str, func_by_name: dict[str, str]
) -> str:
    """Resolve a call target name to a function entry label."""
    return func_by_name.get(callee_name, callee_name)


def find_top_level_call_sites(cfg: CFG, call_graph: CallGraph) -> list[TopLevelCall]:
    """Find CALL_FUNCTION/CALL_METHOD instructions in top-level code.

    Scans all blocks NOT owned by any function (using the block-to-function
    mapping from call_graph.py). These calls are not in call_graph.call_sites
    because build_call_graph skips non-function blocks.
    """
    # Build function-name → label lookup from call_graph.functions
    func_by_name: dict[str, str] = {
        f.label.split("_")[1] if f.label.startswith("func_") else f.label: f.label
        for f in call_graph.functions
    }
    # Also map labels to themselves
    func_by_name.update({f.label: f.label for f in call_graph.functions})

    # Identify function-owned blocks
    func_entries = {f.label: f for f in call_graph.functions}
    owned_blocks = {
        label
        for label, block in cfg.blocks.items()
        for f in call_graph.functions
        if label == f.label or label.startswith(f.label + "_")
    }
    # Also mark blocks reachable from func entries (via extract_sub_cfg logic)
    # Simpler: use _build_block_to_function which maps blocks to their owning function
    # We need to build function_entries dict for it
    func_entries_dict = {f.label: f for f in call_graph.functions}
    block_to_func = _build_block_to_function(cfg, func_entries_dict)
    non_func_blocks = {
        label for label in cfg.blocks if label not in block_to_func
    }

    return [
        TopLevelCall(
            callee_label=_resolve_callee_label(
                str(inst.operands[0]) if inst.opcode == Opcode.CALL_FUNCTION
                else str(inst.operands[1]),
                func_by_name,
            ),
            arg_operands=(
                tuple(str(op) for op in inst.operands[1:])
                if inst.opcode == Opcode.CALL_FUNCTION
                else tuple(str(op) for op in inst.operands[2:])
            ),
            result_var=(
                trace_reg_to_var(inst.result_reg, cfg, label)
                if inst.result_reg else ""
            ),
            block_label=label,
            instruction_index=idx,
        )
        for label in non_func_blocks
        for idx, inst in enumerate(cfg.blocks[label].instructions)
        if inst.opcode in (Opcode.CALL_FUNCTION, Opcode.CALL_METHOD)
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_dataflow_graph_panel.py -x -v`
Expected: All tests PASS (old + new).

- [ ] **Step 5: Commit**

```bash
git add viz/panels/dataflow_graph_panel.py tests/unit/test_dataflow_graph_panel.py
git commit -m "feat(viz): add TopLevelCall/ChainNode models and find_top_level_call_sites"
```

---

### Task 2: Add `build_call_chain` recursive tree builder

**Files:**
- Modify: `viz/panels/dataflow_graph_panel.py`
- Modify: `tests/unit/test_dataflow_graph_panel.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_dataflow_graph_panel.py`:

```python
from viz.panels.dataflow_graph_panel import build_call_chain


class TestBuildCallChain:
    def test_simple_function_shows_param_to_return(self):
        """f(x) -> return x+1: chain should show x → return(f)."""
        source = "def f(x):\n    return x + 1\nf(5)\n"
        cfg, result = _analyze(source)
        f_entry = [f for f in result.call_graph.functions if "f" in f.label][0]
        nodes = build_call_chain(
            f_entry, result.call_graph, result.summaries, cfg, set()
        )
        assert len(nodes) >= 1
        assert any("x" in n.label and "return" in n.label.lower() for n in nodes)

    def test_caller_callee_chain_has_nested_nodes(self):
        """double(x) calls add(x, x): chain should have nested subtree."""
        source = (
            "def add(a, b):\n    return a + b\n"
            "def double(x):\n    return add(x, x)\n"
            "double(5)\n"
        )
        cfg, result = _analyze(source)
        double_entry = [f for f in result.call_graph.functions if "double" in f.label][0]
        nodes = build_call_chain(
            double_entry, result.call_graph, result.summaries, cfg, set()
        )
        # Should have a node for x flowing to add(), with children for a, b
        has_nested = any(len(n.children) > 0 for n in nodes)
        assert has_nested, f"Expected nested nodes, got: {[n.label for n in nodes]}"

    def test_recursive_function_stops_at_guard(self):
        """factorial(n) calls factorial(n-1): should not infinite-loop."""
        source = (
            "def factorial(n):\n"
            "    if n <= 1:\n"
            "        return 1\n"
            "    return n * factorial(n - 1)\n"
            "factorial(5)\n"
        )
        cfg, result = _analyze(source)
        f_entry = [f for f in result.call_graph.functions if "factorial" in f.label][0]
        nodes = build_call_chain(
            f_entry, result.call_graph, result.summaries, cfg, set()
        )
        # Should terminate and have a recursive guard leaf
        all_labels = _collect_labels(nodes)
        assert any("recursive" in lbl.lower() for lbl in all_labels), (
            f"Expected recursion guard, got: {all_labels}"
        )


def _collect_labels(nodes: list[ChainNode]) -> list[str]:
    """Collect all labels from a ChainNode tree."""
    result = []
    for n in nodes:
        result.append(n.label)
        result.extend(_collect_labels(n.children))
    return result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_dataflow_graph_panel.py::TestBuildCallChain -x -v`
Expected: FAIL — `build_call_chain` not defined.

- [ ] **Step 3: Implement `build_call_chain`**

Add to `viz/panels/dataflow_graph_panel.py`:

```python
from viz.panels.dataflow_summary_panel import (
    render_endpoint,
    merge_flows_for_function,
)
from interpreter.interprocedural.types import ReturnEndpoint, FieldEndpoint


def _build_param_map(site, callee: FunctionEntry, cfg: CFG) -> dict[str, str]:
    """Map callee formal params to caller actual arg names."""
    block_label = site.location.block_label
    return {
        formal: trace_reg_to_var(actual_reg, cfg, block_label)
        for formal, actual_reg in zip(callee.params, site.arg_operands)
    }


def _param_inner_calls(
    param: str,
    inner_sites: list,
    cfg: CFG,
    params_set: frozenset[str],
) -> list[tuple]:
    """Find inner call sites where this param flows as an argument."""
    return [
        (site, arg_op)
        for site in inner_sites
        for arg_op in site.arg_operands
        if trace_reg_to_var(arg_op, cfg, site.location.block_label) == param
    ]


def build_call_chain(
    func_entry: FunctionEntry,
    call_graph: CallGraph,
    summaries: dict[SummaryKey, FunctionSummary],
    cfg: CFG,
    visited: set[str],
) -> list[ChainNode]:
    """Recursively build a call-chain tree for a function.

    Shows per-param flows: to return (leaf), to field writes (leaf),
    or through inner call sites (recursive subtree).
    """
    if func_entry.label in visited:
        return [ChainNode(label="[recursive — see above]")]
    visited = visited | {func_entry.label}

    flows = merge_flows_for_function(func_entry, summaries)
    inner_sites = [s for s in call_graph.call_sites if s.caller == func_entry]
    params_set = frozenset(func_entry.params)

    def _nodes_for_param(param: str) -> list[ChainNode]:
        inner_calls = _param_inner_calls(param, inner_sites, cfg, params_set)
        call_nodes = [
            ChainNode(
                label=f"{param} → {callee.label}({', '.join(f'{p}={v}' for p, v in _build_param_map(site, callee, cfg).items())})",
                children=build_call_chain(callee, call_graph, summaries, cfg, visited),
            )
            for site, arg_op in inner_calls
            for callee in site.callees
        ]
        return_nodes = [
            ChainNode(label=f"{param} → return({func_entry.label})")
            for src, dst in flows
            if isinstance(src, VariableEndpoint) and src.name == param
            and isinstance(dst, ReturnEndpoint)
        ]
        field_nodes = [
            ChainNode(label=f"{param} → Field({dst.base.name}.{dst.field})")
            for src, dst in flows
            if isinstance(src, VariableEndpoint) and src.name == param
            and isinstance(dst, FieldEndpoint)
        ]
        return call_nodes + return_nodes + field_nodes

    return [node for param in func_entry.params for node in _nodes_for_param(param)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_dataflow_graph_panel.py -x -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add viz/panels/dataflow_graph_panel.py tests/unit/test_dataflow_graph_panel.py
git commit -m "feat(viz): add build_call_chain recursive tree builder"
```

---

### Task 3: Change panel from Static to Tree

**Files:**
- Modify: `viz/panels/dataflow_graph_panel.py`
- Modify: `tests/integration/test_dataflow_tui.py`

- [ ] **Step 1: Write integration test**

Append to `tests/integration/test_dataflow_tui.py`:

```python
class TestCallChainTreeView:
    SOURCE = """\
def add(a, b):
    return a + b

def double(x):
    return add(x, x)

result = double(5)
"""

    def test_pipeline_produces_nonempty_call_chain(self):
        """The call-chain tree builder produces nodes for a multi-function program."""
        from viz.panels.dataflow_graph_panel import (
            find_top_level_call_sites,
            build_call_chain,
        )

        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        interprocedural = result.interprocedural
        assert interprocedural is not None

        top_calls = find_top_level_call_sites(result.cfg, interprocedural.call_graph)
        assert len(top_calls) >= 1, "Should find top-level call to double()"

        # Build chain for the callee
        callee_label = top_calls[0].callee_label
        callee_entry = [
            f for f in interprocedural.call_graph.functions
            if f.label == callee_label
        ][0]
        nodes = build_call_chain(
            callee_entry,
            interprocedural.call_graph,
            interprocedural.summaries,
            result.cfg,
            set(),
        )
        assert len(nodes) > 0, "Call chain should have at least one node"
```

- [ ] **Step 2: Change base class from Static to Tree**

In `viz/panels/dataflow_graph_panel.py`, change:

```python
# Old:
from textual.widgets import Static
# ...
class DataflowGraphPanel(Static):

# New:
from textual.widgets import Static, Tree
# ...
class DataflowGraphPanel(Tree):
```

Update `__init__`:
```python
    def __init__(
        self,
        result: InterproceduralResult | None = None,
        cfg: CFG | None = None,
        **kwargs,
    ) -> None:
        super().__init__("Call Chains", **kwargs)
        self._result = result
        self._cfg = cfg
```

Replace `on_mount` to call `_populate_tree`:
```python
    def on_mount(self) -> None:
        if self._result is None:
            self.root.add_leaf("[dim]No dataflow analysis available[/dim]")
            return
        self._populate_tree()
        self.root.expand()

    def _populate_tree(self) -> None:
        cfg = self._cfg
        result = self._result
        top_calls = find_top_level_call_sites(cfg, result.call_graph)

        func_by_label = {f.label: f for f in result.call_graph.functions}

        for call in top_calls:
            callee_entry = func_by_label[call.callee_label]
            root_label = f"{call.callee_label}({', '.join(call.arg_operands)}) → {call.result_var}"
            root_node = self.root.add(root_label)

            chain_nodes = build_call_chain(
                callee_entry, result.call_graph, result.summaries, cfg, set()
            )
            self._add_chain_nodes(root_node, chain_nodes)

        if not top_calls:
            # Fallback: show per-function chains for all functions
            for func in sorted(result.call_graph.functions, key=lambda f: f.label):
                func_node = self.root.add(f"{func.label}({', '.join(func.params)})")
                chain_nodes = build_call_chain(
                    func, result.call_graph, result.summaries, cfg, set()
                )
                self._add_chain_nodes(func_node, chain_nodes)

    def _add_chain_nodes(self, parent, chain_nodes: list[ChainNode]) -> None:
        """Recursively convert ChainNode tree into Textual TreeNode widgets."""
        for node in chain_nodes:
            if node.children:
                tree_node = parent.add(node.label)
                self._add_chain_nodes(tree_node, node.children)
            else:
                parent.add_leaf(node.label)
```

Remove `_render_graph` method (no longer used by the panel, but keep `render_graph_lines` as a public function).

- [ ] **Step 3: Run all tests**

Run: `poetry run python -m pytest tests/unit/test_dataflow_graph_panel.py tests/integration/test_dataflow_tui.py -x -v`
Expected: All tests PASS.

- [ ] **Step 4: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All pass, no regressions.

- [ ] **Step 5: Run black**

Run: `poetry run python -m black .`

- [ ] **Step 6: Commit**

```bash
git add viz/panels/dataflow_graph_panel.py tests/integration/test_dataflow_tui.py
git commit -m "feat(viz): replace flat edge list with collapsible call-chain tree"
```

---

### Task 4: Final validation and smoke test

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All pass.

- [ ] **Step 2: Manual smoke test with multi-function program**

```bash
cat > /tmp/multi_func.py << 'EOF'
def add(a, b):
    return a + b

def double(x):
    return add(x, x)

def quadruple(n):
    return double(double(n))

result = quadruple(5)
EOF
poetry run python -m viz /tmp/multi_func.py -l python
# Press d → dataflow mode
# Bottom-right panel should show collapsible call chain tree
# Expand nodes to see param flow paths
```

- [ ] **Step 3: Smoke test with recursive function**

```bash
cat > /tmp/factorial.py << 'EOF'
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

result = factorial(5)
EOF
poetry run python -m viz /tmp/factorial.py -l python
# Press d → should show factorial chain with [recursive — see above] guard
```

- [ ] **Step 4: Run black on codebase**

Run: `poetry run python -m black .`

- [ ] **Step 5: Final commit and push**

```bash
git push origin main
```
