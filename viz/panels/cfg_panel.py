"""CFG panel — displays block list with current block highlighted."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from interpreter.cfg_types import CFG
from interpreter.trace_types import TraceStep


class CFGPanel(Static):
    """Displays CFG blocks as a labelled list with the current block highlighted."""

    current_step: reactive[TraceStep | None] = reactive(None)

    def __init__(self, cfg: CFG | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cfg = cfg

    def set_cfg(self, cfg: CFG) -> None:
        self._cfg = cfg
        self._render_cfg()

    def watch_current_step(self, step: TraceStep | None) -> None:
        self._render_cfg()

    def _render_cfg(self) -> None:
        if not self._cfg:
            self.update("[dim]No CFG loaded[/dim]")
            return

        step = self.current_step
        current_block = step.block_label if step else ""

        text = Text()
        for label, block in self._cfg.blocks.items():
            is_current = label == current_block
            marker = " ► " if is_current else "   "
            style = "bold yellow" if is_current else ""

            text.append(marker, style=style)
            text.append(f"[{label}]", style=style or "cyan")

            if block.successors:
                text.append(" → ", style="dim")
                text.append(", ".join(block.successors), style="dim")

            inst_count = len(block.instructions)
            text.append(f"  ({inst_count} inst)", style="dim")
            text.append("\n")

        self.update(text)
