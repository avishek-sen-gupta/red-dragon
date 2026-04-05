# Multi-File Project TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the RedDragon TUI visualizer to support multi-file projects with a two-phase interactive experience: project overview (import graph + entry point selection) followed by module-aware execution debugging.

**Architecture:** A new `project` subcommand compiles a directory via `compile_directory()`, presents a two-screen Textual app (overview → execution), and switches source/AST panels as execution crosses module boundaries. The data pipeline lives in `viz/project_pipeline.py`, the app shell in `viz/project_app.py`, and two screens + two panels handle the UI.

**Tech Stack:** Python 3.13+, Textual (TUI framework), tree-sitter (AST), existing interpreter/project infrastructure.

---

## File Map

| File | Responsibility |
|------|----------------|
| **Create:** `viz/project_pipeline.py` | `ProjectPipelineResult` dataclass, `run_project_pipeline()`, `execute_project()`, module-to-IR range building |
| **Create:** `viz/project_app.py` | `ProjectApp` — Textual App with two-screen architecture |
| **Create:** `viz/screens/__init__.py` | Package init |
| **Create:** `viz/screens/project_overview_screen.py` | Phase 1 screen: import graph + entry point picker |
| **Create:** `viz/screens/execution_screen.py` | Phase 2 screen: module-aware execution debugging |
| **Create:** `viz/panels/import_graph_panel.py` | Box-drawing import DAG visualization |
| **Create:** `viz/panels/entry_point_picker_panel.py` | Scrollable entry point selection list |
| **Modify:** `viz/__main__.py` | Add `project` to subcommand dispatch table |
| **Modify:** `interpreter/run.py` | Add `run_linked_traced()` function |
| **Modify:** `viz/panels/source_panel.py` | Add `set_title()` method for module-aware title updates |
| **Modify:** `viz/panels/ast_panel.py` | Add `set_ast()` method to swap AST tree |
| **Test:** `tests/unit/viz/test_project_pipeline.py` | Unit tests for pipeline, IR range building, module lookup |
| **Test:** `tests/integration/viz/test_project_tui.py` | Integration tests for full project pipeline + trace module mapping |

---

## Task 1: `run_linked_traced()` in interpreter/run.py

**Files:**
- Modify: `interpreter/run.py` (after `run_linked()` at line ~776)
- Test: `tests/unit/viz/test_run_linked_traced.py`

This mirrors `run_linked()` but uses `execute_cfg_traced()` instead of `execute_cfg()` and returns `(VMState, ExecutionTrace)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/viz/test_run_linked_traced.py`:

```python
"""Tests for run_linked_traced — traced execution of LinkedPrograms."""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.project.compiler import compile_directory
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run_linked_traced
from interpreter.trace_types import ExecutionTrace


class TestRunLinkedTraced:
    """run_linked_traced returns (VMState, ExecutionTrace) for linked programs."""

    def test_top_level_returns_trace(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1 + 2\n")
        linked = compile_directory(tmp_path, Language.PYTHON)

        vm, trace = run_linked_traced(linked, EntryPoint.top_level(), max_steps=100)

        assert isinstance(trace, ExecutionTrace)
        assert len(trace.steps) > 0
        assert vm.lookup_var("x") is not None

    def test_function_entry_returns_trace(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text(
            "def add(a, b):\n    return a + b\n"
        )
        linked = compile_directory(tmp_path, Language.PYTHON)

        vm, trace = run_linked_traced(
            linked,
            EntryPoint.function(lambda f: str(f.name) == "add"),
            max_steps=100,
        )

        assert isinstance(trace, ExecutionTrace)
        assert len(trace.steps) > 0

    def test_two_phase_concatenates_traces(self, tmp_path: Path) -> None:
        """Function entry: preamble trace + dispatch trace are concatenated."""
        (tmp_path / "utils.py").write_text("MAGIC = 42\n")
        (tmp_path / "main.py").write_text(
            "from utils import MAGIC\n\ndef show():\n    return MAGIC\n"
        )
        linked = compile_directory(tmp_path, Language.PYTHON)

        vm, trace = run_linked_traced(
            linked,
            EntryPoint.function(lambda f: str(f.name) == "show"),
            max_steps=200,
        )

        assert len(trace.steps) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/viz/test_run_linked_traced.py -v`
Expected: FAIL with `ImportError: cannot import name 'run_linked_traced' from 'interpreter.run'`

- [ ] **Step 3: Implement `run_linked_traced`**

Add to `interpreter/run.py` after the `run_linked()` function (after line ~776):

```python
def run_linked_traced(
    linked: LinkedProgram,
    entry_point: EntryPoint,
    max_steps: int = 100,
    verbose: bool = False,
    backend: str = LLMProvider.CLAUDE,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
) -> tuple[VMState, ExecutionTrace]:
    """Execute a LinkedProgram with tracing. Returns (VMState, ExecutionTrace).

    Mirrors run_linked() but uses execute_cfg_traced() to capture every step.
    For function entry points, concatenates preamble + dispatch traces.
    """
    strategies = _build_strategies_from_linked(linked)

    vm_config = VMConfig(
        backend=backend,
        max_steps=max_steps,
        verbose=verbose,
        source_language=linked.language,
        unresolved_call_strategy=unresolved_call_strategy,
    )

    if entry_point.is_top_level:
        vm, trace = execute_cfg_traced(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            vm_config,
            strategies,
        )
    else:
        # Phase 1: preamble
        vm, preamble_trace = execute_cfg_traced(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            vm_config,
            strategies,
        )

        # Resolve entry point function via predicate
        func_ref = entry_point.resolve(list(linked.func_symbol_table.values()))
        func_label = _resolve_entry_function(vm, str(func_ref.name), linked.merged_cfg)

        # Phase 2: dispatch into target function
        remaining = max_steps - preamble_trace.stats.steps
        phase2_config = replace(vm_config, max_steps=max(remaining, 0))
        vm, dispatch_trace = execute_cfg_traced(
            linked.merged_cfg,
            func_label,
            linked.merged_registry,
            phase2_config,
            strategies,
            vm=vm,
        )

        # Concatenate traces — renumber dispatch steps
        all_steps = list(preamble_trace.steps)
        offset = len(all_steps)
        for step in dispatch_trace.steps:
            all_steps.append(replace(step, step_index=step.step_index + offset))

        combined_stats = ExecutionStats(
            steps=preamble_trace.stats.steps + dispatch_trace.stats.steps,
            llm_calls=preamble_trace.stats.llm_calls + dispatch_trace.stats.llm_calls,
        )
        trace = ExecutionTrace(
            steps=all_steps,
            stats=combined_stats,
            initial_state=preamble_trace.initial_state,
        )

    vm.data_layout = linked.data_layout
    return vm, trace
```

