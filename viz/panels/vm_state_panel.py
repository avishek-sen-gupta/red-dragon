"""VM State panel — displays heap, locals, and registers with diff highlighting."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from interpreter.trace_types import TraceStep
from interpreter.types.typed_value import TypedValue
from interpreter.vm_types import HeapObject, Pointer, SymbolicValue


def _format_value(val: object) -> str:
    """Format a VM value for display."""
    if isinstance(val, TypedValue):
        return _format_value(val.value)
    if isinstance(val, SymbolicValue):
        return f"sym:{val.name}"
    if isinstance(val, Pointer):
        return f"→ {val.base}[{val.offset}]"
    if isinstance(val, HeapObject):
        return f"<{val.type_hint or 'obj'}>"
    if isinstance(val, str) and len(val) > 40:
        return f'"{val[:37]}..."'
    if isinstance(val, str):
        return f'"{val}"'
    return repr(val)


class VMStatePanel(Static):
    """Displays the VM state (stack frames, heap) with diff highlighting."""

    current_step: reactive[TraceStep | None] = reactive(None)

    def watch_current_step(self, step: TraceStep | None) -> None:
        self._render_state()

    def _render_state(self) -> None:
        step = self.current_step
        if not step:
            self.update("[dim]No execution state[/dim]")
            return

        vm = step.vm_state
        update = step.update
        changed_regs = set(update.register_writes.keys()) if update else set()
        changed_vars = set(update.var_writes.keys()) if update else set()
        changed_heap_fields = {
            (hw.obj_addr, hw.field) for hw in (update.heap_writes if update else [])
        }

        text = Text()

        # Stack frames (most recent first)
        for frame_idx, frame in enumerate(reversed(vm.call_stack)):
            is_current = frame_idx == 0
            marker = "▸" if is_current else "▹"
            style = "bold" if is_current else "dim"
            text.append(f"  {marker} ", style=style)
            text.append(f"Frame: {frame.function_name}\n", style=style)

            # Local variables
            if frame.local_vars:
                text.append("    locals:\n", style="dim")
                for var, val in sorted(frame.local_vars.items()):
                    val_str = _format_value(val)
                    if is_current and var in changed_vars:
                        text.append(f"      {var}: ", style="green bold")
                        text.append(f"{val_str}\n", style="green bold")
                    else:
                        text.append(f"      {var}: ", style="")
                        text.append(f"{val_str}\n", style="dim")

            # Registers (only show current frame, collapse if many)
            if is_current and frame.registers:
                text.append("    registers:\n", style="dim")
                for reg, val in sorted(frame.registers.items()):
                    val_str = _format_value(val)
                    if reg in changed_regs:
                        text.append(f"      {reg}: ", style="green bold")
                        text.append(f"{val_str}\n", style="green bold")
                    else:
                        text.append(f"      {reg}: ", style="dim")
                        text.append(f"{val_str}\n", style="dim")

            text.append("\n")

        # Heap
        if vm.heap:
            text.append("  Heap:\n", style="bold magenta")
            for addr, obj in sorted(vm.heap.items()):
                type_hint = obj.type_hint or ""
                text.append(f"    {addr}", style="magenta")
                if type_hint:
                    text.append(f" ({type_hint})", style="dim magenta")
                text.append(":\n")
                for field_name, val in sorted(obj.fields.items()):
                    val_str = _format_value(val)
                    if (addr, field_name) in changed_heap_fields:
                        text.append(
                            f"      .{field_name} = {val_str}\n", style="green bold"
                        )
                    else:
                        text.append(f"      .{field_name} = {val_str}\n", style="dim")

        self.update(text)
