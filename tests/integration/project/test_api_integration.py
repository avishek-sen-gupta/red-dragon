"""Tests for multi-file API and MCP integration."""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.api import analyze_project, run_project


class TestAnalyzeProject:
    @pytest.fixture
    def two_file_project(self, tmp_path):
        (tmp_path / "utils.py").write_text(
            "def helper(x):\n    return x + 1\n"
        )
        (tmp_path / "main.py").write_text(
            "from utils import helper\n\nresult = helper(42)\n"
        )
        return tmp_path

    def test_returns_interprocedural_result(self, two_file_project):
        result = analyze_project(
            two_file_project / "main.py",
            Language.PYTHON,
            project_root=two_file_project,
        )
        from interpreter.interprocedural.types import InterproceduralResult

        assert isinstance(result, InterproceduralResult)

    def test_call_graph_has_functions(self, two_file_project):
        result = analyze_project(
            two_file_project / "main.py",
            Language.PYTHON,
            project_root=two_file_project,
        )
        # The call graph should have discovered functions
        assert len(result.call_graph.functions) > 0


class TestRunProject:
    @pytest.fixture
    def simple_project(self, tmp_path):
        (tmp_path / "utils.py").write_text(
            "def add(a, b):\n    return a + b\n"
        )
        (tmp_path / "main.py").write_text(
            "from utils import add\n\nresult = add(1, 2)\n"
        )
        return tmp_path

    def test_returns_vm_state(self, simple_project):
        from interpreter.vm.vm import VMState

        vm = run_project(
            simple_project / "main.py",
            Language.PYTHON,
            project_root=simple_project,
        )
        assert isinstance(vm, VMState)
