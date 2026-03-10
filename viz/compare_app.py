"""Compare mode — side-by-side pipeline visualization for multiple languages."""

from __future__ import annotations

import logging

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Footer, Header, Static

from viz.panels.source_panel import SourcePanel
from viz.panels.ir_panel import IRPanel
from viz.panels.step_panel import StepPanel
from viz.pipeline import PipelineResult, run_pipeline

logger = logging.getLogger(__name__)


class CompareApp(App):
    """Side-by-side comparison of pipeline execution across languages."""

    TITLE = "RedDragon Pipeline Comparator"

    CSS = """
    Screen {
        layout: vertical;
    }

    #compare-columns {
        height: 1fr;
    }

    .lang-column {
        width: 1fr;
        border: solid rgb(80,80,120);
        overflow-y: auto;
    }

    .panel-title {
        dock: top;
        background: $surface;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }

    .source-section {
        height: auto;
        max-height: 40%;
        border-bottom: solid rgb(60,60,60);
        overflow-y: auto;
    }

    .ir-section {
        height: auto;
        max-height: 40%;
        border-bottom: solid rgb(60,60,60);
        overflow-y: auto;
    }

    .step-section {
        height: auto;
        overflow-y: auto;
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

    def __init__(self, results: list[PipelineResult]) -> None:
        super().__init__()
        self._results = results
        self._current_step_indices = [0] * len(results)
        self._play_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="compare-columns"):
            for i, result in enumerate(self._results):
                with Vertical(classes="lang-column"):
                    with Vertical(classes="source-section"):
                        yield Static(
                            f" {result.language.upper()} — Source",
                            classes="panel-title",
                        )
                        yield SourcePanel(result.source, id=f"source-{i}")
                    with Vertical(classes="ir-section"):
                        yield Static(" IR", classes="panel-title")
                        yield IRPanel(result.cfg, id=f"ir-{i}")
                    with Vertical(classes="step-section"):
                        yield Static(" Step", classes="panel-title")
                        yield StepPanel(id=f"step-{i}")

        yield Footer()

    def on_mount(self) -> None:
        self._update_panels()

    def _update_panels(self) -> None:
        for i, result in enumerate(self._results):
            steps = result.trace.steps
            if not steps:
                continue

            idx = min(self._current_step_indices[i], len(steps) - 1)
            step = steps[idx]

            self.query_one(f"#source-{i}", SourcePanel).current_instruction = (
                step.instruction
            )
            self.query_one(f"#ir-{i}", IRPanel).current_step = step
            step_panel = self.query_one(f"#step-{i}", StepPanel)
            step_panel.current_step = step
            step_panel.total_steps = len(steps)

    def action_step_forward(self) -> None:
        for i, result in enumerate(self._results):
            max_idx = len(result.trace.steps) - 1
            if self._current_step_indices[i] < max_idx:
                self._current_step_indices[i] += 1
        self._update_panels()

    def action_step_backward(self) -> None:
        for i in range(len(self._results)):
            if self._current_step_indices[i] > 0:
                self._current_step_indices[i] -= 1
        self._update_panels()

    def action_step_first(self) -> None:
        self._current_step_indices = [0] * len(self._results)
        self._update_panels()

    def action_step_last(self) -> None:
        self._current_step_indices = [
            max(0, len(r.trace.steps) - 1) for r in self._results
        ]
        self._update_panels()

    def action_toggle_play(self) -> None:
        if self._play_timer:
            self._play_timer.stop()
            self._play_timer = None
        else:
            self._play_timer = self.set_interval(0.5, self._auto_step)

    def _auto_step(self) -> None:
        any_advanced = False
        for i, result in enumerate(self._results):
            max_idx = len(result.trace.steps) - 1
            if self._current_step_indices[i] < max_idx:
                self._current_step_indices[i] += 1
                any_advanced = True
        self._update_panels()
        if not any_advanced:
            self.action_toggle_play()
