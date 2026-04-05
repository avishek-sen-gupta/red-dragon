# TUI MVVM Architecture — Design Spec

## Goal

Decouple the TUI visualization layer from domain types by introducing a proper MVVM (Model-View-ViewModel) architecture. Panels should never import from `interpreter/`. All domain-to-display translation happens in view dataclasses and builder functions. Navigation and command logic lives in framework-free ViewModels.

## Architecture

```
interpreter/          Model (domain types, VM, pipeline)
viz/viewmodels/       ViewModel (state + commands + view exposure)
viz/views/            View dataclasses + builder functions
viz/screens/          Screens (layout + key bindings + sync glue)
viz/panels/           Panels (pure rendering of view dataclasses)
```

### Dependency Rules

- `panels/` imports only from `views/` (view dataclasses)
- `screens/` imports from `viewmodels/`, `panels/`, and `views/`
- `viewmodels/` imports from `views/` (builders) and `interpreter/` (domain)
- `views/` builder functions import from `interpreter/` (to read domain data)
- `interpreter/` imports nothing from `viz/`

### Data Flow

```
User key press
  → Screen delegates to ViewModel command (e.g. vm.step_forward())
  → ViewModel updates internal state, calls notify
  → Screen._sync_panels() reads ViewModel view properties
  → Screen pushes view dataclasses into Panel reactives
  → Panel.watch_current_view() renders plain data
```

For view-to-domain actions (e.g. entry point selection):

```
User clicks option in OptionList
  → Screen receives OptionSelected event (plain index)
  → Screen calls ViewModel command (e.g. vm.select_entry_point(index))
  → ViewModel constructs domain EntryPoint, runs pipeline
  → App creates new ExecutionViewModel, pushes ExecutionScreen
```

## View Dataclasses

All frozen dataclasses. All fields are primitives (`str`, `int`, `bool`) or plain collections thereof. No domain types.

### `viz/views/vm_state_view.py`

```python
@dataclass(frozen=True)
class FrameView:
    function_name: str
    is_current: bool
    locals: list[tuple[str, str]]       # (name, formatted_value), pre-sorted
    registers: list[tuple[str, str]]    # (name, formatted_value), pre-sorted
    changed_vars: frozenset[str]
    changed_regs: frozenset[str]

@dataclass(frozen=True)
class HeapObjectView:
    address: str
    type_hint: str
    fields: list[tuple[str, str]]       # (field_name, formatted_value), pre-sorted
    changed_fields: frozenset[str]

@dataclass(frozen=True)
class VMStateView:
    frames: list[FrameView]             # most-recent first
    heap: list[HeapObjectView]          # sorted by address
```

### `viz/views/step_view.py`

```python
@dataclass(frozen=True)
class DeltaEntry:
    kind: str          # "reg", "var", "heap"
    label: str         # e.g. "%5", "x", "obj_0.name"
    value: str         # formatted value

@dataclass(frozen=True)
class StepView:
    step_number: int        # 1-indexed
    total_steps: int
    instruction_text: str
    deltas: list[DeltaEntry]
    next_label: str | None
    call_push: str | None       # function name or None
    call_pop_value: str | None  # formatted return value or None
    reasoning: str
    used_llm: bool
    playing: bool
```

### `viz/views/ir_view.py`

```python
@dataclass(frozen=True)
class IRBlockView:
    label: str
    successors: list[str]
    instructions: list[str]     # str(__repr__) of each instruction
    is_current: bool
    current_instruction_index: int  # -1 if none
    is_label_opcode: list[bool]     # per instruction, True if LABEL opcode (skip rendering)

@dataclass(frozen=True)
class IRView:
    blocks: list[IRBlockView]
```

### `viz/views/cfg_view.py`

```python
@dataclass(frozen=True)
class CFGBlockView:
    label: str
    is_current: bool
    instruction_count: int
    terminator: str             # "branch_if", "return", etc. or ""
    successors: list[str]
    edge_labels: list[str]      # "T"/"F"/"" per successor

@dataclass(frozen=True)
class CFGView:
    blocks: list[CFGBlockView]
```

