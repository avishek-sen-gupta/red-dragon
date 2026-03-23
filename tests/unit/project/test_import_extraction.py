"""Tests for import extraction base infrastructure."""

from pathlib import Path

import pytest

from interpreter.project.types import ImportRef
from interpreter.project.imports import extract_imports
from interpreter.constants import Language


class TestExtractImportsBase:
    """Test the base extract_imports dispatch — default returns empty list."""

    def test_returns_empty_for_no_imports(self):
        """Simple code with no imports produces an empty list."""
        result = extract_imports(b"x = 42\n", Path("main.py"), Language.PYTHON)
        assert result == []

    def test_returns_list_type(self):
        result = extract_imports(b"", Path("main.py"), Language.PYTHON)
        assert isinstance(result, list)


class TestExtractImportsPython:
    """Test Python import extraction."""

    def test_import_statement(self):
        source = b"import os\n"
        refs = extract_imports(source, Path("main.py"), Language.PYTHON)
        assert len(refs) == 1
        assert refs[0].module_path == "os"
        assert refs[0].names == ()
        assert refs[0].kind == "import"
        assert refs[0].source_file == Path("main.py")

    def test_import_dotted(self):
        source = b"import os.path\n"
        refs = extract_imports(source, Path("main.py"), Language.PYTHON)
        assert len(refs) == 1
        assert refs[0].module_path == "os.path"

    def test_from_import(self):
        source = b"from os.path import join\n"
        refs = extract_imports(source, Path("main.py"), Language.PYTHON)
        assert len(refs) == 1
        assert refs[0].module_path == "os.path"
        assert refs[0].names == ("join",)

    def test_from_import_multiple_names(self):
        source = b"from os.path import join, exists\n"
        refs = extract_imports(source, Path("main.py"), Language.PYTHON)
        assert len(refs) == 1
        assert set(refs[0].names) == {"join", "exists"}

    def test_relative_import_single_dot(self):
        source = b"from . import utils\n"
        refs = extract_imports(source, Path("pkg/main.py"), Language.PYTHON)
        assert len(refs) == 1
        assert refs[0].is_relative is True
        assert refs[0].relative_level == 1
        assert refs[0].names == ("utils",)

    def test_relative_import_double_dot(self):
        source = b"from .. import models\n"
        refs = extract_imports(source, Path("pkg/sub/main.py"), Language.PYTHON)
        assert len(refs) == 1
        assert refs[0].is_relative is True
        assert refs[0].relative_level == 2

    def test_relative_from_import(self):
        source = b"from .models import User\n"
        refs = extract_imports(source, Path("pkg/main.py"), Language.PYTHON)
        assert len(refs) == 1
        assert refs[0].is_relative is True
        assert refs[0].relative_level == 1
        assert refs[0].module_path == "models"
        assert refs[0].names == ("User",)

    def test_wildcard_import(self):
        source = b"from utils import *\n"
        refs = extract_imports(source, Path("main.py"), Language.PYTHON)
        assert len(refs) == 1
        assert refs[0].names == ("*",)

    def test_aliased_import(self):
        source = b"import numpy as np\n"
        refs = extract_imports(source, Path("main.py"), Language.PYTHON)
        assert len(refs) == 1
        assert refs[0].module_path == "numpy"
        assert refs[0].alias == "np"

    def test_multiple_imports(self):
        source = b"import os\nimport sys\nfrom pathlib import Path\n"
        refs = extract_imports(source, Path("main.py"), Language.PYTHON)
        assert len(refs) == 3

    def test_ignores_non_import_statements(self):
        source = b"x = 42\ndef foo(): pass\nimport os\n"
        refs = extract_imports(source, Path("main.py"), Language.PYTHON)
        assert len(refs) == 1
        assert refs[0].module_path == "os"

    def test_future_import_ignored(self):
        source = b"from __future__ import annotations\nimport os\n"
        refs = extract_imports(source, Path("main.py"), Language.PYTHON)
        # __future__ imports should either be skipped or marked as system
        non_future = [r for r in refs if "__future__" not in r.module_path]
        assert len(non_future) >= 1
        assert non_future[0].module_path == "os"
