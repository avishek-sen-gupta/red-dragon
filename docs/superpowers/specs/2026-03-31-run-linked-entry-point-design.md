# Design: Predicate-Based Entry Point Execution for LinkedProgram

**Date:** 2026-03-31
**Issue:** red-dragon-ug4v

## Problem

LinkedProgram execution from `compile_project()` lacks entry point support. The consumer has no way to specify which function to dispatch into after module preamble completion. All execution steps are consumed by the preamble (CONST+DECL_VAR registrations for all classes and functions across all modules), leaving no budget for actual function execution.

Additionally, `compile_project()` and `compile_directory()` overlap in purpose, with `compile_project()` performing unnecessary BFS import-tracing that adds complexity without meaningful benefit — preamble ordering is irrelevant since all modules just register symbols.

## Design

### 1. Compilation: Consolidate to `compile_directory()`

- **Remove `compile_project()` orchestrator.** The BFS import-tracing machinery provides no value for compilation — preamble order doesn't affect correctness since all modules just register symbols via CONST+DECL_VAR.
- **Simplify `compile_directory()` signature:** `compile_directory(directory: Path, language: Language) -> LinkedProgram`. Drop the `entry_file` parameter — the consumer controls entry point at execution time, not compilation time.
- **Drop `entry_module` from `LinkedProgram`.** No longer meaningful when the consumer picks the entry point post-compilation.
- **Keep reusable utilities:** `ImportResolver`, `topological_sort`, `extract_imports` remain available for analysis use cases (dependency visualization, unused module detection, etc.) but are no longer called from the compilation path.

### 2. Execution: `run_linked()` with Predicate-Based Entry Point

**New function: `run_linked()`**

```python
def run_linked(
    linked: LinkedProgram,
    entry_point: Callable[[FuncRef], bool],
    max_steps: int = 100,
    verbose: bool = False,
    backend: str = LLMProvider.CLAUDE,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
) -> VMState:
```

- Builds execution strategies from `linked.merged_registry` + symbol tables.
- Applies predicate against registry's `FuncRef`s. Expects exactly one match; raises if zero or multiple.
- Two-phase execution: preamble (module entry in merged_cfg) then dispatch into the matched function.

**Refactored `run()`**

- `entry_point` parameter changes from `str` to `Callable[[FuncRef], bool] | None`. When `None` (default), execution runs the full module preamble without dispatching into any function — preserving current no-entry-point behavior.
- Internally: lower source string into a single-module `LinkedProgram`, then delegate to `run_linked()`.
- `LinkedProgram` becomes the universal intermediate between compilation and execution, whether from a single source string or a multi-module directory.

**Discovery: `LinkedProgram.entry_points()`**

```python
def entry_points(
    self, predicate: Callable[[FuncRef], bool] = lambda _: True,
) -> list[FuncRef]:
```

- Query method on `LinkedProgram` for discovering available entry points.
- Returns `list[FuncRef]` — typed, no naked strings.
- Default predicate returns all top-level functions.
- Consumer can inspect candidates before choosing one to pass to `run_linked()`.

### 3. Caller Migration

26 existing call sites change from string entry points to predicates:

```python
# Before
run(source, language=Language.PYTHON, entry_point="main")

# After
run(source, language=Language.PYTHON, entry_point=lambda f: f.name == FuncName("main"))
```

### 4. Testing

**Unit tests:**
- `LinkedProgram.entry_points()` with various predicates
- `run_linked()` predicate matching (zero matches raises, multiple matches raises, single match succeeds)
- Single-module `LinkedProgram` construction from `run()` path

**Integration tests:**
- All 16 frontends get multi-module `compile_directory() -> run_linked()` integration tests
- Each frontend is a **separate Beads issue** for incremental work
- Each test: multi-file project in `tmp_path`, `compile_directory()`, `run_linked()` with predicate, concrete value assertions
- If a frontend's import resolution doesn't support multi-module yet, write the test with correct assertions and `xfail` with the issue ID

**Frontends (16 issues):**
Python, JavaScript, TypeScript, Java, Go, Kotlin, C#, Ruby, PHP, Lua, Rust, C, C++, Scala, Pascal, COBOL

### 5. ADR Update

Document in `docs/architectural-design-decisions.md`:
- Consolidation of `compile_project()` and `compile_directory()` into a single compilation entry point
- Rationale: BFS import-tracing adds complexity without benefit; preamble ordering doesn't affect correctness
- Predicate-based entry point selection over string matching
- `LinkedProgram` as the universal execution unit (single-source and multi-module)

## Components Changed

| Component | Change |
|---|---|
| `LinkedProgram` (project/types.py) | Drop `entry_module`, add `entry_points(predicate)` |
| `compile_directory()` (project/compiler.py) | Drop `entry_file` param |
| `compile_project()` (project/compiler.py) | Remove |
| `run()` (run.py) | `entry_point: str` -> `Callable[[FuncRef], bool]`, build single-module LinkedProgram, delegate to `run_linked()` |
| `run_linked()` (run.py) | New function: LinkedProgram + predicate -> VMState |
| 26 call sites | String entry points -> predicates |
| ADRs | Document consolidation and rationale |
| Integration tests | 16 new per-frontend multi-module test files |
