# Interprocedural Dataflow Analysis — Design Spec

**Date:** 2026-03-22
**Type:** New feature — extends existing intraprocedural dataflow analysis

## Summary

Extend the existing intraprocedural dataflow analysis (`interpreter/dataflow.py`) with whole-program interprocedural analysis: call graph construction, per-function summaries with 1-CFA context sensitivity, depth-1 field-sensitive heap flow tracking, and query interfaces for impact analysis, taint tracking, and program slicing.

## Use Cases

1. **Impact analysis** — "If I change variable X in function A, which variables in other functions are affected?"
2. **Taint tracking** — "Can user input from source S reach security-sensitive sink K?" with witness path
3. **Program slicing** — "All statements that affect the value of variable Y at point P, across all functions"

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Virtual dispatch | CHA (class hierarchy analysis) | Simple, sound, uses existing FunctionRegistry |
| Whole vs demand | Whole-program upfront | Queries are O(1) after one-time computation |
| Heap/field flows | Depth-1 field-sensitive | CodeQL-style store/read — standard practice, covers OOP patterns |
| Context sensitivity | 1-CFA (one summary per call site) | Prevents false cross-contamination through utility functions |
| Existing code changes | None — separate field flow pass | Keep intraprocedural `dataflow.py` pristine |
| Traceability | All endpoints reference actual IR objects | No opaque string keys anywhere |

## Data Model

### Hashability Note

All types below are frozen dataclasses used in sets and dict keys. `BasicBlock` (mutable)
and `IRInstruction` (Pydantic BaseModel) are NOT hashable, so they are NOT stored directly.
Instead, types store **location coordinates** (label + index) that resolve to the actual
objects via CFG lookup. A `resolve(cfg)` helper on each type provides the actual objects
when needed. This keeps the data model hashable while maintaining traceability.

Per project conventions, `None` is not used. Sentinel objects (`NO_DEFINITION`,
`NO_INSTRUCTION_LOC`, `ROOT_CONTEXT`) replace nullable fields.

### InstructionLocation — hashable reference to an IR instruction

```python
@dataclass(frozen=True)
class InstructionLocation:
    block_label: str
    instruction_index: int

    def resolve(self, cfg: CFG) -> IRInstruction:
        return cfg.blocks[self.block_label].instructions[self.instruction_index]

NO_INSTRUCTION_LOC = InstructionLocation(block_label="", instruction_index=-1)
```

### FunctionEntry — a resolved function in the program

```python
@dataclass(frozen=True)
class FunctionEntry:
    label: str                              # entry label in CFG (also the block label)
    params: tuple[str, ...]                 # parameter names from FunctionRegistry

    def entry_block(self, cfg: CFG) -> BasicBlock:
        return cfg.blocks[self.label]
```

### FlowEndpoint — what flows where

```python
@dataclass(frozen=True)
class VariableEndpoint:
    name: str
    definition: Definition                  # links back to intraprocedural Definition
    # Use NO_DEFINITION sentinel when no intraprocedural Definition exists (e.g., function params)

@dataclass(frozen=True)
class FieldEndpoint:
    base: VariableEndpoint                  # the object variable (traceable)
    field: str
    location: InstructionLocation           # the STORE_FIELD/LOAD_FIELD location

@dataclass(frozen=True)
class ReturnEndpoint:
    function: FunctionEntry                 # which function returns
    location: InstructionLocation           # the RETURN instruction location

FlowEndpoint = VariableEndpoint | FieldEndpoint | ReturnEndpoint
```

### CallSite — a specific call instruction

```python
@dataclass(frozen=True)
class CallSite:
    caller: FunctionEntry                   # function containing this call
    location: InstructionLocation           # block_label + instruction_index
    callees: frozenset[FunctionEntry]       # resolved targets (CHA → multiple for CALL_METHOD)
    arg_operands: tuple[str, ...]           # actual argument register names

    def instruction(self, cfg: CFG) -> IRInstruction:
        return self.location.resolve(cfg)

    def block(self, cfg: CFG) -> BasicBlock:
        return cfg.blocks[self.location.block_label]
```