### `viz/views/source_view.py`

```python
@dataclass(frozen=True)
class SourceView:
    highlight_start: int    # 0-indexed line, -1 if none
    highlight_end: int      # 0-indexed line, -1 if none
```

### `viz/views/dataflow_view.py`

```python
@dataclass(frozen=True)
class FunctionSummaryView:
    label: str
    params: str
    callers: str
    callees: str
    flows: list[str]        # "x → Return(f)" pre-formatted

@dataclass(frozen=True)
class DataflowSummaryView:
    functions: list[FunctionSummaryView]

@dataclass(frozen=True)
class ChainNodeView:
    label: str
    children: list[ChainNodeView]

@dataclass(frozen=True)
class DataflowGraphView:
    top_level_chains: list[ChainNodeView]
    fallback_chains: list[ChainNodeView]
```

### `viz/views/overview_view.py`

```python
@dataclass(frozen=True)
class EntryPointOption:
    display_text: str
    is_separator: bool      # OptionList separator
    is_disabled: bool       # non-selectable header
    option_index: int       # actual OptionList index

@dataclass(frozen=True)
class OverviewView:
    import_graph_text: str
    module_count: int
    entry_points: list[EntryPointOption]
```

## Builder Functions

Each view file contains a `build_*` pure function that converts domain objects to views. All sorting, `str()` coercion, `isinstance` checks, and value formatting happen here.

```python
# viz/views/vm_state_view.py
def format_value(val: object) -> str:
    """Format any VM value for display. Moved from vm_state_panel.py."""
    ...

def build_vm_state_view(step: TraceStep) -> VMStateView:
    """Convert TraceStep VM state into display-ready view."""
    ...

# viz/views/step_view.py
def build_step_view(step: TraceStep, total_steps: int, playing: bool) -> StepView:
    ...

# viz/views/ir_view.py
def build_ir_view(cfg: CFG, step: TraceStep | None = None, highlighted_block: str | None = None) -> IRView:
    ...

# viz/views/cfg_view.py
def build_cfg_view(cfg: CFG, step: TraceStep | None = None) -> CFGView:
    ...

# viz/views/source_view.py
def build_source_view(instruction: InstructionBase | None) -> SourceView:
    ...

# viz/views/dataflow_view.py
def build_dataflow_summary_view(result: InterproceduralResult) -> DataflowSummaryView:
    ...

def build_dataflow_graph_view(result: InterproceduralResult, cfg: CFG) -> DataflowGraphView:
    ...

# viz/views/overview_view.py
def build_overview_view(result: ProjectPipelineResult, project_root: Path) -> OverviewView:
    ...
```

## ViewModels

Framework-free classes. No Textual imports. Fully unit-testable.

### `viz/viewmodels/execution_vm.py`

