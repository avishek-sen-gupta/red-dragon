"""Source code panel — displays source with current instruction span highlighted."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from interpreter.ir import IRInstruction


class SourcePanel(Static):
    """Displays source code with the current instruction's source span highlighted."""

    current_instruction: reactive[IRInstruction | None] = reactive(None)

    def __init__(self, source: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._source = source
        self._lines = source.splitlines() if source else []

    def set_source(self, source: str) -> None:
        self._source = source
        self._lines = source.splitlines() if source else []
        self._render_source()

    def watch_current_instruction(self, inst: IRInstruction | None) -> None:
        self._render_source()

    def _render_source(self) -> None:
        if not self._lines:
            self.update("[dim]No source loaded[/dim]")
            return

        inst = self.current_instruction
        highlight_start = -1
        highlight_end = -1
        if inst and not inst.source_location.is_unknown():
            highlight_start = inst.source_location.start_line - 1
            highlight_end = inst.source_location.end_line - 1

        text = Text()
        for i, line in enumerate(self._lines):
            line_num = f"{i + 1:>4} "
            if highlight_start <= i <= highlight_end:
                text.append(line_num, style="bold yellow")
                text.append(f"{line}\n", style="bold white on rgb(40,40,80)")
            else:
                text.append(line_num, style="dim")
                text.append(f"{line}\n")

        self.update(text)