### CallContext — 1-CFA context key

```python
@dataclass(frozen=True)
class CallContext:
    site: CallSite                          # ROOT_CONTEXT for top-level (no caller)

ROOT_CONTEXT = CallContext(site=CallSite(
    caller=FunctionEntry(label="__root__", params=()),
    location=NO_INSTRUCTION_LOC,
    callees=frozenset(),
    arg_operands=(),
))
```

### FunctionSummary — how data flows through a function

```python
@dataclass(frozen=True)
class FunctionSummary:
    function: FunctionEntry
    context: CallContext
    flows: frozenset[tuple[FlowEndpoint, FlowEndpoint]]  # (source → sink) pairs
```

### CallGraph

```python
@dataclass(frozen=True)
class CallGraph:
    functions: frozenset[FunctionEntry]     # all functions in the program
    call_sites: frozenset[CallSite]         # all call sites (frozenset, not tuple — unordered)
```

### InterproceduralResult — the complete analysis output

```python
@dataclass(frozen=True)
class SummaryKey:
    function: FunctionEntry
    context: CallContext

@dataclass(frozen=True)
class InterproceduralResult:
    call_graph: CallGraph
    summaries: dict[SummaryKey, FunctionSummary]
    whole_program_graph: dict[FlowEndpoint, frozenset[FlowEndpoint]]  # transitive
    raw_program_graph: dict[FlowEndpoint, frozenset[FlowEndpoint]]    # direct edges only
```

## Architecture

### Phase 1: Call Graph Construction

Scan all CFG blocks for `CALL_FUNCTION`, `CALL_METHOD`, `CALL_UNKNOWN` instructions.

| Opcode | Resolution | Result |
|--------|-----------|--------|
| `CALL_FUNCTION` | Direct — operand is function label | Single callee FunctionEntry |
| `CALL_METHOD` | CHA — find all classes defining the method via `FunctionRegistry.class_methods` | Multiple callee FunctionEntries |
| `CALL_UNKNOWN` | Unresolved — no callee | Opaque (no interprocedural flow) |

Build `FunctionEntry` for every function in the registry, then scan for calls.

### Phase 2: Summary Computation (1-CFA)

For each function, at each call site that invokes it (1-CFA = one analysis per call site):

1. **Extract the function's sub-CFG** — blocks reachable from entry label to RETURN
2. **Run existing `analyze(sub_cfg)`** — produces `DataflowResult` with def-use chains and dependency graph
3. **Extract field flows** (separate pass, does NOT modify `dataflow.py`):
   - Scan instructions for `STORE_FIELD obj field val` → `FieldEndpoint` as sink
   - Scan instructions for `LOAD_FIELD obj field` → `FieldEndpoint` as source
   - Trace through the intraprocedural dependency graph to connect field endpoints to parameter endpoints
4. **Build `FunctionSummary`** — all `(source → sink)` flow pairs

### Phase 3: Interprocedural Propagation (Whole-Program Fixpoint)

1. Compute SCCs (strongly connected components) of call graph
2. Process SCCs in reverse topological order (leaves first)
3. For each SCC, iterate until summaries stabilize:
   - For each function in SCC, for each call site calling it:
     - Map actual arguments → formal parameters
     - Apply callee summary: substitute formal endpoints with caller's actual endpoints
     - For `FieldEndpoint`: base variable is substituted, field name stays
     - Inject propagated flows into caller's dependency graph
   - If any summary changed → re-iterate the SCC
4. Safety bound: `DATAFLOW_MAX_ITERATIONS` prevents non-termination on pathological recursion
5. After fixpoint: build whole-program graph (raw + transitive closure)

### Phase 4: Query Interface

All queries operate on the pre-computed `InterproceduralResult`:

**Impact analysis:**
```python
def impact_of(result, target: FlowEndpoint) -> frozenset[FlowEndpoint]
```
Forward transitive closure from target. O(1) dict lookup.