```python
class ExecutionViewModel:
    """Owns execution state. Exposes views. Handles navigation commands."""

    def __init__(self, result: ProjectPipelineResult, project_root: Path):
        self._result = result
        self._project_root = project_root
        self._step_index = 0
        self._playing = False
        self._dataflow_mode = False
        self._highlighted_block: str | None = None
        self._current_module: Path | None = result.topo_order[0] if result.topo_order else None
        self._on_change: Callable[[], None] | None = None

    # --- Binding ---
    def bind(self, callback: Callable[[], None]) -> None:
        self._on_change = callback

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()

    # --- Commands ---
    def step_forward(self) -> None:
        if self._step_index < self.total_steps - 1:
            self._step_index += 1
            self._check_module_switch()
            self._notify()

    def step_backward(self) -> None:
        if self._step_index > 0:
            self._step_index -= 1
            self._check_module_switch()
            self._notify()

    def step_first(self) -> None:
        self._step_index = 0
        self._check_module_switch()
        self._notify()

    def step_last(self) -> None:
        self._step_index = max(0, self.total_steps - 1)
        self._check_module_switch()
        self._notify()

    def toggle_play(self) -> None:
        self._playing = not self._playing
        self._notify()

    def toggle_dataflow(self) -> None:
        self._dataflow_mode = not self._dataflow_mode
        self._notify()

    def highlight_block(self, label: str | None) -> None:
        self._highlighted_block = label
        self._notify()

    # --- Computed state ---
    @property
    def total_steps(self) -> int: ...
    @property
    def playing(self) -> bool: ...
    @property
    def dataflow_mode(self) -> bool: ...
    @property
    def module_changed(self) -> bool: ...
    @property
    def current_module_source(self) -> str: ...
    @property
    def current_module_ast(self) -> ASTNode | None: ...
    # Note: ASTNode is defined in viz/pipeline.py — it's a viz-layer type, not a domain type.

    # --- View properties ---
    @property
    def vm_state(self) -> VMStateView: ...
    @property
    def cfg(self) -> CFGView: ...
    @property
    def ir(self) -> IRView: ...
    @property
    def source(self) -> SourceView: ...
    @property
    def step(self) -> StepView: ...
    @property
    def dataflow_summary(self) -> DataflowSummaryView: ...
    @property
    def dataflow_graph(self) -> DataflowGraphView: ...

    # --- Internal ---
    def _check_module_switch(self) -> None:
        """Detect module transitions using instruction_to_index + lookup_module_for_index."""
        ...
```

### `viz/viewmodels/overview_vm.py`

```python
class OverviewViewModel:
    """Owns project overview state. Handles entry point selection."""

    def __init__(self, result: ProjectPipelineResult, project_root: Path):
        self._result = result
        self._project_root = project_root
        self._entry_point_map: dict[int, FuncRef | None] = {}

    @property
    def overview(self) -> OverviewView:
        """Build display data for overview screen. Populates _entry_point_map as side effect."""
        ...

    def select_entry_point(self, option_index: int) -> EntryPoint | None:
        """Translate option index to domain EntryPoint."""
        func_ref = self._entry_point_map.get(option_index)
        if func_ref is None:
            return None
        return EntryPoint.function(lambda f, n=func_ref.name: f.name == n)
```

## Screen Refactoring

Screens become thin glue: layout, key bindings, and sync.

### `ExecutionScreen`

```python
class ExecutionScreen(Screen):
    def __init__(self, vm: ExecutionViewModel, project_root: Path):
        super().__init__()
        self._vm = vm
        self._project_root = project_root

    def on_mount(self):
        self._vm.bind(self._sync_panels)
        self._sync_panels()

    def _sync_panels(self):
        self.query_one(VMStatePanel).current_view = self._vm.vm_state
        self.query_one(CFGPanel).current_view = self._vm.cfg
        self.query_one(IRPanel).current_view = self._vm.ir
        self.query_one(SourcePanel).current_view = self._vm.source
        self.query_one(StepPanel).current_view = self._vm.step
        # Handle module switching
        if self._vm.module_changed:
            self.query_one(SourcePanel).set_source(self._vm.current_module_source)
            ast = self._vm.current_module_ast
            if ast:
                self.query_one(ASTPanel).set_ast(ast)

    def action_step_forward(self):
        self._vm.step_forward()

    def action_step_backward(self):
        self._vm.step_backward()

    def action_toggle_play(self):
        self._vm.toggle_play()
        if self._vm.playing:
            self._play_timer = self.set_interval(0.5, self._auto_step)
        elif self._play_timer:
            self._play_timer.stop()
            self._play_timer = None

    def _auto_step(self):
        self._vm.step_forward()
        if self._vm.playing and self._vm._step_index >= self._vm.total_steps - 1:
            self._vm.toggle_play()
```

### `ProjectOverviewScreen`

