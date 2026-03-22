# Interprocedural Dataflow Analysis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Whole-program interprocedural dataflow analysis with call graph, 1-CFA function summaries, depth-1 field-sensitive heap tracking, and query interface for impact/taint/slicing.

**Architecture:** 6 new modules in `interpreter/interprocedural/` building on existing `dataflow.py`. Pure analysis over CFG + FunctionRegistry — no VM dependency. Each phase is independently testable. TDD throughout.

**Tech Stack:** Python 3.13+, pytest, existing dataflow/CFG/IR infrastructure

**Spec:** `docs/superpowers/specs/2026-03-22-interprocedural-dataflow-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `interpreter/interprocedural/__init__.py` | Create | Package init |
| `interpreter/interprocedural/types.py` | Create | All data types: FlowEndpoint, FunctionEntry, CallSite, CallContext, FunctionSummary, CallGraph, InterproceduralResult (~100 lines) |
| `interpreter/interprocedural/call_graph.py` | Create | build_call_graph, build_function_entries, CHA resolution (~150 lines) |
| `interpreter/interprocedural/summaries.py` | Create | build_summary, extract field flows (~200 lines) |
| `interpreter/interprocedural/propagation.py` | Create | apply_summary, whole_program_fixpoint, SCC computation (~250 lines) |
| `interpreter/interprocedural/queries.py` | Create | impact_of, taint_reaches, taint_path, backward_slice, forward_slice (~100 lines) |
| `interpreter/interprocedural/analyze.py` | Create | analyze_interprocedural entry point (~50 lines) |
| `tests/unit/test_interprocedural_types.py` | Create | Type construction, equality, hashing tests |
| `tests/unit/test_call_graph.py` | Create | Call graph construction tests |
| `tests/unit/test_summaries.py` | Create | Function summary extraction tests |
| `tests/unit/test_propagation.py` | Create | Interprocedural propagation tests |
| `tests/unit/test_queries.py` | Create | Query interface tests |
| `tests/integration/test_interprocedural_integration.py` | Create | End-to-end tests through real language programs |

---

### Task 1: Data Types (`types.py`)

**Files:**
- Create: `interpreter/interprocedural/__init__.py`
- Create: `interpreter/interprocedural/types.py`
- Create: `tests/unit/test_interprocedural_types.py`

**Reference:**
- Existing `Definition` in `interpreter/dataflow.py:40-52` (custom `__hash__` pattern)
- Spec data model section

- [ ] **Step 1: Write failing unit tests for all data types**

Test cases:
- `InstructionLocation` — construction, equality, hashing, `resolve(cfg)` returns correct instruction
- `NO_INSTRUCTION_LOC` — sentinel has empty label and -1 index
- `FunctionEntry` — construction, equality, hashing, `entry_block(cfg)` returns correct block
- `VariableEndpoint` — construction, equality, hashing, name preserved
- `FieldEndpoint` — construction with base VariableEndpoint, field name, location
- `ReturnEndpoint` — construction with function and location
- `CallSite` — construction, caller/callees/arg_operands, `instruction(cfg)` resolves
- `CallContext` — construction, `ROOT_CONTEXT` sentinel
- `FunctionSummary` — construction with flows frozenset
- `SummaryKey` — construction, hashing (used as dict key)
- `CallGraph` — construction with functions and call_sites frozensets
- `InterproceduralResult` — construction
- All types usable in sets and as dict keys (hashability)

Build test IR programs using hand-crafted `IRInstruction` and `BasicBlock` objects — same pattern as `tests/unit/test_dataflow.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_interprocedural_types.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement all data types**

Create `interpreter/interprocedural/__init__.py` (empty).

Create `interpreter/interprocedural/types.py` with all frozen dataclasses per spec. Key implementation details:
- All types use `@dataclass(frozen=True)`
- Types containing `IRInstruction` (indirectly via `Definition`) use custom `__hash__` excluding unhashable fields — follow the `Definition` pattern from `dataflow.py:49-50`
- `InstructionLocation.resolve(cfg)` does `cfg.blocks[self.block_label].instructions[self.instruction_index]`
- `NO_INSTRUCTION_LOC`, `ROOT_CONTEXT` defined as module-level sentinels
- `NO_DEFINITION` sentinel: `Definition(variable="", block_label="", instruction_index=-1, instruction=...)`
  - Needs a dummy `IRInstruction` — create `_SENTINEL_INSTRUCTION = IRInstruction(opcode=Opcode.CONST, operands=[], result_reg="")`