**Taint tracking:**
```python
def taint_reaches(result, source: FlowEndpoint, sink: FlowEndpoint) -> bool
def taint_path(result, source: FlowEndpoint, sink: FlowEndpoint) -> tuple[FlowEndpoint, ...] | None
```
Reachability check (O(1)) + witness path via BFS on raw graph. Each endpoint traces back to its `IRInstruction`.

**Program slicing:**
```python
def backward_slice(result, target: FlowEndpoint) -> frozenset[IRInstruction]
def forward_slice(result, target: FlowEndpoint) -> frozenset[IRInstruction]
```
Walk raw graph backward/forward, collect instructions from each endpoint's traceability chain.

## Module Structure

```
interpreter/
  dataflow.py                          ← UNCHANGED (existing intraprocedural analysis)
  interprocedural/
    __init__.py
    types.py                           ← FlowEndpoint, FunctionEntry, CallSite, CallContext,
                                         FunctionSummary, CallGraph, InterproceduralResult (~80 lines)
    call_graph.py                      ← build_call_graph, build_function_entries, CHA resolution (~150 lines)
    summaries.py                       ← build_summary, extract field flows from DataflowResult (~200 lines)
    propagation.py                     ← apply_summary, whole_program_fixpoint, SCC computation (~250 lines)
    queries.py                         ← impact_of, taint_reaches, taint_path, backward_slice,
                                         forward_slice (~100 lines)
    analyze.py                         ← analyze_interprocedural() entry point (~50 lines)
```

### Dependencies

```
ir.py, cfg_types.py, constants.py
    ↑
dataflow.py (UNCHANGED)
    ↑
interprocedural/types.py ← ir.py, cfg_types.py, dataflow.py (Definition)
    ↑
interprocedural/call_graph.py ← types.py, cfg_types.py, registry.py
    ↑
interprocedural/summaries.py ← types.py, dataflow.py (analyze)
    ↑
interprocedural/propagation.py ← types.py, summaries.py, call_graph.py
    ↑
interprocedural/queries.py ← types.py
    ↑
interprocedural/analyze.py ← all above
```

No dependency on VM, executor, frontends, or backends. Pure analysis pass over CFG + FunctionRegistry.

### Entry Point

```python
def analyze_interprocedural(
    cfg: CFG,
    registry: FunctionRegistry,
) -> InterproceduralResult:
    """Build call graph, compute 1-CFA summaries, produce whole-program dependency graph."""
```

Two inputs (same as `execute_cfg`), one output. Callers don't need to know about internal phases.

### Modification to Existing Code

**`interpreter/dataflow.py` — UNCHANGED.** Field flow extraction is a separate pass in
`interprocedural/summaries.py`, not an extension of the intraprocedural analysis.

### Sub-CFG Extraction

To analyze a single function, extract its sub-CFG: starting from the function's entry label,
collect all blocks reachable before hitting a RETURN or exiting the function's label space.
The registry's `func_params` maps function labels to entry points; the CFG's block successors
provide reachability. Build a `CFG(blocks=sub_blocks, entry=function_label)` and pass to
the existing `analyze()`.

## Known Limitations

### CALL_FUNCTION with dynamic targets
`CALL_FUNCTION` where `operands[0]` is a variable holding a `FuncRef` (rather than a literal
function label) cannot be statically resolved without points-to analysis. These are treated
as `CALL_UNKNOWN` (opaque). This affects higher-order function patterns (callbacks, function
arguments).

### No alias analysis
If `a = b` (aliasing), then `a.field = x` does NOT propagate to `b.field`. Different
variables pointing to the same heap object are treated independently. Acknowledged as a
false-negative source — same limitation as existing intraprocedural analysis.

### Constructor calls
`NEW_OBJECT` + class body execution implicitly calls `__init__`. The call graph builder
must recognize these as call sites to the constructor's entry label (available in
`FunctionRegistry.func_params` as `"ClassName___init__"` or similar). Test coverage
required for this pattern.

### SpreadArguments
`SpreadArguments(register)` operands in CALL_* instructions are not plain register names.
The summary builder must detect `SpreadArguments` and either expand them (if the array
is statically known) or treat the spread as a single opaque argument flowing to all
remaining parameters.

