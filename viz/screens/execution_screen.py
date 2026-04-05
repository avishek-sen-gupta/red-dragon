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
from viz.panels.dataflow_summary_panel import DataflowSummaryPanel
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
            yield Static(
                f" Source [{rel_name}]", classes="panel-title", id="source-title"
            )
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

        try:
            rel = new_path.relative_to(self._project_root)
        except ValueError:
            rel = new_path
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
