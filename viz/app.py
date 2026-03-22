"""RedDragon Pipeline Visualizer — interactive TUI for stepping through execution."""

from __future__ import annotations

import sys
import logging

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Footer, Header, Static

from viz.panels.source_panel import SourcePanel
from viz.panels.ast_panel import ASTPanel
from viz.panels.ir_panel import IRPanel
from viz.panels.vm_state_panel import VMStatePanel
from viz.panels.cfg_panel import CFGPanel
from viz.panels.step_panel import StepPanel
from viz.panels.dataflow_summary_panel import DataflowSummaryPanel, FunctionSelected
from viz.panels.dataflow_graph_panel import DataflowGraphPanel
from viz.pipeline import PipelineResult, run_pipeline

logger = logging.getLogger(__name__)


class PipelineApp(App):
    """Main TUI application for the RedDragon pipeline visualizer."""

    TITLE = "RedDragon Pipeline Visualizer"

    CSS = """
    Screen {
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

    /* Focus: brighten border on focused container, dim on unfocused */
    Vertical:focus-within {
        border: solid rgb(200,200,255);
    }

    /* Override Tree's built-in focus styling to match container approach */
    Tree:focus {
        border: none;
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

    Screen.dataflow-mode {
        grid-size: 2 2;
        grid-columns: 1fr 2fr;
        grid-rows: 1fr 1fr;
    }

    Screen.dataflow-mode #ast-container,
    Screen.dataflow-mode #vm-state-container,
    Screen.dataflow-mode #cfg-container {
        display: none;
    }

    Screen.dataflow-mode #dataflow-summary-container,
    Screen.dataflow-mode #dataflow-graph-container {
        display: block;
    }
    """

    BINDINGS = [
        Binding("right,l", "step_forward", "Step →", show=True, priority=True),
        Binding("left,h", "step_backward", "Step ←", show=True, priority=True),
        Binding("space", "toggle_play", "Play/Pause", show=True, priority=True),
        Binding("home", "step_first", "First", show=True, priority=True),
        Binding("end", "step_last", "Last", show=True, priority=True),
        Binding("a", "toggle_ast", "AST", show=True, priority=True),
        Binding("g", "toggle_cfg", "CFG", show=True, priority=True),
        Binding("d", "toggle_dataflow", "Dataflow", show=True, priority=True),
        Binding("q", "quit", "Quit", show=True, priority=True),
    ]

    def __init__(self, result: PipelineResult) -> None:
        super().__init__()
        self._result = result
        self._current_step_index = 0
        self._play_timer: Timer | None = None
        self._ast_visible = True
        self._cfg_visible = True
        self._dataflow_mode = False
        self._saved_instruction = None

    @property
    def _steps(self):
        return self._result.trace.steps

    @property
    def _total_steps(self) -> int:
        return len(self._steps)

    def compose(self) -> ComposeResult:
        yield Header()

        with Vertical(id="source-container"):
            yield Static(f" Source ({self._result.language})", classes="panel-title")
            yield SourcePanel(self._result.source, id="source-panel")

        with Vertical(id="ast-container"):
            yield Static(" AST", classes="panel-title")
            yield ASTPanel(self._result.ast, id="ast-panel")

        with Vertical(id="vm-state-container"):
            yield Static(" VM State", classes="panel-title")
            yield VMStatePanel(id="vm-state-panel")

        with Vertical(id="ir-container"):
            yield Static(" IR", classes="panel-title")
            yield IRPanel(self._result.cfg, id="ir-panel")

        with Vertical(id="cfg-container"):
            yield Static(" CFG  │  Step", classes="panel-title")
            yield CFGPanel(self._result.cfg, id="cfg-panel")
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
                cfg=self._result.cfg,
                id="dataflow-graph-panel",
            )

        yield Footer()

    def on_mount(self) -> None:
        self._update_panels()

    def _update_panels(self) -> None:
        if not self._steps:
            return

        step = self._steps[self._current_step_index]
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
        self.screen.set_class(self._dataflow_mode, "dataflow-mode")

        source_panel = self.query_one("#source-panel", SourcePanel)
        ir_panel = self.query_one("#ir-panel", IRPanel)

        if self._dataflow_mode:
            self._saved_instruction = source_panel.current_instruction
            source_panel.current_instruction = None
            ir_panel.highlight_block(None)
        else:
            source_panel._highlight_start = -1
            source_panel._highlight_end = -1
            ir_panel.highlight_block(None)
            if self._saved_instruction:
                source_panel.current_instruction = self._saved_instruction
            self._update_panels()

    def on_function_selected(self, message: FunctionSelected) -> None:
        """Cross-highlight source and IR when a function is selected in the dataflow tree."""
        cfg = self._result.cfg
        label = message.label

        ir_panel = self.query_one("#ir-panel", IRPanel)
        ir_panel.highlight_block(label)

        source_panel = self.query_one("#source-panel", SourcePanel)
        min_line = float("inf")
        max_line = 0
        for block_label, block in cfg.blocks.items():
            if block_label == label or block_label.startswith(label + "_"):
                for inst in block.instructions:
                    loc = inst.source_location
                    if loc.is_unknown():
                        continue
                    min_line = min(min_line, loc.start_line)
                    max_line = max(max_line, loc.end_line)

        if max_line > 0:
            source_panel.highlight_lines(int(min_line), int(max_line))

    def _auto_step(self) -> None:
        if self._current_step_index < self._total_steps - 1:
            self._current_step_index += 1
            self._update_panels()
        else:
            self.action_toggle_play()


def main() -> None:
    """Entry point: parse CLI args and launch the TUI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="RedDragon Pipeline Visualizer — interactive TUI"
    )
    parser.add_argument("source_file", help="Path to source file to visualize")
    parser.add_argument(
        "-l",
        "--language",
        default="python",
        help="Source language (default: python)",
    )
    parser.add_argument(
        "-s",
        "--max-steps",
        type=int,
        default=300,
        help="Maximum execution steps (default: 300)",
    )
    args = parser.parse_args()

    with open(args.source_file) as f:
        source = f.read()

    logging.basicConfig(level=logging.WARNING)
    result = run_pipeline(source, language=args.language, max_steps=args.max_steps)
    app = PipelineApp(result)
    app.run()


if __name__ == "__main__":
    main()
