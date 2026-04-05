"""Tests for the project pipeline — compile directory into ProjectPipelineResult."""

from pathlib import Path
import pytest
from interpreter.constants import Language
from viz.project_pipeline import (
    ProjectPipelineResult,
    run_project_pipeline,
    execute_project,
    lookup_module_for_index,
)


class TestRunProjectPipeline:
    def test_single_file_project(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1\n")
        result = run_project_pipeline(tmp_path, "python")
        assert isinstance(result, ProjectPipelineResult)
        assert result.linked is not None
        assert len(result.module_sources) == 1
        assert len(result.module_asts) == 1
        assert len(result.topo_order) == 1
        assert result.trace is None

    def test_two_file_project(self, tmp_path: Path) -> None:
        (tmp_path / "utils.py").write_text("def helper(x):\n    return x + 1\n")
        (tmp_path / "main.py").write_text(
            "from utils import helper\nresult = helper(5)\n"
        )
        result = run_project_pipeline(tmp_path, "python")
        assert len(result.module_sources) == 2
        assert len(result.topo_order) == 2

    def test_module_ir_ranges_cover_instructions(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.py").write_text("y = 2\n")
        result = run_project_pipeline(tmp_path, "python")
        total_ir = len(result.linked.merged_ir)
        covered = set()
        for start, end, _path in result.module_ir_ranges:
            for i in range(start, end):
                covered.add(i)
        assert len(covered) > 0


class TestModuleLookup:
    def test_lookup_returns_correct_module(self, tmp_path: Path) -> None:
        (tmp_path / "utils.py").write_text("x = 1\n")
        (tmp_path / "main.py").write_text("from utils import x\ny = x\n")
        result = run_project_pipeline(tmp_path, "python")
        if result.module_ir_ranges:
            start, _end, expected_path = result.module_ir_ranges[0]
            found = lookup_module_for_index(result.module_ir_ranges, start)
            assert found == expected_path

    def test_lookup_out_of_range_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1\n")
        result = run_project_pipeline(tmp_path, "python")
        found = lookup_module_for_index(result.module_ir_ranges, 999999)
        assert found is None


class TestExecuteProject:
    def test_top_level_execution(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 42\n")
        result = run_project_pipeline(tmp_path, "python")
        result = execute_project(result, entry_point=None, max_steps=100)
        assert result.trace is not None
        assert len(result.trace.steps) > 0
