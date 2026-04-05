"""CFG panel — displays block graph with edges and current block highlighted."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from interpreter.cfg_types import CFG
from interpreter.ir import Opcode
from interpreter.trace_types import TraceStep


class CFGPanel(Static):
    """Displays CFG blocks as a graph with box-drawing edges."""

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
        blocks = list(self._cfg.blocks.items())

        for idx, (label, block) in enumerate(blocks):
            is_current = label == current_block
            is_last = idx == len(blocks) - 1

            # Block box
            box_style = "bold yellow" if is_current else "cyan"
            marker = "►" if is_current else " "

            # Top border
            label_str = str(label)
            width = max(len(label_str) + 4, 20)
            text.append(f"  {marker} ", style=box_style)
            text.append("┌" + "─" * width + "┐\n", style=box_style)

            # Block label
            text.append("    ", style=box_style)
            padded = f" {label_str} ".ljust(width)
            text.append("│", style=box_style)
            text.append(padded, style="bold white" if is_current else "cyan bold")
            text.append("│\n", style=box_style)

            # Instruction summary (truncated)
            inst_count = len(block.instructions)
            terminator = _block_terminator(block)
            summary = f" {inst_count} inst"
            if terminator:
                summary += f" │ {terminator}"
            text.append("    ", style=box_style)
            text.append("│", style=box_style)
            text.append(summary.ljust(width), style="dim" if not is_current else "")
            text.append("│\n", style=box_style)

            # Bottom border
            text.append("    ", style=box_style)
            text.append("└" + "─" * width + "┘\n", style=box_style)

            # Edge arrows to successors
            if block.successors:
                for i, succ in enumerate(block.successors):
                    is_last_succ = i == len(block.successors) - 1
                    connector = "└" if is_last_succ else "├"
                    edge_label = _edge_label(block, i)
                    text.append(f"    {connector}──", style="dim green")
                    if edge_label:
                        text.append(f"[{edge_label}]", style="dim yellow")
                    text.append("──▸ ", style="dim green")
                    text.append(f"{succ}\n", style="green")

            if not is_last:
                text.append("\n")

        self.update(text)


def _block_terminator(block) -> str:
    """Get a short description of the block's terminating instruction."""
    if not block.instructions:
        return ""
    last = block.instructions[-1]
    if last.opcode == Opcode.BRANCH_IF:
        return "branch_if"
    if last.opcode == Opcode.BRANCH:
        return "branch"
    if last.opcode == Opcode.RETURN:
        return "return"
    if last.opcode == Opcode.THROW:
        return "throw"
    return ""


def _edge_label(block, succ_idx: int) -> str:
    """Label for a CFG edge (T/F for conditional branches)."""
    if not block.instructions:
        return ""
    last = block.instructions[-1]
    if last.opcode == Opcode.BRANCH_IF and len(block.successors) == 2:
        return "T" if succ_idx == 0 else "F"
    return ""
