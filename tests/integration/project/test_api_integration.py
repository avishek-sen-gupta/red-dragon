"""Tests for multi-file API and MCP integration."""

import pytest

from interpreter.api import run_project
from interpreter.constants import Language


class TestRunProject:
    @pytest.fixture
    def simple_project(self, tmp_path):
        (tmp_path / "utils.py").write_text("def add(a, b):\n    return a + b\n")
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
