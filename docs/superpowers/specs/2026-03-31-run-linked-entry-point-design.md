# Design: EntryPoint-Based Execution for LinkedProgram

**Date:** 2026-03-31
**Issue:** red-dragon-ug4v

## Problem

LinkedProgram execution from `compile_project()` lacks entry point support. The consumer has no way to specify which function to dispatch into after module preamble completion. All execution steps are consumed by the preamble (CONST+DECL_VAR registrations for all classes and functions across all modules), leaving no budget for actual function execution.

Additionally, `compile_project()` and `compile_directory()` overlap in purpose, with `compile_project()` performing unnecessary BFS import-tracing that adds complexity without meaningful benefit — preamble ordering is irrelevant since all modules just register symbols.

The current `entry_point: str = ""` parameter on `run()` encodes execution mode implicitly: empty string means "run top-to-bottom," non-empty means "dispatch into function." This is a stringly-typed convention that should be an explicit, typed choice.

## Design

### 0. New Type: `EntryPoint`

A single type that explicitly encodes how to enter a program for execution. No strings, no None, no implicit defaults.

```python
@dataclass(frozen=True)
class EntryPoint:
    """Specifies how to enter a program for execution.

    Two modes:
    - top_level(): execute module code top-to-bottom (preamble + top-level statements)
    - function(predicate): run preamble, then dispatch into the single function matching the predicate
    """

    _predicate: Callable[[FuncRef], bool] | None  # None = top-level mode
    _is_top_level: bool

    @staticmethod
    def function(predicate: Callable[[FuncRef], bool]) -> EntryPoint:
        return EntryPoint(_predicate=predicate, _is_top_level=False)

    @staticmethod
    def top_level() -> EntryPoint:
        return EntryPoint(_predicate=None, _is_top_level=True)
```

Usage:

```python
# Dispatch into a specific function
run(source, language=Language.PYTHON, entry_point=EntryPoint.function(lambda f: f.name == FuncName("main")))

# Run module top-to-bottom
run(source, language=Language.PYTHON, entry_point=EntryPoint.top_level())
```

### 1. Compilation: Consolidate to `compile_directory()`

- **Remove `compile_project()` orchestrator.** The BFS import-tracing machinery provides no value for compilation — preamble order doesn't affect correctness since all modules just register symbols via CONST+DECL_VAR.
- **Simplify `compile_directory()` signature:** `compile_directory(directory: Path, language: Language) -> LinkedProgram`. Drop the `entry_file` parameter — the consumer controls entry point at execution time, not compilation time.
- **Drop `entry_module` from `LinkedProgram`.** No longer meaningful when the consumer picks the entry point post-compilation.
- **Keep reusable utilities:** `ImportResolver`, `topological_sort`, `extract_imports` remain available for analysis use cases (dependency visualization, unused module detection, etc.) but are no longer called from the compilation path.

### 2. Execution: `run_linked()` with `EntryPoint`

**New function: `run_linked()`**

```python
def run_linked(
    linked: LinkedProgram,
    entry_point: EntryPoint,
    max_steps: int = 100,
    verbose: bool = False,
    backend: str = LLMProvider.CLAUDE,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
) -> VMState:
```

- Builds execution strategies from `linked.merged_registry` + symbol tables.
- If `entry_point` is top-level: execute from `merged_cfg.entry` (module start), no function dispatch.
- If `entry_point` is function: apply predicate against registry's `FuncRef`s, expect exactly one match (raise if zero or multiple), two-phase execution (preamble then dispatch into matched function).

**Refactored `run()`**

- `entry_point` parameter changes from `str` to `EntryPoint`. Required, no default.
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

**145 call sites across 74 files.** Two categories:

1. **26 sites already passing `entry_point="main"` etc.** — change to `EntryPoint.function(lambda f: f.name == FuncName("main"))`.
2. **~119 sites passing no `entry_point`** — change to `EntryPoint.top_level()`.

```python
# Before (with entry_point)
run(source, language=Language.PYTHON, entry_point="main")

# After (with entry_point)
run(source, language=Language.PYTHON, entry_point=EntryPoint.function(lambda f: f.name == FuncName("main")))

# Before (no entry_point — implicitly ran from module start)
run(source, language=Language.PYTHON)

# After (explicitly run top-to-bottom)
run(source, language=Language.PYTHON, entry_point=EntryPoint.top_level())
```

### 4. Testing

**Unit tests:**
- `EntryPoint.function()` and `EntryPoint.top_level()` construction
- `LinkedProgram.entry_points()` with various predicates
- `run_linked()` predicate matching (zero matches raises, multiple matches raises, single match succeeds)
- `run_linked()` with `EntryPoint.top_level()` runs preamble only
- Single-module `LinkedProgram` construction from `run()` path

**Integration tests:**
- All 16 frontends get multi-module `compile_directory() -> run_linked()` integration tests
- Each frontend is a **separate Beads issue** for incremental work
- Each test: multi-file project in `tmp_path`, `compile_directory()`, `run_linked()` with `EntryPoint.function(...)`, concrete value assertions
- If a frontend's import resolution doesn't support multi-module yet, write the test with correct assertions and `xfail` with the issue ID

**Frontends (16 issues):**
Python, JavaScript, TypeScript, Java, Go, Kotlin, C#, Ruby, PHP, Lua, Rust, C, C++, Scala, Pascal, COBOL

### 5. ADR Update

Document in `docs/architectural-design-decisions.md`:
- Consolidation of `compile_project()` and `compile_directory()` into a single compilation entry point
- Rationale: BFS import-tracing adds complexity without benefit; preamble ordering doesn't affect correctness
- `EntryPoint` type replacing stringly-typed entry point selection
- Predicate-based function matching over string name matching
- `LinkedProgram` as the universal execution unit (single-source and multi-module)

## Components Changed

| Component | Change |
|---|---|
| `EntryPoint` (new, project/types.py) | New type: `function(predicate)` and `top_level()` factory methods |
| `LinkedProgram` (project/types.py) | Drop `entry_module`, add `entry_points(predicate)` |
| `compile_directory()` (project/compiler.py) | Drop `entry_file` param |
| `compile_project()` (project/compiler.py) | Remove |
| `run()` (run.py) | `entry_point: str` -> `EntryPoint`, build single-module LinkedProgram, delegate to `run_linked()` |
| `run_linked()` (run.py) | New function: LinkedProgram + EntryPoint -> VMState |
| 145 call sites (74 files) | String/missing entry points -> `EntryPoint.function(...)` or `EntryPoint.top_level()` |
| ADRs | Document consolidation and rationale |
| Integration tests | 16 new per-frontend multi-module test files |