### Module-level (top-level) code
Code outside any function (e.g., Python module-level assignments, COBOL PROCEDURE DIVISION)
is analyzed as a synthetic "main" function with no parameters. The call graph builder creates
a `FunctionEntry(label="__module__", params=())` for it.

### CHA over-approximation
Class hierarchy analysis may include callees that are unreachable at runtime (e.g., a method
on a class that is never instantiated). This produces false positives in the dependency graph —
acceptable for impact analysis ("what *might* be affected") but may cause noise for taint tracking.

## Testing Strategy

### Unit Tests

Each module gets focused unit tests with hand-crafted IR programs:

**`test_interprocedural_types.py`:**
- FunctionEntry, CallSite, FlowEndpoint construction and equality
- Frozen dataclass immutability
- Traceability: every endpoint navigates back to its IR objects

**`test_call_graph.py`:**
- Direct calls (`CALL_FUNCTION`) → single callee
- Method calls (`CALL_METHOD`) → CHA resolves to multiple callees
- Unknown calls → no callees, opaque
- Recursive calls → caller == callee in edges
- No calls → empty call graph
- Call site arg_operands correctly captured

**`test_summaries.py`:**
- Simple pass-through: `def f(x): return x` → `(Variable(x), Return)`
- Field write: `def f(obj, val): obj.name = val` → `(Variable(val), FieldEndpoint(obj, "name"))`
- Field read: `def f(obj): return obj.name` → `(FieldEndpoint(obj, "name"), Return)`
- No params, no return → empty summary
- Multiple params flowing to return
- Field read feeding field write → transitive through function body
- 1-CFA: same function called at 2 sites → 2 distinct summaries

**`test_propagation.py`:**
- Single call site, substitute actual→formal
- Field endpoint base substitution (formal base → actual base, field preserved)
- Two-level call chain: A calls B calls C → transitive flow
- Recursive function → fixpoint converges
- Mutual recursion (SCC) → fixpoint converges
- CALL_METHOD with CHA → flows propagated through all resolved callees
- Safety bound: pathological recursion terminates

**`test_queries.py`:**
- impact_of: variable → all downstream variables and fields
- taint_reaches: true positive, true negative
- taint_path: returns witness chain with correct instructions
- backward_slice: returns all contributing instructions
- forward_slice: returns all affected instructions
- Cross-function flows appear in slice results

### Integration Tests

End-to-end tests using real language programs through the full pipeline:

**`test_interprocedural_integration.py`:**
- Python program with function calls → verify interprocedural dependencies
- Multi-function chain (A→B→C) → transitive flow detected
- OOP field flow: constructor sets field, method reads field → connected
- Recursive function → summary converges, self-dependency detected
- Cross-language: same IR patterns work regardless of source language
- Taint tracking: user input through 3 function calls to output → witness path correct
- Impact analysis: change in deep utility function → all callers affected

### TDD Approach

For each module:
1. Write failing unit tests first (define expected behavior)
2. Implement minimal code to pass
3. Refactor if needed
4. Integration tests after all modules are wired

## Future Extensions (designed for, not built)

- **Type-based dispatch refinement** — narrow CHA results using TypeEnvironment
- **k-CFA (k>1)** — `CallContext` already supports chaining via `site.caller`
- **Deeper field access paths** — `FieldEndpoint` base could be another `FieldEndpoint` for `obj.inner.value`
- **Must-analysis variant** — intersection instead of union at merge points
- **Incremental re-analysis** — invalidate only affected summaries when code changes

## References

- Existing design: `docs/notes-on-dataflow-design.md` (789 lines)
- ADR-009: Iterative Dataflow Analysis
- CodeQL store/read content model: `github.com/github/codeql/blob/main/docs/ql-libraries/dataflow/dataflow.md`
- FlowDroid access paths: Arzt et al., "FlowDroid: Precise Context, Flow, Field, Object-sensitive and Lifecycle-aware Taint Analysis for Android Apps" (PLDI 2014)
- IFDS/IDE framework: Reps, Horwitz, Sagiv, "Precise Interprocedural Dataflow Analysis via Graph Reachability" (POPL 1995)
