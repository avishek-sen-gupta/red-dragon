# Call-Chain Tree View for Whole-Program Graph Panel

**Date:** 2026-03-22
**Status:** Accepted
**Depends on:** `2026-03-22-dataflow-tui-panel-design.md`

## Context

The whole-program graph panel (`DataflowGraphPanel`) currently renders interprocedural flow edges as a flat list of `source → destination` lines. This is technically correct but hard to interpret — register names like `%15` are meaningless, and the flat structure doesn't show how data flows through call chains.

## Decision

Replace the flat edge list with a collapsible `Tree` widget that traces data flow from each top-level call site downward through the call chain, showing per-param flow paths at each level.

## Design

### Tree Structure

For a program like:
```python
def add(a, b):
    return a + b

def double(x):
    return add(x, x)

def quadruple(n):
    return double(double(n))

result = quadruple(5)
```

The tree renders as:
```
▼ quadruple(5) → result
    ▼ n → double(x=n)
        ▼ x → add(a=x, b=x)
            a → return(add)
            b → return(add)
        return(add) → return(double)
    ▼ return(double) → double(x=return(double))
        ▼ x → add(a=x, b=x)
            a → return(add)
            b → return(add)
        return(add) → return(double)
    return(double) → return(quadruple)
```

Each level shows how each parameter of the callee flows (to return, to field writes, or to further calls).

### Top-Level Roots

Root nodes are top-level call sites. Since `build_call_graph` in `call_graph.py` skips non-function blocks (line 102-105: `if caller is None: continue`), top-level call sites are NOT present in `call_graph.call_sites`.

`find_top_level_call_sites` scans the CFG directly: iterate all blocks, skip those reachable from any `func_*` entry, and collect `CALL_FUNCTION`/`CALL_METHOD` instructions. For each found call, resolve the callee using the same `_resolve_call_function_callees` logic from `call_graph.py` (or look up the callee in `call_graph.functions` by name). Returns a list of `TopLevelCall` dataclass instances (not `CallSite`, since there's no `caller` FunctionEntry for top-level code).

```python
@dataclass(frozen=True)
class TopLevelCall:
    callee_label: str
    arg_operands: tuple[str, ...]
    result_var: str  # variable that receives the return value
    block_label: str
    instruction_index: int
```

The `result_var` is determined by scanning subsequent instructions in the same block for a `STORE_VAR` or `DECL_VAR` that consumes the call's `result_reg`.

### Building the Tree

The tree is built by walking the call graph top-down from each `TopLevelCall`:

1. For each top-level call, create a root node: `callee_name(args) → result_var`
2. Look up the callee's `FunctionEntry` in `call_graph.functions` by label
3. Merge all summary flows for that function (union across contexts, same as summary panel)
4. For each param→return flow: add a leaf `param → return(func)`
5. For each param→field flow: add a leaf `param → Field(obj.field)`
6. For param flows that reach a call site within the callee: find `CallSite` objects in `call_graph.call_sites` where `site.caller == callee_entry`, then check which params flow to the call's arg operands. For each matching inner call, recurse — creating a subtree for that callee.

**Connecting params to inner call sites (step 6):** Summary flows only tell us `param → return` or `param → field`. To find which params reach inner calls, trace the param through the callee's sub-CFG: for each `CallSite` where `site.caller == callee_entry`, check if any `arg_operand` register was loaded from a param variable (scan for `LOAD_VAR param_name` producing a register that matches an arg operand, or use `_trace_reg_to_var` to resolve). This join is: `param_name ∈ {_trace_reg_to_var(arg_op) for arg_op in site.arg_operands}`.

**`trace_reg_to_var`:** The existing `_trace_reg_to_var` in `propagation.py` (line 151-173) is a private function. Extract the logic into a public function in a shared location (e.g., `interpreter/interprocedural/utils.py`) or duplicate the 15-line function in `dataflow_graph_panel.py`. The function scans a block for `LOAD_VAR` producing the register or `DECL_VAR`/`STORE_VAR` consuming the register, returning the named variable.

### Recursion Guard

Recursive functions (`factorial → factorial`) would create infinite trees. Track a set of visited function labels on the current path. When a function is already in the visited set, emit a leaf: `[recursive — see above]`. This detects cycles (direct and mutual recursion) regardless of depth.

### Widget Change

`DataflowGraphPanel` changes from `textual.widgets.Static` to `textual.widgets.Tree`. The `__init__` passes `"Call Chains"` as the root label to `Tree.__init__`, and still accepts `result: InterproceduralResult | None` and `cfg: CFG | None`. The `on_mount` method calls `_populate_tree()` instead of `_render_graph()`.

### Pure Helper Functions

The tree-building logic is extracted into testable pure functions:

- `find_top_level_call_sites(cfg, call_graph) → list[TopLevelCall]` — scans CFG directly for calls in non-function blocks, resolves callee and result variable
- `build_call_chain(callee_entry, call_graph, summaries, cfg, visited) → list[ChainNode]` — recursively builds the tree structure as a data model
- `ChainNode` dataclass: `label: str, children: list[ChainNode]` — intermediate representation before Textual Tree rendering
- `trace_reg_to_var(reg, cfg, block_label) → str` — resolves register to named variable (extracted from propagation.py)

The panel's `_populate_tree` method converts `ChainNode` trees into Textual `TreeNode` widgets.

### Existing Functions

- `annotate_endpoint` stays as a public function (used by existing tests)
- `render_graph_lines` stays as a public function (same reason)
- Neither is used by the new tree rendering

### Files Changed

| File | Change |
|------|--------|
| `viz/panels/dataflow_graph_panel.py` | Change base class to `Tree`, add `TopLevelCall`/`ChainNode` dataclasses, add pure helper functions, add `_populate_tree`, keep existing functions |
| `tests/unit/test_dataflow_graph_panel.py` | Add tests for `find_top_level_call_sites`, `build_call_chain`; keep existing `annotate_endpoint` tests |

### Files NOT Changed

- `viz/app.py` — no changes needed, panel container and CSS work the same
- `viz/panels/dataflow_summary_panel.py` — unchanged
- `viz/pipeline.py` — unchanged
- `interpreter/interprocedural/` — unchanged (no modifications to analysis code)

## What This Does NOT Include

- No interactive navigation (clicking a node to jump to source) — the summary panel already handles cross-highlighting via `FunctionSelected`
- No filtering or search within the tree
- No alternate flat view toggle — the old flat view is replaced entirely