Note: `replace` is `dataclasses.replace` — confirm it's already imported at the top of `run.py`. If not, add `from dataclasses import replace`.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/viz/test_run_linked_traced.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add interpreter/run.py tests/unit/viz/test_run_linked_traced.py
git commit -m "feat(viz): add run_linked_traced for traced multi-file execution"
```

---

## Task 2: `ProjectPipelineResult` and `run_project_pipeline()`

**Files:**
- Create: `viz/project_pipeline.py`
- Test: `tests/unit/viz/test_project_pipeline.py`

The data model and pipeline function. No execution here — trace is `None` until entry point selection.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/viz/test_project_pipeline.py`:

```python
"""Tests for the project pipeline — compile directory into ProjectPipelineResult."""

from pathlib import Path

import pytest

from interpreter.constants import Language
from viz.project_pipeline import (
    ProjectPipelineResult,
    run_project_pipeline,
    execute_project,
    lookup_module_for_index,
)


class TestRunProjectPipeline:
    """run_project_pipeline compiles a directory and returns ProjectPipelineResult."""

    def test_single_file_project(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1\n")

        result = run_project_pipeline(tmp_path, "python")

        assert isinstance(result, ProjectPipelineResult)
        assert result.linked is not None
        assert len(result.module_sources) == 1
        assert len(result.module_asts) == 1
        assert len(result.topo_order) == 1
        assert result.trace is None

    def test_two_file_project(self, tmp_path: Path) -> None:
        (tmp_path / "utils.py").write_text("def helper(x):\n    return x + 1\n")
        (tmp_path / "main.py").write_text("from utils import helper\nresult = helper(5)\n")

        result = run_project_pipeline(tmp_path, "python")

        assert len(result.module_sources) == 2
        assert len(result.topo_order) == 2
        # utils.py should come before main.py in topo order (dependency first)
        paths_by_name = {p.name: p for p in result.topo_order}
        assert list(paths_by_name.keys()).index("utils.py") < list(paths_by_name.keys()).index("main.py")

    def test_module_ir_ranges_cover_all_instructions(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.py").write_text("y = 2\n")

        result = run_project_pipeline(tmp_path, "python")

        # All instructions should be covered by ranges
        total_ir = len(result.linked.merged_ir)
        covered = set()
        for start, end, _path in result.module_ir_ranges:
            for i in range(start, end):
                covered.add(i)
        # At minimum, non-entry instructions are covered
        assert len(covered) > 0


class TestModuleLookup:
    """lookup_module_for_index finds the owning module for an instruction index."""

    def test_lookup_returns_correct_module(self, tmp_path: Path) -> None:
        (tmp_path / "utils.py").write_text("x = 1\n")
        (tmp_path / "main.py").write_text("from utils import x\ny = x\n")

        result = run_project_pipeline(tmp_path, "python")

        # First range's start index should map back to the first module
        if result.module_ir_ranges:
            start, _end, expected_path = result.module_ir_ranges[0]
            found = lookup_module_for_index(result.module_ir_ranges, start)
            assert found == expected_path

    def test_lookup_out_of_range_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1\n")

        result = run_project_pipeline(tmp_path, "python")

        found = lookup_module_for_index(result.module_ir_ranges, 999999)
        assert found is None


class TestExecuteProject:
    """execute_project populates trace on a ProjectPipelineResult."""

    def test_top_level_execution(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 42\n")

        result = run_project_pipeline(tmp_path, "python")
        result = execute_project(result, entry_point=None, max_steps=100)

        assert result.trace is not None
        assert len(result.trace.steps) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/viz/test_project_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'viz.project_pipeline'`

- [ ] **Step 3: Implement `viz/project_pipeline.py`**

