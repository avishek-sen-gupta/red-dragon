# Multi-File Project TUI Design

## Summary

Extend the RedDragon TUI visualizer to support multi-file projects. A new `project` subcommand accepts a directory, compiles and links all source files via the existing `compile_directory()` pipeline, and presents a two-phase interactive experience: project overview (import graph + entry point selection) followed by module-aware execution debugging.

## CLI Interface

```
poetry run python -m viz project /path/to/dir -l java -s 500
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `directory` | yes | - | Path to project root directory |
| `-l/--language` | yes | - | Source language (no default — multi-file projects are language-explicit) |
| `-s/--max-steps` | no | 300 | Maximum execution steps |

Dispatched via a new `project` entry in `viz/__main__.py`'s subcommand dispatch table.

## Data Model

### ProjectPipelineResult

```python
@dataclass(frozen=True)
class ProjectPipelineResult:
    linked: LinkedProgram
    module_sources: dict[Path, str]       # path -> source text
    module_asts: dict[Path, ASTNode]      # path -> parsed AST
    topo_order: list[Path]                # linking order
    module_ir_ranges: list[tuple[int, int, Path]]  # (start, end, path) in merged_ir
    trace: ExecutionTrace | None          # None until entry point selected
    interprocedural: InterproceduralResult | None
```

- `module_sources` and `module_asts` are pre-loaded at pipeline time (no file I/O in TUI).
- `LinkedProgram` carries `import_graph`, `modules`, `merged_ir`, `merged_cfg`, `merged_registry`.
- `topo_order` is recomputed from `LinkedProgram.import_graph` using `topological_sort()` (already public in `interpreter/project/resolver.py`).
- `module_ir_ranges` maps instruction index ranges in `merged_ir` to source modules.
- `instruction_to_index` maps `id(instruction)` -> index in `merged_ir` for trace step lookups.
- `trace` is `None` initially; populated after entry point selection and execution.

### Module-to-Instruction Mapping

Built post-link in `run_project_pipeline()`. Two data structures:

**1. IR ranges** — built by scanning `merged_ir` for module boundary labels. The linker strips per-module `entry:` labels but emits each module's first namespaced label (e.g., `src.utils.func_helper_0`). We can identify module boundaries by matching label prefixes against the known `module_prefix()` values for each file in topo order:

```python
prefixes = {path: module_prefix(path, project_root) for path in topo_order}
# Walk merged_ir, tracking which prefix the current instructions belong to
ranges: list[tuple[int, int, Path]] = []
current_path = topo_order[0]
current_start = 1  # skip entry label at index 0
for i, inst in enumerate(merged_ir[1:], start=1):
    # detect module transition by label prefix change
    ...
```

**2. Instruction identity map** — since `TraceStep` stores an `instruction: InstructionBase` object reference (not an index), we build a reverse map at pipeline time:

```python
instruction_to_index: dict[int, int] = {id(inst): i for i, inst in enumerate(merged_ir)}
```

During execution, given a trace step: `idx = instruction_to_index[id(step.instruction)]` -> binary search `module_ir_ranges` -> owning module Path.

## Pipeline Function

New function `run_project_pipeline()` in `viz/pipeline.py`:

1. Call `compile_directory(directory, language)` -> `LinkedProgram`
2. Recompute `topo_order` from `linked.import_graph` via `topological_sort(linked.import_graph)`
3. Pre-load `module_sources`: read each module path's text
4. Pre-load `module_asts`: parse each with tree-sitter
5. Build `module_ir_ranges` from merged_ir + topo_order
6. Return `ProjectPipelineResult` with `trace=None`

Execution (trace generation) happens lazily after entry point selection:

```python
def execute_project(result: ProjectPipelineResult, entry_point: EntryPoint, max_steps: int) -> ProjectPipelineResult:
    vm, trace = run_linked_traced(result.linked, entry_point, max_steps)
    interprocedural = analyze_interprocedural(result.linked.merged_cfg, result.linked.merged_registry)
    return dataclasses.replace(result, trace=trace, interprocedural=interprocedural)