- [ ] **Step 4: Run tests, format, commit**

```bash
git commit -m "feat(interprocedural): add data types — FlowEndpoint, CallSite, FunctionSummary, etc."
```

---

### Task 2: Call Graph Construction (`call_graph.py`)

**Files:**
- Create: `interpreter/interprocedural/call_graph.py`
- Create: `tests/unit/test_call_graph.py`

**Reference:**
- `interpreter/registry.py` — FunctionRegistry structure (func_params, class_methods)
- `interpreter/ir.py` — Opcode.CALL_FUNCTION, CALL_METHOD, CALL_UNKNOWN
- `interpreter/constants.py` — FUNC_LABEL_PREFIX, PARAM_PREFIX

- [ ] **Step 1: Write failing unit tests**

Build hand-crafted CFGs with CALL_* instructions and verify call graph construction.

Test cases:

**Direct calls:**
- Program with `CALL_FUNCTION "func__foo"` → CallGraph has edge from caller to `foo`
- Multiple calls in same function → multiple CallSite objects
- Call to non-existent function → callee set is empty (no crash)

**Method calls (CHA):**
- `CALL_METHOD obj "speak"` where registry has Dog.speak and Cat.speak → CallSite.callees has 2 entries
- `CALL_METHOD obj "unique_method"` where only one class has it → 1 callee

**Unknown calls:**
- `CALL_UNKNOWN` → CallSite.callees is empty frozenset

**Edge cases:**
- Recursive call (function calls itself) → caller == callee
- No calls in program → CallGraph with functions but no call_sites
- Module-level code (no function label prefix) → synthetic `__module__` FunctionEntry

**Arg operand extraction:**
- `CALL_FUNCTION "func__foo" %1 %2` → arg_operands = ("%1", "%2")
- `CALL_METHOD %0 "bar" %1` → arg_operands properly extracted (skip object register)

Each test builds a CFG + FunctionRegistry by hand, calls `build_call_graph(cfg, registry)`, asserts on the resulting `CallGraph`.

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement call graph construction**

```python
# interpreter/interprocedural/call_graph.py

def build_function_entries(cfg: CFG, registry: FunctionRegistry) -> dict[str, FunctionEntry]:
    """Build FunctionEntry for every registered function."""

def _resolve_call_targets(
    inst: IRInstruction, function_entries: dict[str, FunctionEntry], registry: FunctionRegistry
) -> frozenset[FunctionEntry]:
    """Resolve CALL_* instruction to target FunctionEntries."""

def build_call_graph(cfg: CFG, registry: FunctionRegistry) -> CallGraph:
    """Scan all CFG blocks for CALL_* instructions, resolve targets, return CallGraph."""
```

Key logic:
- `build_function_entries`: iterate `registry.func_params`, create `FunctionEntry(label, params)` for each
- `_resolve_call_targets`:
  - `CALL_FUNCTION`: look up `operands[0]` in function_entries dict
  - `CALL_METHOD`: look up method name across all classes in `registry.class_methods`, collect all matching function labels
  - `CALL_UNKNOWN`: return empty frozenset
- `build_call_graph`: walk all blocks/instructions, create `CallSite` for each CALL_*, collect into `CallGraph`

- [ ] **Step 4: Run tests, format, commit**

```bash
git commit -m "feat(interprocedural): add call graph construction with CHA"
```

---

### Task 3: Function Summaries (`summaries.py`)

**Files:**
- Create: `interpreter/interprocedural/summaries.py`
- Create: `tests/unit/test_summaries.py`

**Reference:**
- `interpreter/dataflow.py` — `analyze()` function, `DataflowResult`
- Spec Section 3 (summary computation)

- [ ] **Step 1: Write failing unit tests**

Build hand-crafted sub-CFGs representing single functions. Run `build_summary` and verify FlowEndpoint pairs.

Test cases:

**Pass-through:**
- `def f(x): return x` → summary contains `(VariableEndpoint("x"), ReturnEndpoint(f))`