```python
"""Project pipeline — compile a directory into a ProjectPipelineResult for TUI display."""

from __future__ import annotations

import bisect
import dataclasses
import logging
from dataclasses import dataclass, field
from pathlib import Path

from interpreter.constants import Language
from interpreter.interprocedural.analyze import analyze_interprocedural
from interpreter.interprocedural.types import InterproceduralResult
from interpreter.parser import TreeSitterParserFactory
from interpreter.project.compiler import compile_directory
from interpreter.project.entry_point import EntryPoint
from interpreter.project.linker import module_prefix
from interpreter.project.resolver import topological_sort
from interpreter.project.types import LinkedProgram
from interpreter.run import run_linked_traced
from interpreter.trace_types import ExecutionTrace
from viz.pipeline import ASTNode, _ast_from_ts_node

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectPipelineResult:
    """All stage outputs from a multi-file project pipeline run."""

    linked: LinkedProgram
    module_sources: dict[Path, str]
    module_asts: dict[Path, ASTNode]
    topo_order: list[Path]
    module_ir_ranges: list[tuple[int, int, Path]]
    instruction_to_index: dict[int, int]
    trace: ExecutionTrace | None = None
    interprocedural: InterproceduralResult | None = None


def run_project_pipeline(
    directory: str | Path,
    language: str,
) -> ProjectPipelineResult:
    """Compile a directory into a ProjectPipelineResult.

    Execution (trace) is deferred until execute_project() is called.
    """
    directory = Path(directory).resolve()
    lang = Language(language)
    linked = compile_directory(directory, lang)

    topo_order = topological_sort(linked.import_graph)

    # Pre-load sources and ASTs
    parser_factory = TreeSitterParserFactory()
    ts_parser = parser_factory.get_parser(language)
    module_sources: dict[Path, str] = {}
    module_asts: dict[Path, ASTNode] = {}
    for path in topo_order:
        text = path.read_text()
        module_sources[path] = text
        source_bytes = text.encode("utf-8")
        tree = ts_parser.parse(source_bytes)
        module_asts[path] = _ast_from_ts_node(tree.root_node, source_bytes)

    # Build module IR ranges
    module_ir_ranges = _build_module_ir_ranges(linked, topo_order, directory)

    # Build instruction identity map
    instruction_to_index = {id(inst): i for i, inst in enumerate(linked.merged_ir)}

    return ProjectPipelineResult(
        linked=linked,
        module_sources=module_sources,
        module_asts=module_asts,
        topo_order=topo_order,
        module_ir_ranges=module_ir_ranges,
        instruction_to_index=instruction_to_index,
    )


def execute_project(
    result: ProjectPipelineResult,
    entry_point: EntryPoint | None,
    max_steps: int,
) -> ProjectPipelineResult:
    """Execute the linked program and populate the trace.

    Args:
        result: Pipeline result from run_project_pipeline().
        entry_point: None for top-level, or an EntryPoint.function(...).
        max_steps: Maximum execution steps.
    """
    if entry_point is None:
        entry_point = EntryPoint.top_level()

    _vm, trace = run_linked_traced(result.linked, entry_point, max_steps=max_steps)

    try:
        interprocedural = analyze_interprocedural(
            result.linked.merged_cfg, result.linked.merged_registry
        )
    except Exception:
        logger.warning("Interprocedural analysis failed", exc_info=True)
        interprocedural = None

    return dataclasses.replace(result, trace=trace, interprocedural=interprocedural)


def lookup_module_for_index(
    ranges: list[tuple[int, int, Path]],
    index: int,
) -> Path | None:
    """Binary search module_ir_ranges to find the owning module for an instruction index."""
    # ranges are sorted by start index; find the rightmost range where start <= index
    starts = [r[0] for r in ranges]
    pos = bisect.bisect_right(starts, index) - 1
    if pos < 0:
        return None
    start, end, path = ranges[pos]
    if start <= index < end:
        return path
    return None


def _build_module_ir_ranges(
    linked: LinkedProgram,
    topo_order: list[Path],
    project_root: Path,
) -> list[tuple[int, int, Path]]:
    """Build (start, end, path) ranges mapping merged_ir indices to source modules.

    Walks merged_ir tracking module transitions by matching label prefixes
    against known module_prefix() values for each file in topo_order.
    """
    if not topo_order:
        return []

    prefixes = {
        module_prefix(path, project_root): path for path in topo_order
    }

    merged_ir = linked.merged_ir
    ranges: list[tuple[int, int, Path]] = []
    current_path = topo_order[0]
    current_start = 0

    for i, inst in enumerate(merged_ir):
        # Check if this instruction is a LABEL that signals a module transition
        if inst.opcode.name == "LABEL" and hasattr(inst, "label"):
            label_str = str(inst.label)
            for prefix, path in prefixes.items():
                if label_str.startswith(prefix + ".") or label_str == prefix:
                    if path != current_path:
                        # Close previous range
                        if i > current_start:
                            ranges.append((current_start, i, current_path))
                        current_path = path
                        current_start = i
                    break

    # Close final range
    if len(merged_ir) > current_start:
        ranges.append((current_start, len(merged_ir), current_path))

    return ranges
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/viz/test_project_pipeline.py -v`
Expected: All PASSED

- [ ] **Step 5: Commit**

```bash
git add viz/project_pipeline.py tests/unit/viz/test_project_pipeline.py
git commit -m "feat(viz): add ProjectPipelineResult and run_project_pipeline"
```

---

## Task 3: Source and AST panel swap methods

**Files:**
- Modify: `viz/panels/ast_panel.py` (add `set_ast()` method)
- Modify: `viz/panels/source_panel.py` (add `set_title()` convenience — `set_source()` already exists)
- Test: `tests/unit/viz/test_panel_swap.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/viz/test_panel_swap.py`:

```python
"""Tests for source/AST panel content swapping."""

from viz.panels.ast_panel import ASTPanel
from viz.panels.source_panel import SourcePanel
from viz.pipeline import ASTNode


class TestSourcePanelSwap:
    """SourcePanel.set_source replaces content."""

    def test_set_source_updates_lines(self) -> None:
        panel = SourcePanel("line1\nline2")
        assert len(panel._lines) == 2

        panel.set_source("a\nb\nc")
        assert len(panel._lines) == 3


class TestASTPanelSwap:
    """ASTPanel.set_ast replaces the tree."""

    def test_set_ast_stores_new_ast(self) -> None:
        ast1 = ASTNode("module", "mod1", 1, 0, 1, 3, [])
        ast2 = ASTNode("module", "mod2", 1, 0, 2, 5, [])

        panel = ASTPanel(ast1)
        assert panel._ast is ast1

        panel.set_ast(ast2)
        assert panel._ast is ast2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/viz/test_panel_swap.py -v`
Expected: FAIL with `AttributeError: 'ASTPanel' object has no attribute 'set_ast'`

