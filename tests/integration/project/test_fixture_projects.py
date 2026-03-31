"""Integration tests using the fixture projects on disk."""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.project.compiler import compile_directory
from interpreter.project.types import LinkedProgram

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "projects"


class TestPythonBasicFixture:
    """Test with tests/fixtures/projects/python_basic/"""

    def test_compiles_and_links(self):
        entry = FIXTURES_DIR / "python_basic" / "main.py"
        if not entry.exists():
            pytest.skip("fixture not found")

        linked = compile_directory(FIXTURES_DIR / "python_basic", Language.PYTHON)
        assert isinstance(linked, LinkedProgram)
        assert len(linked.modules) == 2
        assert any("helper" in label for label in linked.merged_registry.func_params)

    def test_import_graph_lists_all_files(self):
        entry = FIXTURES_DIR / "python_basic" / "main.py"
        if not entry.exists():
            pytest.skip("fixture not found")

        linked = compile_directory(FIXTURES_DIR / "python_basic", Language.PYTHON)
        main_path = (FIXTURES_DIR / "python_basic" / "main.py").resolve()
        utils_path = (FIXTURES_DIR / "python_basic" / "utils.py").resolve()
        assert main_path in linked.import_graph
        assert utils_path in linked.import_graph


class TestPythonPackageFixture:
    """Test with tests/fixtures/projects/python_package/"""

    def test_compiles_package_imports(self):
        entry = FIXTURES_DIR / "python_package" / "main.py"
        if not entry.exists():
            pytest.skip("fixture not found")

        linked = compile_directory(FIXTURES_DIR / "python_package", Language.PYTHON)
        assert len(linked.modules) >= 2  # main.py + models/user.py


class TestJsEsmFixture:
    """Test with tests/fixtures/projects/js_esm/"""

    def test_compiles_and_links(self):
        entry = FIXTURES_DIR / "js_esm" / "main.js"
        if not entry.exists():
            pytest.skip("fixture not found")

        linked = compile_directory(FIXTURES_DIR / "js_esm", Language.JAVASCRIPT)
        assert len(linked.modules) == 2
        assert any("add" in label for label in linked.merged_registry.func_params)


class TestCSimpleFixture:
    """Test with tests/fixtures/projects/c_simple/"""

    def test_compiles_and_links(self):
        entry = FIXTURES_DIR / "c_simple" / "main.c"
        if not entry.exists():
            pytest.skip("fixture not found")

        linked = compile_directory(FIXTURES_DIR / "c_simple", Language.C)
        assert len(linked.modules) == 2