**Computation:**
- `def f(x, y): return x + y` → `(Variable("x"), Return)` and `(Variable("y"), Return)`

**Field write:**
- `def f(obj, val): STORE_FIELD obj "name" val` → `(Variable("val"), FieldEndpoint(obj, "name"))`

**Field read:**
- `def f(obj): LOAD_FIELD obj "name"; RETURN result` → `(FieldEndpoint(obj, "name"), Return)`

**Field read → field write (transitive through body):**
- `def f(obj): val = LOAD_FIELD obj "x"; STORE_FIELD obj "y" val` → `(FieldEndpoint(obj, "x"), FieldEndpoint(obj, "y"))`

**No params, no return:**
- `def f(): CONST 42; RETURN` → flows is empty (no parameter-connected flows)

**Multiple params to return:**
- `def f(a, b, c): return a + b` → `(Variable("a"), Return)`, `(Variable("b"), Return)`, NOT `(Variable("c"), Return)`

**1-CFA context:**
- Same function analyzed with two different `CallContext` objects → two different `FunctionSummary` instances (distinct context field)

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement summary builder**

```python
# interpreter/interprocedural/summaries.py

def extract_sub_cfg(cfg: CFG, function_entry: FunctionEntry) -> CFG:
    """Extract the sub-CFG for a single function (entry label → RETURN)."""

def _extract_field_flows(
    sub_cfg: CFG, params: tuple[str, ...], dataflow_result: DataflowResult
) -> frozenset[tuple[FlowEndpoint, FlowEndpoint]]:
    """Scan instructions for STORE_FIELD/LOAD_FIELD, trace to params via dependency graph."""

def build_summary(
    cfg: CFG,
    function_entry: FunctionEntry,
    context: CallContext,
) -> FunctionSummary:
    """Run intraprocedural analyze() on function's sub-CFG, extract FlowEndpoint pairs."""
```

Key logic:
- `extract_sub_cfg`: BFS from entry label, stop at RETURN or blocks outside function's label space
- `build_summary`:
  1. `extract_sub_cfg` → sub_cfg
  2. `analyze(sub_cfg)` → DataflowResult (existing intraprocedural analysis)
  3. For each param: trace through `dependency_graph` to find if it reaches RETURN instruction → `(VariableEndpoint, ReturnEndpoint)`
  4. `_extract_field_flows`: scan for STORE_FIELD/LOAD_FIELD, trace field endpoints to params
  5. Combine all flows into `FunctionSummary`

- [ ] **Step 4: Run tests, format, commit**

```bash
git commit -m "feat(interprocedural): add function summary extraction"
```

---

### Task 4: Interprocedural Propagation (`propagation.py`)

**Files:**
- Create: `interpreter/interprocedural/propagation.py`
- Create: `tests/unit/test_propagation.py`

**Reference:**
- Spec Section 4 (propagation)
- Tarjan's SCC algorithm or Kosaraju's

- [ ] **Step 1: Write failing unit tests**

Test cases:

**Single call site substitution:**
- Caller has `x = 5; result = call f(x)`. Summary of f: `(Variable("param"), Return)`. After propagation: `Variable("x") → Variable("result")` in caller's graph.

**Field endpoint substitution:**
- Summary: `(Variable("param_obj"), FieldEndpoint(param_obj, "name"))`. Caller passes `my_obj`. Propagated: `Variable("my_obj") → FieldEndpoint(my_obj, "name")`.

**Two-level chain:**
- A calls B, B calls C. Flow from A's arg through B and C back to A's result.

**Recursive function:**
- f calls f → fixpoint converges (summary stabilizes after ≤2 iterations)

**Mutual recursion (SCC):**
- f calls g, g calls f → SCC detected, both summaries computed together until stable

**CHA multiple callees:**
- call_method with 2 callees → flows from BOTH callees propagated

**Safety bound:**
- Pathological recursion that would iterate forever → terminates at DATAFLOW_MAX_ITERATIONS

**Whole-program graph construction:**
- After propagation, verify `raw_program_graph` has direct edges and `whole_program_graph` has transitive edges

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement propagation**