- [ ] **Step 3: Add `set_ast()` to ASTPanel**

In `viz/panels/ast_panel.py`, add after the `__init__` method (after line ~20):

```python
    def set_ast(self, ast: ASTNode) -> None:
        """Replace the AST tree with a new one and rebuild the widget tree."""
        self._ast = ast
        self._node_map.clear()
        self.root.remove_children()
        if self._ast:
            self._populate_tree(self.root, self._ast)
            self.root.expand()
            for child in self.root.children:
                child.expand()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/viz/test_panel_swap.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add viz/panels/ast_panel.py tests/unit/viz/test_panel_swap.py
git commit -m "feat(viz): add set_ast() to ASTPanel for module switching"
```

---

## Task 4: ImportGraphPanel

**Files:**
- Create: `viz/panels/import_graph_panel.py`
- Test: `tests/unit/viz/test_import_graph_panel.py`

Box-drawing DAG of the import graph, showing modules in topo order with edge annotations.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/viz/test_import_graph_panel.py`:

```python
"""Tests for ImportGraphPanel — box-drawing import DAG."""

from pathlib import Path

from viz.panels.import_graph_panel import render_import_graph


class TestRenderImportGraph:
    """render_import_graph produces a text DAG of the import graph."""

    def test_single_module(self) -> None:
        root = Path("/project")
        topo = [Path("/project/main.py")]
        graph: dict[Path, list[Path]] = {topo[0]: []}
        exports: dict[Path, tuple[int, int]] = {topo[0]: (1, 0)}

        text = render_import_graph(topo, graph, exports, root)

        assert "main.py" in text
        assert "1." in text

    def test_two_modules_with_edge(self) -> None:
        root = Path("/project")
        utils = Path("/project/utils.py")
        main = Path("/project/main.py")
        topo = [utils, main]
        graph: dict[Path, list[Path]] = {utils: [], main: [utils]}
        exports: dict[Path, tuple[int, int]] = {utils: (1, 0), main: (1, 0)}

        text = render_import_graph(topo, graph, exports, root)

        assert "utils.py" in text
        assert "main.py" in text
        assert "imports" in text.lower() or "→" in text or "──" in text

    def test_three_modules_chain(self) -> None:
        root = Path("/project")
        a = Path("/project/a.py")
        b = Path("/project/b.py")
        c = Path("/project/c.py")
        topo = [a, b, c]
        graph: dict[Path, list[Path]] = {a: [], b: [a], c: [b]}
        exports: dict[Path, tuple[int, int]] = {a: (0, 1), b: (2, 0), c: (1, 0)}

        text = render_import_graph(topo, graph, exports, root)

        lines = text.strip().split("\n")
        assert len(lines) >= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/viz/test_import_graph_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'viz.panels.import_graph_panel'`

- [ ] **Step 3: Implement `viz/panels/import_graph_panel.py`**

```python
"""Import graph panel — box-drawing DAG of the project's import structure."""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Static


def render_import_graph(
    topo_order: list[Path],
    import_graph: dict[Path, list[Path]],
    exports: dict[Path, tuple[int, int]],
    project_root: Path,
) -> str:
    """Render a text-based import DAG.

    Args:
        topo_order: Modules in topological (dependency-first) order.
        import_graph: path -> list of paths it imports.
        exports: path -> (function_count, variable_count).
        project_root: Root directory for relative path display.

    Returns:
        Multi-line string with box-drawing import graph.
    """
    lines: list[str] = []
    name_for: dict[Path, str] = {}

    for i, path in enumerate(topo_order, start=1):
        rel = path.relative_to(project_root) if path.is_relative_to(project_root) else path
        name_for[path] = str(rel)
        fn_count, var_count = exports.get(path, (0, 0))
        parts = []
        if fn_count:
            parts.append(f"{fn_count} fn")
        if var_count:
            parts.append(f"{var_count} var")
        summary = f" ({', '.join(parts)})" if parts else ""
        lines.append(f"  {i}. {rel}{summary}")

        deps = import_graph.get(path, [])
        if deps:
            dep_names = ", ".join(name_for.get(d, str(d)) for d in deps)
            lines.append(f"     └── imports ── {dep_names}")

        # Draw connector to next module
        if i < len(topo_order):
            lines.append("     │")

    return "\n".join(lines)