```python
class ProjectOverviewScreen(Screen):
    def __init__(self, vm: OverviewViewModel):
        super().__init__()
        self._vm = vm

    def compose(self):
        overview = self._vm.overview
        yield Header()
        with Horizontal():
            yield Static(overview.import_graph_text)
            picker = EntryPointPickerPanel(overview.entry_points, id="entry-picker-panel")
            yield picker
        yield Footer()

    def on_option_list_option_selected(self, event):
        entry_point = self._vm.select_entry_point(event.option_index)
        self.app.execute_entry_point(entry_point)
```

## Panel Refactoring

Every panel changes from `current_step: reactive[TraceStep | None]` to `current_view: reactive[*View | None]`. Rendering logic stays, domain extraction goes.

### Import Changes

**Before:** Panels import from `interpreter.trace_types`, `interpreter.vm.vm_types`, `interpreter.ir`, `interpreter.cfg_types`, `interpreter.interprocedural.types`, etc.

**After:** Panels import only from `viz.views.*`.

### Key Panel Changes

- **VMStatePanel**: Remove `_format_value`, `isinstance` checks on `TypedValue`/`Pointer`/`SymbolicValue`/`HeapObject`. Iterate `FrameView.locals`/`.registers` (already sorted strings).
- **StepPanel**: Remove direct access to `StateUpdate` fields. Read `StepView.deltas`, `.call_push`, `.call_pop_value`, `.reasoning`.
- **IRPanel**: Remove `CFG` dependency and `Opcode` import. Iterate `IRBlockView` list.
- **CFGPanel**: Remove `CFG` dependency and `Opcode` import. Iterate `CFGBlockView` list.
- **SourcePanel**: Remove `InstructionBase` reference. Read `SourceView.highlight_start/end`.
- **ASTPanel**: Already mostly clean. Remove `InstructionBase` reference. Receive highlight coordinates via `SourceView`.
- **DataflowSummaryPanel**: Remove all `interprocedural.types` imports. Receive `DataflowSummaryView` at construction.
- **DataflowGraphPanel**: Remove all `interprocedural.types`, `instructions`, `cfg_types` imports. Receive `DataflowGraphView` at construction.
- **EntryPointPickerPanel**: Remove `FuncRef` and `CodeLabel` imports. Receive `list[EntryPointOption]` (plain strings).

## App Changes

`ProjectApp` creates ViewModels and passes them to screens:

```python
class ProjectApp(App):
    def on_mount(self):
        vm = OverviewViewModel(self._result, self._project_root)
        self.push_screen(ProjectOverviewScreen(vm))

    def execute_entry_point(self, entry_point):
        self._result = execute_project(self._result, entry_point)
        vm = ExecutionViewModel(self._result, self._project_root)
        self.push_screen(ExecutionScreen(vm, self._project_root))
```

`ProjectApp` remains the one place that imports pipeline functions (`execute_project`) and creates ViewModels.

## Testing Strategy

### Builder Tests (`tests/unit/viz/views/`)

Each builder gets unit tests that construct domain objects and verify the output view:

```python
def test_build_vm_state_view_sorts_registers():
    step = make_trace_step(registers={Register("%b"): ..., Register("%a"): ...})
    view = build_vm_state_view(step)
    assert [r[0] for r in view.frames[0].registers] == ["%a", "%b"]

def test_build_cfg_view_labels_conditional_edges():
    cfg = make_cfg_with_branch_if()
    view = build_cfg_view(cfg)
    assert view.blocks[0].edge_labels == ["T", "F"]
```

### ViewModel Tests (`tests/unit/viz/viewmodels/`)

Test navigation, state transitions, and view exposure without any Textual dependency:

```python
def test_step_forward_increments_and_notifies():
    vm = ExecutionViewModel(result, root)
    notified = []
    vm.bind(lambda: notified.append(True))
    vm.step_forward()
    assert len(notified) == 1

def test_step_forward_at_end_does_nothing():
    vm = ExecutionViewModel(result, root)
    vm.step_last()
    vm.step_forward()
    # no crash, no notification
```

### Panel Tests (`tests/unit/viz/panels/`)

Panel tests construct view dataclasses directly (no domain objects needed):

