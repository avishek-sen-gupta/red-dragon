"""Lowering trace app — interactive TUI for exploring AST→IR lowering."""

from __future__ import annotations

import logging

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from viz.lowering_trace import LoweringEvent, LoweringResult
from viz.panels.lowering_panel import LoweringPanel
from viz.panels.source_panel import SourcePanel

logger = logging.getLogger(__name__)


class LoweringIRPanel(Static):
    """Displays IR instructions emitted by the currently selected lowering event."""

    def __init__(self, **kwargs) -> None:
        super().__init__("Select a node in the lowering trace", **kwargs)
        self._event: LoweringEvent | None = None

    def set_event(self, event: LoweringEvent | None) -> None:
        self._event = event
        self._render_detail()

    def _render_detail(self) -> None:
        if not self._event:
            self.update("[dim]Select a node in the lowering trace[/dim]")
            return

        text = Text()
        text.append(f"  Handler: ", style="dim")
        text.append(f"{self._event.handler_name}", style="bold cyan")
        text.append(f" ({self._event.handler_module})\n", style="dim")
        text.append(f"  Node: ", style="dim")
        text.append(f"{self._event.ast_node_type}", style="bold")
        text.append(f"  Dispatch: ", style="dim")
        text.append(f"{self._event.dispatch_type}\n", style="yellow")
        text.append(f"  Source: ", style="dim")
        text.append(f"L{self._event.start_line}:{self._event.start_col}")
        text.append(f" → L{self._event.end_line}:{self._event.end_col}\n")
        text.append("\n")

        if self._event.instructions_emitted:
            text.append(
                f"  Emitted {len(self._event.instructions_emitted)} instructions:\n",
                style="bold green",
            )
            for inst in self._event.instructions_emitted:
                text.append(f"    {inst}\n")
        else:
            text.append("  [dim]No instructions emitted directly[/dim]\n")

        if self._event.children:
            text.append(
                f"\n  {len(self._event.children)} child handler(s)\n", style="dim"
            )

        self.update(text)


class LoweringFullIRPanel(Static):
    """Displays the complete IR output from the lowering pass."""

    def __init__(self, result: LoweringResult, **kwargs) -> None:
        super().__init__("Loading IR...", **kwargs)
        self._result = result

    def on_mount(self) -> None:
        text = Text()
        text.append(f"  {len(self._result.ir)} instructions total\n\n", style="bold")
        for inst in self._result.ir:
            text.append(f"  {inst}\n")
        self.update(text)


class LoweringApp(App):
    """TUI for exploring how the frontend lowers AST to IR."""

    TITLE = "RedDragon Lowering Trace"

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-columns: 1fr 1fr;
        grid-rows: 1fr 1fr;
    }

    #source-container {
        border: solid rgb(80,80,120);
        overflow-y: auto;
    }

    #trace-container {
        border: solid rgb(100,80,140);
        overflow-y: auto;
    }

    #detail-container {
        border: solid rgb(80,120,80);
        overflow-y: auto;
    }

    #ir-container {
        border: solid rgb(120,80,80);
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
        Binding("q", "quit", "Quit", show=True),
        Binding("t", "toggle_ir", "Full IR", show=True),
    ]

    def __init__(self, result: LoweringResult) -> None:
        super().__init__()
        self._result = result
        self._ir_visible = True

    def compose(self) -> ComposeResult:
        yield Header()

        with Vertical(id="source-container"):
            yield Static(f" Source ({self._result.language})", classes="panel-title")
            yield SourcePanel(self._result.source, id="source-panel")

        with Vertical(id="trace-container"):
            yield Static(" Lowering Trace", classes="panel-title")
            yield LoweringPanel(self._result.events, id="lowering-panel")

        with Vertical(id="detail-container"):
            yield Static(" Handler Detail", classes="panel-title")
            yield LoweringIRPanel(id="detail-panel")

        with Vertical(id="ir-container"):
            yield Static(" Full IR Output", classes="panel-title")
            yield LoweringFullIRPanel(self._result, id="full-ir-panel")

        yield Footer()

    def on_tree_node_selected(self, event) -> None:
        """When a lowering tree node is selected, show its details."""
        data = event.node.data
        if isinstance(data, LoweringEvent):
            detail = self.query_one("#detail-panel", LoweringIRPanel)
            detail.set_event(data)

            # Highlight source location
            source_panel = self.query_one("#source-panel", SourcePanel)
            source_panel.highlight_lines(data.start_line, data.end_line)

    def action_toggle_ir(self) -> None:
        ir_container = self.query_one("#ir-container")
        self._ir_visible = not self._ir_visible
        ir_container.set_class(not self._ir_visible, "hidden")
