"""IR panel — displays IR instructions grouped by CFG block with current step highlighted."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from interpreter.cfg_types import CFG
from interpreter.ir import Opcode
from interpreter.trace_types import TraceStep


class IRPanel(Static):
    """Displays IR instructions grouped by CFG block, highlighting the current step."""

    current_step: reactive[TraceStep | None] = reactive(None)

    def __init__(self, cfg: CFG | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cfg = cfg

    def set_cfg(self, cfg: CFG) -> None:
        self._cfg = cfg
        self._render_ir()

    def watch_current_step(self, step: TraceStep | None) -> None:
        self._render_ir()

    def _render_ir(self) -> None:
        if not self._cfg:
            self.update("[dim]No IR loaded[/dim]")
            return

        step = self.current_step
        current_block = step.block_label if step else ""
        current_idx = step.instruction_index if step else -1

        text = Text()
        for label, block in self._cfg.blocks.items():
            # Block header
            is_current_block = label == current_block
            header_style = "bold cyan" if is_current_block else "dim cyan"
            text.append(f"  {label}:", style=header_style)
            succs = ", ".join(block.successors)
            if succs:
                text.append(f"  → {succs}", style="dim")
            text.append("\n")

            # Instructions
            for i, inst in enumerate(block.instructions):
                is_current = is_current_block and i == current_idx
                marker = " ► " if is_current else "   "

                if is_current:
                    text.append(marker, style="bold yellow")
                    text.append(f"{inst}\n", style="bold white on rgb(40,40,80)")
                elif inst.opcode == Opcode.LABEL:
                    continue  # labels are shown as block headers
                else:
                    text.append(marker, style="dim")
                    text.append(f"{inst}\n")

            text.append("\n")

        self.update(text)
