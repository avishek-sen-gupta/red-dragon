"""ProjectApp — multi-file project TUI with two-screen architecture."""

from __future__ import annotations

import logging
from pathlib import Path

from textual.app import App

from interpreter.project.entry_point import EntryPoint
from viz.project_pipeline import ProjectPipelineResult, execute_project
from viz.screens.execution_screen import ExecutionScreen
from viz.screens.project_overview_screen import ProjectOverviewScreen

logger = logging.getLogger(__name__)


class ProjectApp(App):
    """Main TUI application for multi-file project visualization."""

    TITLE = "RedDragon Project Visualizer"

    def __init__(
        self,
        result: ProjectPipelineResult,
        project_root: Path,
        max_steps: int = 300,
    ) -> None:
        super().__init__()
        self._result = result
        self._project_root = project_root
        self._max_steps = max_steps

    def on_mount(self) -> None:
        self.push_screen(ProjectOverviewScreen(self._result, self._project_root))

    def execute_entry_point(self, entry_point: EntryPoint | None) -> None:
        """Called by ProjectOverviewScreen when an entry point is selected."""
        self._result = execute_project(
            self._result, entry_point=entry_point, max_steps=self._max_steps
        )
        self.push_screen(ExecutionScreen(self._result, self._project_root))
