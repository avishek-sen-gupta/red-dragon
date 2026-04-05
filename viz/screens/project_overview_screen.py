"""Project overview screen — import graph + entry point picker."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, OptionList, Static

from interpreter.project.entry_point import EntryPoint
from viz.panels.import_graph_panel import ImportGraphPanel
from viz.panels.entry_point_picker_panel import EntryPointPickerPanel
from viz.project_pipeline import ProjectPipelineResult


class ProjectOverviewScreen(Screen):
    """Phase 1: project overview with import graph and entry point selection."""

    CSS = """
    ProjectOverviewScreen {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 1fr;
    }

    #import-graph-container {
        border: solid rgb(80,120,80);
        overflow-y: auto;
    }

    #entry-picker-container {
        border: solid rgb(80,80,120);
        overflow-y: auto;
    }
    """

    def __init__(self, result: ProjectPipelineResult, project_root: Path) -> None:
        super().__init__()
        self._result = result
        self._project_root = project_root

    def compose(self) -> ComposeResult:
        yield Header()

        exports: dict[Path, tuple[int, int]] = {}
        for path, module in self._result.linked.modules.items():
            fn_count = len(module.exports.functions)
            var_count = len(module.exports.variables)
            exports[path] = (fn_count, var_count)

        with Horizontal():
            with Vertical(id="import-graph-container"):
                yield Static(" Import Graph", classes="panel-title")
                yield ImportGraphPanel(
                    topo_order=self._result.topo_order,
                    import_graph=self._result.linked.import_graph,
                    exports=exports,
                    project_root=self._project_root,
                    id="import-graph-panel",
                )

            with Vertical(id="entry-picker-container"):
                yield Static(" Select Entry Point", classes="panel-title")
                yield EntryPointPickerPanel(
                    topo_order=self._result.topo_order,
                    func_symbol_table=self._result.linked.func_symbol_table,
                    project_root=self._project_root,
                    id="entry-picker-panel",
                )

        yield Footer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle entry point selection from the picker."""
        picker = self.query_one("#entry-picker-panel", EntryPointPickerPanel)
        idx = event.option_index
        if idx not in picker.option_refs:
            return
        func_ref = picker.option_refs[idx]
        if func_ref is None:
            entry_point = None
        else:
            name = func_ref.name
            entry_point = EntryPoint.function(lambda f, n=name: f.name == n)
        self.app.execute_entry_point(entry_point)