```python
# interpreter/interprocedural/propagation.py

def compute_sccs(call_graph: CallGraph) -> list[frozenset[FunctionEntry]]:
    """Tarjan's algorithm: strongly connected components in reverse topological order."""

def apply_summary_at_call_site(
    call_site: CallSite,
    summary: FunctionSummary,
) -> frozenset[tuple[FlowEndpoint, FlowEndpoint]]:
    """Substitute formal params with actual args in summary flows."""

def whole_program_fixpoint(
    cfg: CFG,
    call_graph: CallGraph,
    registry: FunctionRegistry,
) -> dict[SummaryKey, FunctionSummary]:
    """Compute all summaries with 1-CFA. Process SCCs bottom-up, iterate until stable."""

def build_whole_program_graph(
    summaries: dict[SummaryKey, FunctionSummary],
    call_graph: CallGraph,
) -> tuple[dict[FlowEndpoint, frozenset[FlowEndpoint]], dict[FlowEndpoint, frozenset[FlowEndpoint]]]:
    """Build raw + transitive whole-program dependency graphs."""
```

Key logic:
- `compute_sccs`: Tarjan's or Kosaraju's. Return list in reverse topological order (leaves first).
- `apply_summary_at_call_site`: zip `call_site.arg_operands` with `summary.function.params`, substitute `VariableEndpoint` names. For `FieldEndpoint`, substitute base but keep field name.
- `whole_program_fixpoint`:
  1. For each SCC in reverse topo order:
     - For each function in SCC, for each call site calling it:
       - Build summary with `build_summary(cfg, function, CallContext(site=call_site))`
     - If any summary changed from previous iteration → re-iterate SCC
  2. Cap at `DATAFLOW_MAX_ITERATIONS`
- `build_whole_program_graph`: apply all summaries at all call sites, collect all propagated edges, compute transitive closure

- [ ] **Step 4: Run tests, format, commit**

```bash
git commit -m "feat(interprocedural): add whole-program propagation with SCC fixpoint"
```

---

### Task 5: Query Interface (`queries.py`)

**Files:**
- Create: `interpreter/interprocedural/queries.py`
- Create: `tests/unit/test_queries.py`

- [ ] **Step 1: Write failing unit tests**

Build an `InterproceduralResult` with known graph edges and verify queries.

Test cases:

**Impact analysis:**
- `impact_of(Variable("x"))` → returns all downstream endpoints
- `impact_of(FieldEndpoint(obj, "name"))` → returns endpoints affected by field
- `impact_of` on endpoint with no outgoing edges → empty frozenset

**Taint tracking:**
- `taint_reaches(source, sink)` where path exists → True
- `taint_reaches(source, sink)` where no path → False
- `taint_path(source, sink)` → returns witness chain of FlowEndpoints
- `taint_path` where no path → empty tuple (not None — project conventions)
- Witness path traces back to IRInstructions via endpoint locations

**Program slicing:**
- `backward_slice(Variable("result"))` → all instructions contributing to result
- `forward_slice(Variable("input"))` → all instructions affected by input
- Cross-function instructions appear in slice results
- Slicing on endpoint with no connections → empty frozenset

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement query functions**

```python
# interpreter/interprocedural/queries.py

def impact_of(result: InterproceduralResult, target: FlowEndpoint) -> frozenset[FlowEndpoint]:
    """Forward transitive closure from target."""

def taint_reaches(result: InterproceduralResult, source: FlowEndpoint, sink: FlowEndpoint) -> bool:
    """Does source flow to sink?"""

def taint_path(
    result: InterproceduralResult, source: FlowEndpoint, sink: FlowEndpoint
) -> tuple[FlowEndpoint, ...]:
    """Witness path from source to sink via BFS on raw graph. Empty tuple if unreachable."""

def backward_slice(result: InterproceduralResult, target: FlowEndpoint) -> frozenset[FlowEndpoint]:
    """All endpoints that contribute to target's value."""

def forward_slice(result: InterproceduralResult, target: FlowEndpoint) -> frozenset[FlowEndpoint]:
    """All endpoints affected by target's value."""

def _collect_instructions(endpoints: frozenset[FlowEndpoint]) -> frozenset[InstructionLocation]:
    """Extract InstructionLocations from a set of FlowEndpoints."""
```

- [ ] **Step 4: Run tests, format, commit**

```bash
git commit -m "feat(interprocedural): add query interface — impact, taint, slicing"
```

---

### Task 6: Entry Point + Integration Tests (`analyze.py`)

