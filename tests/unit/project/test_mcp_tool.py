"""Tests for the MCP load_project tool."""

from pathlib import Path

import pytest

from mcp_server.tools import handle_load_project


class TestHandleLoadProject:
    @pytest.fixture
    def python_project(self, tmp_path):
        (tmp_path / "utils.py").write_text("def helper(x):\n    return x + 1\n")
        (tmp_path / "main.py").write_text(
            "from utils import helper\n\nresult = helper(42)\n"
        )
        return tmp_path

    def test_returns_dict(self, python_project):
        result = handle_load_project(str(python_project / "main.py"), "python")
        assert isinstance(result, dict)
        assert "error" not in result

    def test_has_expected_keys(self, python_project):
        result = handle_load_project(str(python_project / "main.py"), "python")
        assert "modules" in result
        assert "language" in result
        assert "import_graph" in result
        assert "cfg_blocks" in result
        assert "functions" in result

    def test_correct_module_count(self, python_project):
        result = handle_load_project(str(python_project / "main.py"), "python")
        assert result["modules"] == 2

    def test_invalid_language_returns_error(self, python_project):
        result = handle_load_project(str(python_project / "main.py"), "nonexistent")
        assert "error" in result

    def test_missing_file_returns_error(self):
        result = handle_load_project("/nonexistent/main.py", "python")
        assert "error" in result
