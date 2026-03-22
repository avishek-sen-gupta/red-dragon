"""Step panel — displays step counter, delta summary, and reasoning."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from interpreter.trace_types import TraceStep


class StepPanel(Static, can_focus=True):
    """Displays the current step index, instruction delta, and reasoning."""

    current_step: reactive[TraceStep | None] = reactive(None)
    total_steps: reactive[int] = reactive(0)
    playing: reactive[bool] = reactive(False)

    def watch_current_step(self, step: TraceStep | None) -> None:
        self._render_step()

    def watch_playing(self, playing: bool) -> None:
        self._render_step()

    def _render_step(self) -> None:
        step = self.current_step
        if not step:
            self.update("[dim]No trace loaded[/dim]")
            return

        text = Text()

        # Step counter and controls
        play_icon = "⏸ " if self.playing else "▶ "
        text.append(f"  Step {step.step_index + 1}/{self.total_steps}  ", style="bold")
        text.append(play_icon, style="bold cyan")
        text.append("\n")

        # Instruction
        text.append(f"  {step.instruction}\n", style="bold white")

        # Delta summary
        update = step.update
        if update.register_writes:
            for reg, val in update.register_writes.items():
                text.append(f"  Δ reg {reg} = ", style="green")
                text.append(f"{_short_val(val)}\n", style="green bold")

        if update.var_writes:
            for var, val in update.var_writes.items():
                text.append(f"  Δ var {var} = ", style="green")
                text.append(f"{_short_val(val)}\n", style="green bold")

        if update.heap_writes:
            for hw in update.heap_writes:
                text.append(f"  Δ heap {hw.obj_addr}.{hw.field} = ", style="green")
                text.append(f"{_short_val(hw.value)}\n", style="green bold")

        if update.next_label:
            text.append(f"  → {update.next_label}\n", style="cyan")

        if update.call_push:
            text.append(f"  ↳ call {update.call_push.function_name}\n", style="magenta")

        if update.call_pop:
            ret = _short_val(update.return_value) if update.return_value else "(void)"
            text.append(f"  ↲ return {ret}\n", style="magenta")

        # Reasoning
        if update.reasoning:
            text.append(f"  {update.reasoning}\n", style="dim italic")

        # LLM indicator
        if step.used_llm:
            text.append("  [LLM]\n", style="bold red")

        # Key hints
        text.append("\n")
        text.append(
            "  ←/→ step  space play/pause  q quit",
            style="dim",
        )

        self.update(text)


def _short_val(val: object) -> str:
    """Short representation of a value for the delta summary."""
    s = repr(val)
    return s[:60] + "..." if len(s) > 60 else s
