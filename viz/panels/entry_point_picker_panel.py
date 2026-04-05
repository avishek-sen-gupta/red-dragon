"""Entry point picker panel — scrollable list of functions grouped by module."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from interpreter.ir import CodeLabel
from interpreter.refs.func_ref import FuncRef


@dataclass(frozen=True)
class EntryPointSelected(Message):
    """Posted when the user selects an entry point."""

    func_ref: FuncRef | None  # None = top-level execution


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
    """Scrollable list of entry points grouped by module."""

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
        self._option_refs: dict[int, FuncRef | None] = {}

    def on_mount(self) -> None:
        self.add_option(Option("[t] Top-level execution"))
        self._option_refs[0] = None
        option_idx = 1

        grouped = group_entry_points(self._topo_order, self._func_symbol_table)
        for path, funcs in grouped:
            rel = (
                path.relative_to(self._project_root)
                if path.is_relative_to(self._project_root)
                else path
            )
            self.add_option(None)  # separator
            self.add_option(Option(f"  {rel}", disabled=True))
            if not funcs:
                self.add_option(Option("    (no functions)", disabled=True))
            else:
                for ref in funcs:
                    self.add_option(Option(f"    {ref.name}()"))
                    self._option_refs[option_idx] = ref
                    option_idx += 1

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if idx in self._option_refs:
            self.post_message(EntryPointSelected(func_ref=self._option_refs[idx]))