```

## run_linked_traced

New function in `interpreter/run.py` that mirrors `run_linked()` but calls `execute_cfg_traced()` instead of `execute_cfg()`. Returns `(VMState, ExecutionTrace)`.

Two-phase execution:
1. **Preamble:** `execute_cfg_traced(merged_cfg, entry_label, ...)` — top-level code of all modules
2. **Dispatch (if function entry point):** resolve function label, then `execute_cfg_traced(merged_cfg, func_label, ..., vm=vm)` — concatenate traces from both phases

No changes to `execute_cfg_traced` itself.

## ProjectApp — Two-Screen Architecture

A single Textual `App` with two screens sharing the `ProjectPipelineResult`:

### Phase 1: ProjectOverviewScreen

Shown at startup. Grid layout: 2 columns.

**Left: ImportGraphPanel** — box-drawing DAG of the import graph.

```
 Import Graph (3 modules, topo order)
----------------------------------------------
  1. constants.py (1 fn, 2 var)
       |
  2. utils.py (2 fn, 1 var) -- imports -- constants.py
       |
  3. main.py (1 fn) ---------- imports -- utils.py
```

- Modules numbered by topological order
- Each node shows: filename (relative to project root), export summary
- Edges drawn with box-drawing characters
- Unresolved imports shown dimmed at bottom if any

**Right: EntryPointPickerPanel** — scrollable list grouped by module (in topo order).

```
 Select Entry Point
----------------------------------------------
  [t] Top-level execution

  constants.py
    (no functions)

  utils.py
    [ ] helper(x)

  main.py
    [ ] main()
    [ ] process(data)
```

- Up/Down to navigate, Enter to select
- `t` shortcut for top-level execution
- Shows function names from `FuncRef` data, grouped by module

**On selection:** Execute the linked program with the chosen entry point, build the trace, transition to Phase 2.

### Phase 2: ExecutionScreen

Reuses all existing panels: Source, AST, IR, VMState, CFG, Step.

**Module-aware source switching:**
- Source panel title updates: `Source [src/utils.py]`
- When the current step's instruction belongs to a different module than the previous step, the source panel's content is replaced with `module_sources[new_path]` and the AST panel gets `module_asts[new_path]`
- Module lookup: instruction index -> binary search `module_ir_ranges` -> Path

**Keybindings (same as PipelineApp plus):**

| Key | Action |
|---|---|
| `right/l` | Step forward |
| `left/h` | Step backward |
| `f5` | Play/Pause |
| `home/end` | First/Last step |
| `a` | Toggle AST |
| `g` | Toggle CFG |
| `d` | Toggle dataflow mode |
| `p` | Toggle back to project overview (pauses execution) |
| `q` | Quit |

Step navigation logic is the same as `PipelineApp`. The `p` binding pushes/pops `ProjectOverviewScreen`.

## New Files

| File | Purpose |
|---|---|
| `viz/project_app.py` | `ProjectApp` — main app with screen management |
| `viz/project_pipeline.py` | `ProjectPipelineResult`, `run_project_pipeline()`, `execute_project()` |
| `viz/screens/project_overview_screen.py` | Phase 1 screen |
| `viz/screens/execution_screen.py` | Phase 2 screen (module-aware variant of PipelineApp layout) |
| `viz/panels/import_graph_panel.py` | Box-drawing import DAG panel |
| `viz/panels/entry_point_picker_panel.py` | Entry point selection list |

## Modified Files

| File | Change |
|---|---|
| `viz/__main__.py` | Add `project` subcommand to dispatch table |
| `viz/panels/source_panel.py` | Add method to swap source text + update title |
| `viz/panels/ast_panel.py` | Add method to swap AST tree |
| `interpreter/run.py` | Add `run_linked_traced()` function |

## What This Does NOT Change

- Single-file TUI (`python -m viz <file>`) — completely untouched
- Compare mode, lowering trace mode, coverage mode — untouched
- `LinkedProgram`, `ModuleUnit`, linker, compiler — no changes to interpreter/project/
- `execute_cfg_traced` — no changes
- Existing panels (IR, CFG, VMState, Step) — no changes (they work on merged_cfg which is already compatible)

## Testing Strategy

- Unit tests for `run_project_pipeline()` with small multi-file Python projects
- Unit tests for module IR range building + lookup
- Integration test: compile a 2-3 file Python project, verify trace steps map to correct modules
- Manual TUI testing with sample projects in multiple languages
