"""Tests for compile_directory — compile all source files in a directory tree."""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.project.compiler import compile_directory
from interpreter.project.types import LinkedProgram


class TestCompileDirectory:
    def test_compiles_all_python_files(self, tmp_path):
        (tmp_path / "main.py").write_text(
            "from utils import helper\nresult = helper(42)\n"
        )
        (tmp_path / "utils.py").write_text("def helper(x):\n    return x + 1\n")
        (tmp_path / "orphan.py").write_text("CONSTANT = 99\n")

        linked = compile_directory(tmp_path, Language.PYTHON)

        assert isinstance(linked, LinkedProgram)
        # Demand-driven filtering: only main + utils are reachable; orphan is filtered
        assert len(linked.modules) == 2

    def test_nested_directories(self, tmp_path):
        (tmp_path / "main.py").write_text("from pkg.mod import y\nx = y\n")
        sub = tmp_path / "pkg"
        sub.mkdir()
        (sub / "__init__.py").write_text("")
        (sub / "mod.py").write_text("y = 2\n")

        linked = compile_directory(tmp_path, Language.PYTHON)

        # main.py imports pkg.mod, so both should be in the linked program
        assert len(linked.modules) == 3  # main.py, pkg/__init__.py, pkg/mod.py

    def test_ignores_non_matching_extensions(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1\n")
        (tmp_path / "readme.md").write_text("# hello\n")
        (tmp_path / "data.json").write_text("{}\n")

        linked = compile_directory(tmp_path, Language.PYTHON)

        assert len(linked.modules) == 1

    def test_javascript_files(self, tmp_path):
        (tmp_path / "main.js").write_text("var x = 1;\n")
        (tmp_path / "utils.js").write_text("function helper() {}\n")

        linked = compile_directory(tmp_path, Language.JAVASCRIPT)

        # With demand-driven filtering, only reachable modules are included.
        # Since main.js doesn't import utils.js, only main.js is in the linked program.
        assert len(linked.modules) == 1

    def test_merged_cfg_has_entry(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 42\n")

        linked = compile_directory(tmp_path, Language.PYTHON)

        assert linked.merged_cfg.entry is not None
        assert linked.merged_cfg.entry in linked.merged_cfg.blocks