**Files:**
- Create: `interpreter/interprocedural/analyze.py`
- Create: `tests/integration/test_interprocedural_integration.py`

- [ ] **Step 1: Write integration tests**

End-to-end tests using real language programs through the full pipeline (parse → lower → build_cfg → build_registry → analyze_interprocedural → query).

Test cases:

**Python multi-function chain:**
```python
def add(a, b):
    return a + b

def double(x):
    return add(x, x)

result = double(5)
```
Verify: `impact_of(Variable("x"))` includes the return value of `add` and `result`.

**OOP field flow:**
```python
class Dog:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return self.name

d = Dog("Rex")
g = d.greet()
```
Verify: field flow from constructor arg "name" → `self.name` → return of `greet` → `g`.

**Recursive function:**
```python
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

r = factorial(5)
```
Verify: summary converges, `Variable("n")` has self-dependency.

**Taint tracking:**
```python
def process(data):
    return data.upper()

def output(msg):
    print(msg)

user_input = input()
processed = process(user_input)
output(processed)
```
Verify: `taint_reaches(Variable("user_input"), Variable("msg"))` is True. `taint_path` returns the chain.

**Cross-language (Rust):**
```rust
fn add(a: i32, b: i32) -> i32 { a + b }
fn main() { let r = add(3, 4); }
```
Verify: same analysis works on Rust IR as on Python IR.

- [ ] **Step 2: Implement entry point**

```python
# interpreter/interprocedural/analyze.py

def analyze_interprocedural(
    cfg: CFG,
    registry: FunctionRegistry,
) -> InterproceduralResult:
    """Build call graph, compute 1-CFA summaries, produce whole-program dependency graph."""
    call_graph = build_call_graph(cfg, registry)
    summaries = whole_program_fixpoint(cfg, call_graph, registry)
    raw_graph, transitive_graph = build_whole_program_graph(summaries, call_graph)
    return InterproceduralResult(
        call_graph=call_graph,
        summaries=summaries,
        whole_program_graph=transitive_graph,
        raw_program_graph=raw_graph,
    )
```

- [ ] **Step 3: Run all tests**

Run: `poetry run python -m pytest tests/unit/test_interprocedural_types.py tests/unit/test_call_graph.py tests/unit/test_summaries.py tests/unit/test_propagation.py tests/unit/test_queries.py tests/integration/test_interprocedural_integration.py -v`

Then: `poetry run python -m pytest --tb=short -q`

- [ ] **Step 4: Format and commit**

```bash
poetry run python -m black interpreter/interprocedural/ tests/unit/test_interprocedural_*.py tests/unit/test_call_graph.py tests/unit/test_summaries.py tests/unit/test_propagation.py tests/unit/test_queries.py tests/integration/test_interprocedural_integration.py
git commit -m "feat(interprocedural): add analyze_interprocedural entry point + integration tests"
```

---

### Task 7: ADR and Documentation

**Files:**
- Modify: `docs/architectural-design-decisions.md`
- Modify: `docs/notes-on-dataflow-design.md` (add interprocedural section)
- Modify: `README.md`

- [ ] **Step 1: Add ADR**

```markdown
## ADR-NNN: Interprocedural Dataflow Analysis (2026-03-22)

**Status:** Accepted
**Issue:** red-dragon-j7f4

Whole-program interprocedural dataflow analysis extending the existing
intraprocedural infrastructure (ADR-009). 4 phases: call graph (CHA),
function summaries (1-CFA), whole-program fixpoint propagation,
query interface (impact/taint/slicing).

Depth-1 field-sensitive (CodeQL-style store/read). All types hashable
via InstructionLocation indirection. Pure analysis over CFG + FunctionRegistry.

**Decision:** 1-CFA context sensitivity with CHA for virtual dispatch.
Whole-program upfront computation. Field flows extracted in separate pass
(dataflow.py unchanged). Summaries composed at call sites via argument mapping.
```

- [ ] **Step 2: Update dataflow design doc**

Add interprocedural section to `docs/notes-on-dataflow-design.md`.

- [ ] **Step 3: Close issue, run tests, commit**

Run: `bd close red-dragon-j7f4`

```bash
git commit -m "docs: ADR for interprocedural dataflow analysis (red-dragon-j7f4)"
```
