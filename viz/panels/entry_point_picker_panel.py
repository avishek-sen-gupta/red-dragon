"""Entry point picker panel — scrollable list of functions grouped by module."""

from __future__ import annotations

from pathlib import Path

from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from interpreter.ir import CodeLabel
from interpreter.refs.func_ref import FuncRef


class EntryPointSelected(Message):
    """Posted when the user selects an entry point."""

    def __init__(self, func_ref: FuncRef | None) -> None:
        super().__init__()
        self.func_ref = func_ref  # None = top-level execution


def group_entry_points(
    topo_order: list[Path],
    func_symbol_table: dict[CodeLabel, FuncRef],
) -> list[tuple[Path, list[FuncRef]]]:
    """Group function refs by module, ordered by topo_order."""
    result: list[tuple[Path, list[FuncRef]]] = []
    for path in topo_order:
        stem = path.stem
        matched: list[FuncRef] = []
        for label, ref in func_symbol_table.items():
            label_str = str(label)
            if label_str.startswith(stem + ".") or label_str.startswith(stem + "_"):
                matched.append(ref)
        result.append((path, matched))
    return result


class EntryPointPickerPanel(OptionList):
    """Scrollable list of entry points grouped by module.

    Uses OptionList's built-in OptionSelected message — the screen handles
    the event via on_option_list_option_selected and maps option index to
    FuncRef using option_refs.
    """

    def __init__(
        self,
        topo_order: list[Path],
        func_symbol_table: dict[CodeLabel, FuncRef],
        project_root: Path,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._topo_order = topo_order
        self._func_symbol_table = func_symbol_table
        self._project_root = project_root
        self.option_refs: dict[int, FuncRef | None] = {}

    def on_mount(self) -> None:
        self.add_option(Option("[t] Top-level execution"))
        self.option_refs[0] = None
        # Track actual OptionList index (separators and disabled items count)
        actual_idx = 1

        grouped = group_entry_points(self._topo_order, self._func_symbol_table)
        for path, funcs in grouped:
            rel = (
                path.relative_to(self._project_root)
                if path.is_relative_to(self._project_root)
                else path
            )
            self.add_option(None)  # separator
            actual_idx += 1
            self.add_option(Option(f"  {rel}", disabled=True))
            actual_idx += 1
            if not funcs:
                self.add_option(Option("    (no functions)", disabled=True))
                actual_idx += 1
            else:
                for ref in funcs:
                    self.add_option(Option(f"    {ref.name}()"))
                    self.option_refs[actual_idx] = ref
                    actual_idx += 1
