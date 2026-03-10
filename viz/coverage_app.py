"""Coverage matrix app — cross-language frontend handler availability."""

from __future__ import annotations

import logging

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, Static

from viz.coverage import FrontendCoverage, build_coverage
from viz.panels.coverage_panel import CoveragePanel

logger = logging.getLogger(__name__)


class CoverageApp(App):
    """TUI for exploring frontend dispatch table coverage across languages."""

    TITLE = "RedDragon Frontend Coverage Matrix"

    CSS = """
    #filter-bar {
        dock: top;
        height: 3;
        padding: 0 1;
    }

    #matrix-container {
        overflow-y: auto;
        overflow-x: auto;
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
        Binding("slash", "focus_filter", "Filter", show=True),
        Binding("escape", "clear_filter", "Clear", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, coverages: list[FrontendCoverage]) -> None:
        super().__init__()
        self._coverages = coverages

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(
            placeholder="Type to filter node types...",
            id="filter-bar",
        )
        with Vertical(id="matrix-container"):
            yield Static(
                f" Coverage Matrix — {len(self._coverages)} frontends",
                classes="panel-title",
            )
            yield CoveragePanel(self._coverages, id="coverage-panel")
        yield Footer()

    def on_input_changed(self, event: Input.Changed) -> None:
        panel = self.query_one("#coverage-panel", CoveragePanel)
        panel.set_filter(event.value)

    def action_focus_filter(self) -> None:
        self.query_one("#filter-bar", Input).focus()

    def action_clear_filter(self) -> None:
        filter_input = self.query_one("#filter-bar", Input)
        filter_input.value = ""
        panel = self.query_one("#coverage-panel", CoveragePanel)
        panel.set_filter("")
