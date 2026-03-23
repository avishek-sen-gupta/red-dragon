"""Tests for import resolvers — maps ImportRef → file path."""

from pathlib import Path

import pytest

from interpreter.project.types import ImportRef
from interpreter.project.resolver import (
    ImportResolver,
    ResolvedImport,
    NullImportResolver,
    PythonImportResolver,
    get_resolver,
)
from interpreter.constants import Language


class TestNullImportResolver:
    def test_everything_is_external(self):
        resolver = NullImportResolver()
        ref = ImportRef(source_file=Path("main.py"), module_path="utils")
        result = resolver.resolve(ref, Path("/project"))
        assert result.resolved_path is None
        assert result.is_external is True


class TestGetResolver:
    def test_python_returns_python_resolver(self):
        resolver = get_resolver(Language.PYTHON)
        assert isinstance(resolver, PythonImportResolver)

    def test_unknown_language_returns_null(self):
        """Languages without a specific resolver get the null resolver."""
        resolver = get_resolver(Language.COBOL)
        assert isinstance(resolver, NullImportResolver)


class TestPythonImportResolver:
    """Test Python import resolution using real tmp directories."""

    @pytest.fixture
    def project(self, tmp_path):
        """Create a minimal Python project on disk."""
        # /project/main.py
        (tmp_path / "main.py").write_text("from utils import helper\n")
        # /project/utils.py
        (tmp_path / "utils.py").write_text("def helper(): pass\n")
        # /project/pkg/__init__.py
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("")
        # /project/pkg/models.py
        (tmp_path / "pkg" / "models.py").write_text("class User: pass\n")
        # /project/pkg/sub/__init__.py
        (tmp_path / "pkg" / "sub").mkdir()
        (tmp_path / "pkg" / "sub" / "__init__.py").write_text("")
        # /project/pkg/sub/helpers.py
        (tmp_path / "pkg" / "sub" / "helpers.py").write_text("def h(): pass\n")
        return tmp_path

    def test_resolves_simple_module(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "main.py",
            module_path="utils",
        )
        result = resolver.resolve(ref, project)
        assert result.resolved_path == project / "utils.py"
        assert result.is_external is False

    def test_resolves_package_init(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "main.py",
            module_path="pkg",
        )
        result = resolver.resolve(ref, project)
        assert result.resolved_path == project / "pkg" / "__init__.py"

    def test_resolves_dotted_module(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "main.py",
            module_path="pkg.models",
        )
        result = resolver.resolve(ref, project)
        assert result.resolved_path == project / "pkg" / "models.py"

    def test_resolves_relative_single_dot(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "pkg" / "sub" / "helpers.py",
            module_path="",
            names=("models",),
            is_relative=True,
            relative_level=2,  # from .. import models (go up from pkg/sub/ to pkg/)
        )
        # For relative imports, we resolve the module, not the name
        # "from .. import models" from pkg/sub/ means: go to pkg/ and import models
        result = resolver.resolve(ref, project)
        # The resolver should find pkg/models.py
        assert result.resolved_path is not None

    def test_relative_single_dot_module(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "pkg" / "__init__.py",
            module_path="models",
            names=("User",),
            is_relative=True,
            relative_level=1,  # from .models import User
        )
        result = resolver.resolve(ref, project)
        assert result.resolved_path == project / "pkg" / "models.py"

    def test_system_import_is_external(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "main.py",
            module_path="os",
            is_system=True,
        )
        result = resolver.resolve(ref, project)
        assert result.resolved_path is None
        assert result.is_external is True

    def test_nonexistent_module_returns_none(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "main.py",
            module_path="does_not_exist",
        )
        result = resolver.resolve(ref, project)
        assert result.resolved_path is None

    def test_deeply_nested_dotted(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "main.py",
            module_path="pkg.sub.helpers",
        )
        result = resolver.resolve(ref, project)
        assert result.resolved_path == project / "pkg" / "sub" / "helpers.py"
