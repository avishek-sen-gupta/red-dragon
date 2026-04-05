"""Integration tests for the multi-file project TUI pipeline."""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.project.entry_point import EntryPoint
from viz.project_pipeline import (
    ProjectPipelineResult,
    execute_project,
    lookup_module_for_index,
    run_project_pipeline,
)


class TestProjectPipelineIntegration:
    """Full pipeline: directory → compile → link → trace → module mapping."""

    def test_two_file_python_top_level(self, tmp_path: Path) -> None:
        """Two-file project: utils.py defines helper, main.py calls it."""
        (tmp_path / "utils.py").write_text("def helper(x):\n    return x + 1\n")
        (tmp_path / "main.py").write_text(
            "from utils import helper\nresult = helper(5)\n"
        )
        result = run_project_pipeline(tmp_path, "python")
        result = execute_project(result, entry_point=None, max_steps=200)
        assert result.trace is not None
        assert len(result.trace.steps) > 0
        assert len(result.module_sources) == 2
        assert len(result.module_asts) == 2

    def test_trace_steps_map_to_modules(self, tmp_path: Path) -> None:
        """Each trace step's instruction should map to a known module."""
        (tmp_path / "utils.py").write_text("val = 10\n")
        (tmp_path / "main.py").write_text("from utils import val\nx = val\n")
        result = run_project_pipeline(tmp_path, "python")
        result = execute_project(result, entry_point=None, max_steps=200)
        assert result.trace is not None
        mapped_count = 0
        for step in result.trace.steps:
            idx = result.instruction_to_index.get(id(step.instruction))
            if idx is not None:
                module = lookup_module_for_index(result.module_ir_ranges, idx)
                if module is not None:
                    mapped_count += 1
                    assert module in result.module_sources
        assert mapped_count > 0

    def test_function_entry_point(self, tmp_path: Path) -> None:
        """Function entry point executes preamble then dispatches."""
        (tmp_path / "main.py").write_text("x = 1\n\ndef compute():\n    return x + 2\n")
        result = run_project_pipeline(tmp_path, "python")
        result = execute_project(
            result,
            entry_point=EntryPoint.function(lambda f: str(f.name) == "compute"),
            max_steps=200,
        )
        assert result.trace is not None
        assert len(result.trace.steps) > 0

    def test_existing_fixture_project(self) -> None:
        """Use the existing python_basic fixture to verify pipeline works."""
        fixture_dir = Path("tests/fixtures/projects/python_basic")
        if not fixture_dir.exists():
            pytest.skip("Fixture not found")
        result = run_project_pipeline(fixture_dir, "python")
        assert len(result.module_sources) == 2
        assert len(result.topo_order) == 2
        result = execute_project(result, entry_point=None, max_steps=200)
        assert result.trace is not None
        assert len(result.trace.steps) > 0