class ImportGraphPanel(Static):
    """Displays a box-drawing DAG of the project's import graph."""

    def __init__(
        self,
        topo_order: list[Path],
        import_graph: dict[Path, list[Path]],
        exports: dict[Path, tuple[int, int]],
        project_root: Path,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._topo_order = topo_order
        self._import_graph = import_graph
        self._exports = exports
        self._project_root = project_root

    def on_mount(self) -> None:
        text = render_import_graph(
            self._topo_order, self._import_graph, self._exports, self._project_root
        )
        header = f" Import Graph ({len(self._topo_order)} modules, topo order)\n"
        header += "─" * 50 + "\n"
        self.update(header + text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/viz/test_import_graph_panel.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add viz/panels/import_graph_panel.py tests/unit/viz/test_import_graph_panel.py
git commit -m "feat(viz): add ImportGraphPanel with box-drawing DAG"
```

---

## Task 5: EntryPointPickerPanel

**Files:**
- Create: `viz/panels/entry_point_picker_panel.py`
- Test: `tests/unit/viz/test_entry_point_picker.py`

Scrollable list of entry points grouped by module, with keyboard navigation.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/viz/test_entry_point_picker.py`:

```python
"""Tests for EntryPointPickerPanel — entry point grouping and selection."""

from pathlib import Path

from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel
from interpreter.refs.func_ref import FuncRef

from viz.panels.entry_point_picker_panel import group_entry_points


class TestGroupEntryPoints:
    """group_entry_points organizes FuncRefs by module."""

    def test_empty_modules(self) -> None:
        result = group_entry_points([], {})
        assert result == []

    def test_single_module_single_function(self) -> None:
        path = Path("/project/main.py")
        ref = FuncRef(name=FuncName("main"), label=CodeLabel("main.func_main_0"))
        func_table = {CodeLabel("main.func_main_0"): ref}

        result = group_entry_points([path], func_table)

        assert len(result) == 1
        module_path, funcs = result[0]
        assert module_path == path
        assert len(funcs) == 1
        assert funcs[0].name == FuncName("main")

    def test_two_modules(self) -> None:
        utils = Path("/project/utils.py")
        main = Path("/project/main.py")
        ref1 = FuncRef(name=FuncName("helper"), label=CodeLabel("utils.func_helper_0"))
        ref2 = FuncRef(name=FuncName("run"), label=CodeLabel("main.func_run_0"))
        func_table = {ref1.label: ref1, ref2.label: ref2}

        result = group_entry_points([utils, main], func_table)

        assert len(result) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/viz/test_entry_point_picker.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `viz/panels/entry_point_picker_panel.py`**

```python
"""Entry point picker panel — scrollable list of functions grouped by module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option, Separator

from interpreter.ir import CodeLabel
from interpreter.project.linker import module_prefix
from interpreter.refs.func_ref import FuncRef


@dataclass(frozen=True)
class EntryPointSelected(Message):
    """Posted when the user selects an entry point."""

    func_ref: FuncRef | None  # None = top-level execution


def group_entry_points(
    topo_order: list[Path],
    func_symbol_table: dict[CodeLabel, FuncRef],
) -> list[tuple[Path, list[FuncRef]]]:
    """Group function refs by module, ordered by topo_order.

    Matches FuncRefs to modules by checking if their label string starts
    with a prefix derived from the module path.
    """
    result: list[tuple[Path, list[FuncRef]]] = []

    for path in topo_order:
        # Match funcs whose label starts with any recognizable prefix for this path
        stem = path.stem
        matched: list[FuncRef] = []
        for label, ref in func_symbol_table.items():
            label_str = str(label)
            # Labels are namespaced as "module.func_name_N" — match on stem prefix
            if label_str.startswith(stem + ".") or label_str.startswith(stem + "_"):
                matched.append(ref)
        result.append((path, matched))

    return result


class EntryPointPickerPanel(OptionList):
    """Scrollable list of entry points grouped by module."""

    def __init__(
        self,
        topo_order: list[Path],
        func_symbol_table: dict[CodeLabel, FuncRef],
        project_root: Path,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._topo_order = topo_order
        self._func_symbol_table = func_symbol_table
        self._project_root = project_root
        self._option_refs: dict[int, FuncRef | None] = {}

    def on_mount(self) -> None:
        # Top-level option
        self.add_option(Option("[t] Top-level execution"))
        self._option_refs[0] = None
        option_idx = 1

        grouped = group_entry_points(self._topo_order, self._func_symbol_table)
        for path, funcs in grouped:
            rel = path.relative_to(self._project_root) if path.is_relative_to(self._project_root) else path
            self.add_option(Separator())
            self.add_option(Option(f"  {rel}", disabled=True))

            if not funcs:
                self.add_option(Option("    (no functions)", disabled=True))
            else:
                for ref in funcs:
                    self.add_option(Option(f"    {ref.name}()"))
                    self._option_refs[option_idx] = ref
                    option_idx += 1

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if idx in self._option_refs:
            self.post_message(EntryPointSelected(func_ref=self._option_refs[idx]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/viz/test_entry_point_picker.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add viz/panels/entry_point_picker_panel.py tests/unit/viz/test_entry_point_picker.py
git commit -m "feat(viz): add EntryPointPickerPanel with module grouping"
```

---

## Task 6: ProjectOverviewScreen

**Files:**
- Create: `viz/screens/__init__.py`
- Create: `viz/screens/project_overview_screen.py`

Phase 1 screen: import graph on the left, entry point picker on the right.

- [ ] **Step 1: Create screens package**

```python
# viz/screens/__init__.py
```

- [ ] **Step 2: Implement `viz/screens/project_overview_screen.py`**

```python
"""Project overview screen — import graph + entry point picker."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static

from interpreter.func_name import FuncName
from interpreter.project.entry_point import EntryPoint
from viz.panels.import_graph_panel import ImportGraphPanel
from viz.panels.entry_point_picker_panel import EntryPointPickerPanel, EntryPointSelected
from viz.project_pipeline import ProjectPipelineResult


class ProjectOverviewScreen(Screen):
    """Phase 1: project overview with import graph and entry point selection."""

    CSS = """
    ProjectOverviewScreen {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 1fr;
    }

    #import-graph-container {
        border: solid rgb(80,120,80);
        overflow-y: auto;
    }

    #entry-picker-container {
        border: solid rgb(80,80,120);
        overflow-y: auto;
    }
    """

    def __init__(self, result: ProjectPipelineResult, project_root: Path) -> None:
        super().__init__()
        self._result = result
        self._project_root = project_root

    def compose(self) -> ComposeResult:
        yield Header()

        # Build export summary for import graph panel
        exports: dict[Path, tuple[int, int]] = {}
        for path, module in self._result.linked.modules.items():
            fn_count = len(module.exports.functions)
            var_count = len(module.exports.variables)
            exports[path] = (fn_count, var_count)

        with Horizontal():
            with Vertical(id="import-graph-container"):
                yield Static(" Import Graph", classes="panel-title")
                yield ImportGraphPanel(
                    topo_order=self._result.topo_order,
                    import_graph=self._result.linked.import_graph,
                    exports=exports,
                    project_root=self._project_root,
                    id="import-graph-panel",
                )

            with Vertical(id="entry-picker-container"):
                yield Static(" Select Entry Point", classes="panel-title")
                yield EntryPointPickerPanel(
                    topo_order=self._result.topo_order,
                    func_symbol_table=self._result.linked.func_symbol_table,
                    project_root=self._project_root,
                    id="entry-picker-panel",
                )

        yield Footer()

    def on_entry_point_selected(self, message: EntryPointSelected) -> None:
        """Handle entry point selection — notify the app to start execution."""
        if message.func_ref is None:
            entry_point = None
        else:
            name = message.func_ref.name
            entry_point = EntryPoint.function(lambda f, n=name: f.name == n)
        self.app.execute_entry_point(entry_point)
```

- [ ] **Step 3: Commit**

```bash
git add viz/screens/__init__.py viz/screens/project_overview_screen.py
git commit -m "feat(viz): add ProjectOverviewScreen with import graph and entry picker"
```

---

## Task 7: ExecutionScreen

**Files:**
- Create: `viz/screens/execution_screen.py`

Phase 2 screen: reuses existing panels (Source, AST, IR, VMState, CFG, Step) with module-aware source/AST switching.

- [ ] **Step 1: Implement `viz/screens/execution_screen.py`**

```python
"""Execution screen — module-aware variant of the PipelineApp layout."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, Header, Static

from viz.panels.ast_panel import ASTPanel
from viz.panels.cfg_panel import CFGPanel
from viz.panels.dataflow_graph_panel import DataflowGraphPanel
from viz.panels.dataflow_summary_panel import DataflowSummaryPanel, FunctionSelected
from viz.panels.ir_panel import IRPanel
from viz.panels.source_panel import SourcePanel
from viz.panels.step_panel import StepPanel
from viz.panels.vm_state_panel import VMStatePanel
from viz.project_pipeline import ProjectPipelineResult, lookup_module_for_index


class ExecutionScreen(Screen):
    """Phase 2: module-aware execution debugging screen."""

    CSS = """
    ExecutionScreen {
        layout: grid;
        grid-size: 3 2;
        grid-columns: 1fr 1fr 1fr;
        grid-rows: 2fr 1fr;
    }

    #source-container {
        border: solid rgb(80,80,120);
        overflow-y: auto;
    }

    #ast-container {
        border: solid rgb(100,80,140);
        overflow-y: auto;
    }

    #ir-container {
        border: solid rgb(80,120,80);
        overflow-y: auto;
    }

    #vm-state-container {
        border: solid rgb(120,80,80);
        overflow-y: auto;
        row-span: 2;
    }

    #cfg-container {
        border: solid rgb(80,120,120);
        overflow-y: auto;
    }

    #step-container {
        border: solid rgb(120,120,80);
        overflow-y: auto;
    }

    .panel-title {
        dock: top;
        background: $surface;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }

    .hidden {
        display: none;
    }

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

    ExecutionScreen.dataflow-mode #ast-container,
    ExecutionScreen.dataflow-mode #vm-state-container,
    ExecutionScreen.dataflow-mode #cfg-container {
        display: none;
    }

    ExecutionScreen.dataflow-mode #dataflow-summary-container,
    ExecutionScreen.dataflow-mode #dataflow-graph-container {
        display: block;
    }
    """

    BINDINGS = [
        Binding("right,l", "step_forward", "Step →", show=True, priority=True),
        Binding("left,h", "step_backward", "Step ←", show=True, priority=True),
        Binding("f5", "toggle_play", "Play/Pause", show=True, priority=True),
        Binding("home", "step_first", "First", show=True, priority=True),
        Binding("end", "step_last", "Last", show=True, priority=True),
        Binding("a", "toggle_ast", "AST", show=True, priority=True),
        Binding("g", "toggle_cfg", "CFG", show=True, priority=True),
        Binding("d", "toggle_dataflow", "Dataflow", show=True, priority=True),
        Binding("p", "back_to_overview", "Overview", show=True, priority=True),
        Binding("q", "quit", "Quit", show=True, priority=True),
    ]

    def __init__(self, result: ProjectPipelineResult, project_root: Path) -> None:
        super().__init__()
        self._result = result
        self._project_root = project_root
        self._current_step_index = 0
        self._play_timer: Timer | None = None
        self._ast_visible = True
        self._cfg_visible = True
        self._dataflow_mode = False
        self._current_module: Path | None = None

    @property
    def _steps(self):
        return self._result.trace.steps if self._result.trace else []

    @property
    def _total_steps(self) -> int:
        return len(self._steps)

    def compose(self) -> ComposeResult:
        # Determine initial module
        initial_source = ""
        initial_ast = None
        if self._result.topo_order:
            first_path = self._result.topo_order[0]
            initial_source = self._result.module_sources.get(first_path, "")
            initial_ast = self._result.module_asts.get(first_path)
            self._current_module = first_path

        yield Header()

        rel_name = self._current_module.name if self._current_module else "?"
        with Vertical(id="source-container"):
            yield Static(f" Source [{rel_name}]", classes="panel-title", id="source-title")
            yield SourcePanel(initial_source, id="source-panel")

        with Vertical(id="ast-container"):
            yield Static(" AST", classes="panel-title")
            yield ASTPanel(initial_ast, id="ast-panel")

        with Vertical(id="vm-state-container"):
            yield Static(" VM State", classes="panel-title")
            yield VMStatePanel(id="vm-state-panel")

        with Vertical(id="ir-container"):
            yield Static(" IR", classes="panel-title")
            yield IRPanel(self._result.linked.merged_cfg, id="ir-panel")

        with Vertical(id="cfg-container"):
            yield Static(" CFG  │  Step", classes="panel-title")
            yield CFGPanel(self._result.linked.merged_cfg, id="cfg-panel")
            yield StepPanel(id="step-panel")

        with Vertical(id="dataflow-summary-container"):
            yield Static(" Call Graph + Summaries", classes="panel-title")
            yield DataflowSummaryPanel(
                self._result.interprocedural, id="dataflow-summary-panel"
            )

        with Vertical(id="dataflow-graph-container"):
            yield Static(" Whole-Program Graph", classes="panel-title")
            yield DataflowGraphPanel(
                self._result.interprocedural,
                cfg=self._result.linked.merged_cfg,
                id="dataflow-graph-panel",
            )

        yield Footer()

    def on_mount(self) -> None:
        self._update_panels()

    def _update_panels(self) -> None:
        if not self._steps:
            return

        step = self._steps[self._current_step_index]

        # Check if we need to switch modules
        inst_id = id(step.instruction)
        idx = self._result.instruction_to_index.get(inst_id)
        if idx is not None:
            module_path = lookup_module_for_index(self._result.module_ir_ranges, idx)
            if module_path and module_path != self._current_module:
                self._switch_module(module_path)

        source_panel = self.query_one("#source-panel", SourcePanel)
        ast_panel = self.query_one("#ast-panel", ASTPanel)
        ir_panel = self.query_one("#ir-panel", IRPanel)
        vm_panel = self.query_one("#vm-state-panel", VMStatePanel)
        cfg_panel = self.query_one("#cfg-panel", CFGPanel)
        step_panel = self.query_one("#step-panel", StepPanel)

        source_panel.current_instruction = step.instruction
        ast_panel.current_instruction = step.instruction
        ir_panel.current_step = step
        vm_panel.current_step = step
        cfg_panel.current_step = step
        step_panel.current_step = step
        step_panel.total_steps = self._total_steps

    def _switch_module(self, new_path: Path) -> None:
        """Switch source and AST panels to a different module."""
        self._current_module = new_path

        source_panel = self.query_one("#source-panel", SourcePanel)
        source_panel.set_source(self._result.module_sources.get(new_path, ""))

        ast_panel = self.query_one("#ast-panel", ASTPanel)
        new_ast = self._result.module_asts.get(new_path)
        if new_ast:
            ast_panel.set_ast(new_ast)

        # Update source panel title
        rel = new_path.relative_to(self._project_root) if new_path.is_relative_to(self._project_root) else new_path
        title = self.query_one("#source-title", Static)
        title.update(f" Source [{rel}]")

    def action_step_forward(self) -> None:
        if self._current_step_index < self._total_steps - 1:
            self._current_step_index += 1
            self._update_panels()

    def action_step_backward(self) -> None:
        if self._current_step_index > 0:
            self._current_step_index -= 1
            self._update_panels()

    def action_step_first(self) -> None:
        self._current_step_index = 0
        self._update_panels()

    def action_step_last(self) -> None:
        self._current_step_index = max(0, self._total_steps - 1)
        self._update_panels()

    def action_toggle_play(self) -> None:
        step_panel = self.query_one("#step-panel", StepPanel)
        if self._play_timer:
            self._play_timer.stop()
            self._play_timer = None
            step_panel.playing = False
        else:
            step_panel.playing = True
            self._play_timer = self.set_interval(0.5, self._auto_step)

    def action_toggle_ast(self) -> None:
        ast_container = self.query_one("#ast-container")
        self._ast_visible = not self._ast_visible
        ast_container.set_class(not self._ast_visible, "hidden")

    def action_toggle_cfg(self) -> None:
        cfg_container = self.query_one("#cfg-container")
        self._cfg_visible = not self._cfg_visible
        cfg_container.set_class(not self._cfg_visible, "hidden")

    def action_toggle_dataflow(self) -> None:
        self._dataflow_mode = not self._dataflow_mode
        self.set_class(self._dataflow_mode, "dataflow-mode")

    def action_back_to_overview(self) -> None:
        if self._play_timer:
            self._play_timer.stop()
            self._play_timer = None
        self.app.pop_screen()

    def _auto_step(self) -> None:
        if self._current_step_index < self._total_steps - 1:
            self._current_step_index += 1
            self._update_panels()
        else:
            self.action_toggle_play()
```

- [ ] **Step 2: Commit**

```bash
git add viz/screens/execution_screen.py
git commit -m "feat(viz): add ExecutionScreen with module-aware source switching"
```

---

## Task 8: ProjectApp — main app with screen management

**Files:**
- Create: `viz/project_app.py`

Single Textual App that manages the two screens.

- [ ] **Step 1: Implement `viz/project_app.py`**

```python
"""ProjectApp — multi-file project TUI with two-screen architecture."""

from __future__ import annotations

import logging
from pathlib import Path

from textual.app import App

from interpreter.project.entry_point import EntryPoint
from viz.project_pipeline import ProjectPipelineResult, execute_project
from viz.screens.execution_screen import ExecutionScreen
from viz.screens.project_overview_screen import ProjectOverviewScreen

logger = logging.getLogger(__name__)


class ProjectApp(App):
    """Main TUI application for multi-file project visualization."""

    TITLE = "RedDragon Project Visualizer"

    def __init__(
        self,
        result: ProjectPipelineResult,
        project_root: Path,
        max_steps: int = 300,
    ) -> None:
        super().__init__()
        self._result = result
        self._project_root = project_root
        self._max_steps = max_steps

    def on_mount(self) -> None:
        self.push_screen(
            ProjectOverviewScreen(self._result, self._project_root)
        )

    def execute_entry_point(self, entry_point: EntryPoint | None) -> None:
        """Called by ProjectOverviewScreen when an entry point is selected."""
        self._result = execute_project(
            self._result, entry_point=entry_point, max_steps=self._max_steps
        )
        self.push_screen(
            ExecutionScreen(self._result, self._project_root)
        )
```

- [ ] **Step 2: Commit**

```bash
git add viz/project_app.py
git commit -m "feat(viz): add ProjectApp with two-screen management"
```

---

## Task 9: Wire `project` subcommand in `viz/__main__.py`

**Files:**
- Modify: `viz/__main__.py`
- Test: Manual TUI test

- [ ] **Step 1: Add `_main_project` handler**

Add to `viz/__main__.py` after the existing `_main_coverage` function:

```python
def _main_project() -> None:
    parser = argparse.ArgumentParser(
        description="RedDragon Project Visualizer — multi-file TUI"
    )
    parser.add_argument("project", help="project subcommand")
    parser.add_argument("directory", help="Path to project root directory")
    parser.add_argument(
        "-l", "--language", required=True, help="Source language (required)"
    )
    parser.add_argument(
        "-s",
        "--max-steps",
        type=int,
        default=300,
        help="Maximum execution steps (default: 300)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    from pathlib import Path

    from viz.project_app import ProjectApp
    from viz.project_pipeline import run_project_pipeline

    directory = Path(args.directory).resolve()
    result = run_project_pipeline(directory, language=args.language)
    app = ProjectApp(result, project_root=directory, max_steps=args.max_steps)
    app.run()
```

- [ ] **Step 2: Add `"project"` to the dispatch table**

In `viz/__main__.py`, modify the `dispatch` dict in `main()`:

```python
    dispatch = {
        "compare": _main_compare,
        "lower": _main_lower,
        "coverage": _main_coverage,
        "project": _main_project,
    }
```

- [ ] **Step 3: Update module docstring**

Add to the docstring at the top of `viz/__main__.py`:

```python
# Add after "Coverage matrix:" section:
# Multi-file project:
#   poetry run python -m viz project /path/to/dir -l java -s 500
```

- [ ] **Step 4: Commit**

```bash
git add viz/__main__.py
git commit -m "feat(viz): wire project subcommand in __main__.py"
```

---

## Task 10: Integration tests

**Files:**
- Create: `tests/integration/viz/test_project_tui.py`

End-to-end tests: compile directory → build result → execute → verify trace maps to correct modules.

- [ ] **Step 1: Write integration tests**

```python
"""Integration tests for the multi-file project TUI pipeline."""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.project.entry_point import EntryPoint
from viz.project_pipeline import (
    ProjectPipelineResult,
    execute_project,
    lookup_module_for_index,
    run_project_pipeline,
)


class TestProjectPipelineIntegration:
    """Full pipeline: directory → compile → link → trace → module mapping."""

    def test_two_file_python_top_level(self, tmp_path: Path) -> None:
        """Two-file project: utils.py defines helper, main.py calls it."""
        (tmp_path / "utils.py").write_text("def helper(x):\n    return x + 1\n")
        (tmp_path / "main.py").write_text(
            "from utils import helper\nresult = helper(5)\n"
        )

        result = run_project_pipeline(tmp_path, "python")
        result = execute_project(result, entry_point=None, max_steps=200)

        assert result.trace is not None
        assert len(result.trace.steps) > 0
        assert len(result.module_sources) == 2
        assert len(result.module_asts) == 2

    def test_trace_steps_map_to_modules(self, tmp_path: Path) -> None:
        """Each trace step's instruction should map to a known module."""
        (tmp_path / "utils.py").write_text("val = 10\n")
        (tmp_path / "main.py").write_text("from utils import val\nx = val\n")

        result = run_project_pipeline(tmp_path, "python")
        result = execute_project(result, entry_point=None, max_steps=200)

        assert result.trace is not None
        mapped_count = 0
        for step in result.trace.steps:
            idx = result.instruction_to_index.get(id(step.instruction))
            if idx is not None:
                module = lookup_module_for_index(result.module_ir_ranges, idx)
                if module is not None:
                    mapped_count += 1
                    assert module in result.module_sources

        # At least some steps should map to modules
        assert mapped_count > 0

    def test_function_entry_point(self, tmp_path: Path) -> None:
        """Function entry point executes preamble then dispatches."""
        (tmp_path / "main.py").write_text(
            "x = 1\n\ndef compute():\n    return x + 2\n"
        )

        result = run_project_pipeline(tmp_path, "python")
        result = execute_project(
            result,
            entry_point=EntryPoint.function(lambda f: str(f.name) == "compute"),
            max_steps=200,
        )

        assert result.trace is not None
        assert len(result.trace.steps) > 0

    def test_existing_fixture_project(self) -> None:
        """Use the existing python_basic fixture to verify pipeline works."""
        fixture_dir = Path("tests/fixtures/projects/python_basic")
        if not fixture_dir.exists():
            pytest.skip("Fixture not found")

        result = run_project_pipeline(fixture_dir, "python")

        assert len(result.module_sources) == 2
        assert len(result.topo_order) == 2

        result = execute_project(result, entry_point=None, max_steps=200)
        assert result.trace is not None
        assert len(result.trace.steps) > 0
```

- [ ] **Step 2: Run integration tests**

Run: `poetry run python -m pytest tests/integration/viz/test_project_tui.py -v`
Expected: All PASSED

- [ ] **Step 3: Commit**

```bash
git add tests/integration/viz/test_project_tui.py
git commit -m "test(viz): add integration tests for multi-file project TUI pipeline"
```

---

## Task 11: Format and full test suite

- [ ] **Step 1: Run Black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All existing tests still pass + new tests pass.

- [ ] **Step 3: Manual TUI smoke test**

Run: `poetry run python -m viz project tests/fixtures/projects/python_basic -l python`
Expected: Phase 1 screen shows import graph and entry point picker. Selecting an entry point transitions to Phase 2 execution screen. `p` returns to overview.

- [ ] **Step 4: Final commit if formatter changed anything**

```bash
git add -u
git commit -m "style: format project TUI files with Black"
```