```python
def test_vm_state_panel_renders_frame():
    view = VMStateView(frames=[FrameView(...)], heap=[])
    # verify panel.watch_current_view(view) doesn't crash
```

### Guard Tests

Keep the existing tests that verify bare `sorted()` on domain objects raises `TypeError`. These are regression guards ensuring domain types never grow `__lt__`.

## Scope — What This Does NOT Change

- `viz/pipeline.py` and `viz/project_pipeline.py` — these are pipeline orchestration, not presentation. They stay as-is.
- `viz/lowering_trace.py` and `viz/coverage.py` — separate TUI apps with their own domain coupling. Out of scope.
- `viz/app.py` (single-file PipelineApp) — out of scope; this refactor targets the project TUI (`viz/project_app.py` and its screens/panels).
- Domain types themselves — no `__lt__`, `__str__` changes, no display logic added to domain objects.

## File Summary

### New Files

| File | Purpose |
|------|---------|
| `viz/views/__init__.py` | Package init |
| `viz/views/vm_state_view.py` | VMStateView + FrameView + HeapObjectView + format_value + build_vm_state_view |
| `viz/views/step_view.py` | StepView + DeltaEntry + build_step_view |
| `viz/views/ir_view.py` | IRView + IRBlockView + build_ir_view |
| `viz/views/cfg_view.py` | CFGView + CFGBlockView + build_cfg_view |
| `viz/views/source_view.py` | SourceView + build_source_view |
| `viz/views/dataflow_view.py` | DataflowSummaryView + DataflowGraphView + builders |
| `viz/views/overview_view.py` | OverviewView + EntryPointOption + build_overview_view |
| `viz/viewmodels/__init__.py` | Package init |
| `viz/viewmodels/execution_vm.py` | ExecutionViewModel |
| `viz/viewmodels/overview_vm.py` | OverviewViewModel |

### Modified Files

| File | Change |
|------|--------|
| `viz/panels/vm_state_panel.py` | Replace TraceStep reactive with VMStateView. Remove domain imports. |
| `viz/panels/step_panel.py` | Replace TraceStep reactive with StepView. Remove domain imports. |
| `viz/panels/ir_panel.py` | Replace CFG+TraceStep with IRView. Remove domain imports. |
| `viz/panels/cfg_panel.py` | Replace CFG+TraceStep with CFGView. Remove domain imports. |
| `viz/panels/source_panel.py` | Replace InstructionBase with SourceView. |
| `viz/panels/ast_panel.py` | Replace InstructionBase with SourceView for highlighting. |
| `viz/panels/dataflow_summary_panel.py` | Replace InterproceduralResult with DataflowSummaryView. Remove domain imports. |
| `viz/panels/dataflow_graph_panel.py` | Replace InterproceduralResult+CFG with DataflowGraphView. Remove domain imports. |
| `viz/panels/entry_point_picker_panel.py` | Replace FuncRef/CodeLabel with EntryPointOption. Remove domain imports. |
| `viz/screens/execution_screen.py` | Use ExecutionViewModel. Thin sync glue. |
| `viz/screens/project_overview_screen.py` | Use OverviewViewModel. Thin event handling. |
| `viz/project_app.py` | Create ViewModels, pass to screens. |

### New Test Files

| File | Purpose |
|------|---------|
| `tests/unit/viz/views/test_vm_state_view.py` | Builder tests |
| `tests/unit/viz/views/test_step_view.py` | Builder tests |
| `tests/unit/viz/views/test_ir_view.py` | Builder tests |
| `tests/unit/viz/views/test_cfg_view.py` | Builder tests |
| `tests/unit/viz/views/test_source_view.py` | Builder tests |
| `tests/unit/viz/views/test_dataflow_view.py` | Builder tests |
| `tests/unit/viz/views/test_overview_view.py` | Builder tests |
| `tests/unit/viz/viewmodels/test_execution_vm.py` | ViewModel tests |
| `tests/unit/viz/viewmodels/test_overview_vm.py` | ViewModel tests |
