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
from viz.panels.ir_panel import IRPanel
from viz.panels.vm_state_panel import VMStatePanel
from viz.panels.cfg_panel import CFGPanel
from viz.panels.step_panel import StepPanel
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
    """

    BINDINGS = [
        Binding("right,l", "step_forward", "Step →", show=True),
        Binding("left,h", "step_backward", "Step ←", show=True),
        Binding("space", "toggle_play", "Play/Pause", show=True),
        Binding("home", "step_first", "First", show=True),
        Binding("end", "step_last", "Last", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, result: PipelineResult) -> None:
        super().__init__()
        self._result = result
        self._current_step_index = 0
        self._play_timer: Timer | None = None

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

        with Vertical(id="ir-container"):
            yield Static(" IR", classes="panel-title")
            yield IRPanel(self._result.cfg, id="ir-panel")

        with Vertical(id="vm-state-container"):
            yield Static(" VM State", classes="panel-title")
            yield VMStatePanel(id="vm-state-panel")

        with Vertical(id="cfg-container"):
            yield Static(" CFG", classes="panel-title")
            yield CFGPanel(self._result.cfg, id="cfg-panel")

        with Vertical(id="step-container"):
            yield Static(" Step", classes="panel-title")
            yield StepPanel(id="step-panel")

        yield Footer()

    def on_mount(self) -> None:
        self._update_panels()

    def _update_panels(self) -> None:
        if not self._steps:
            return

        step = self._steps[self._current_step_index]
        source_panel = self.query_one("#source-panel", SourcePanel)
        ir_panel = self.query_one("#ir-panel", IRPanel)
        vm_panel = self.query_one("#vm-state-panel", VMStatePanel)
        cfg_panel = self.query_one("#cfg-panel", CFGPanel)
        step_panel = self.query_one("#step-panel", StepPanel)

        source_panel.current_instruction = step.instruction
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
