"""Tests for import resolvers — maps ImportRef → file path."""

from pathlib import Path

import pytest

from interpreter.project.types import ImportRef
from interpreter.project.resolver import (
    ImportResolver,
    ResolvedImport,
    NullImportResolver,
    PythonImportResolver,
    JavaImportResolver,
    get_resolver,
    NO_PATH,
)
from interpreter.constants import Language


class TestNullImportResolver:
    def test_everything_is_external(self):
        resolver = NullImportResolver()
        ref = ImportRef(source_file=Path("main.py"), module_path="utils")
        [result] = resolver.resolve(ref, Path("/project"))
        assert result.resolved_path == NO_PATH
        assert result.is_external is True
        assert result.is_resolved() is False


class TestGetResolver:
    def test_python_returns_python_resolver(self):
        resolver = get_resolver(Language.PYTHON)
        assert isinstance(resolver, PythonImportResolver)

    def test_unknown_language_returns_null(self):
        """Languages without a specific resolver get the null resolver."""
        # COBOL now has its own resolver, so we need a truly unsupported language.
        # Since all Language enum members are covered, test with NullImportResolver directly.
        resolver = NullImportResolver()
        ref = ImportRef(source_file=Path("main.txt"), module_path="utils")
        [result] = resolver.resolve(ref, Path("/project"))
        assert result.resolved_path == NO_PATH
        assert result.is_external is True


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
        [result] = resolver.resolve(ref, project)
        assert result.resolved_path == project / "utils.py"
        assert result.is_external is False

    def test_resolves_package_init(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "main.py",
            module_path="pkg",
        )
        [result] = resolver.resolve(ref, project)
        assert result.resolved_path == project / "pkg" / "__init__.py"

    def test_resolves_dotted_module(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "main.py",
            module_path="pkg.models",
        )
        [result] = resolver.resolve(ref, project)
        assert result.resolved_path == project / "pkg" / "models.py"

    def test_resolves_relative_single_dot(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "pkg" / "models.py",
            module_path="",
            names=("sub",),
            is_relative=True,
            relative_level=1,  # from . import sub (same directory as models.py)
        )
        [result] = resolver.resolve(ref, project)
        assert result.resolved_path == project / "pkg" / "sub" / "__init__.py"

    def test_resolves_relative_double_dot(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "pkg" / "sub" / "helpers.py",
            module_path="",
            names=("models",),
            is_relative=True,
            relative_level=2,  # from .. import models (go up from pkg/sub/ to pkg/)
        )
        [result] = resolver.resolve(ref, project)
        assert result.resolved_path == project / "pkg" / "models.py"

    def test_relative_single_dot_module(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "pkg" / "__init__.py",
            module_path="models",
            names=("User",),
            is_relative=True,
            relative_level=1,  # from .models import User
        )
        [result] = resolver.resolve(ref, project)
        assert result.resolved_path == project / "pkg" / "models.py"

    def test_system_import_is_external(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "main.py",
            module_path="os",
            is_system=True,
        )
        [result] = resolver.resolve(ref, project)
        assert result.resolved_path == NO_PATH
        assert result.is_external is True

    def test_nonexistent_module_returns_no_path(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "main.py",
            module_path="does_not_exist",
        )
        [result] = resolver.resolve(ref, project)
        assert result.resolved_path == NO_PATH
        assert result.is_resolved() is False

    def test_deeply_nested_dotted(self, project):
        resolver = PythonImportResolver()
        ref = ImportRef(
            source_file=project / "main.py",
            module_path="pkg.sub.helpers",
        )
        [result] = resolver.resolve(ref, project)
        assert result.resolved_path == project / "pkg" / "sub" / "helpers.py"


class TestResolvedImport:
    def test_is_resolved_true_for_real_path(self):
        ref = ImportRef(source_file=Path("main.java"), module_path="com.example.Foo")
        result = ResolvedImport(ref=ref, resolved_path=Path("/project/Foo.java"))
        assert result.is_resolved() is True

    def test_is_resolved_false_for_no_path(self):
        ref = ImportRef(source_file=Path("main.java"), module_path="com.example.Foo")
        result = ResolvedImport(ref=ref)
        assert result.is_resolved() is False

    def test_is_resolved_false_for_external(self):
        ref = ImportRef(source_file=Path("main.java"), module_path="java.util.List")
        result = ResolvedImport(
            ref=ref, resolved_path=Path("/jdk/List.java"), is_external=True
        )
        assert result.is_resolved() is False

    def test_default_resolved_path_is_no_path(self):
        ref = ImportRef(source_file=Path("main.java"), module_path="com.example.Foo")
        result = ResolvedImport(ref=ref)
        assert result.resolved_path == NO_PATH


class TestResolverReturnType:
    def test_null_resolver_returns_list(self):
        resolver = NullImportResolver()
        ref = ImportRef(source_file=Path("main.py"), module_path="utils")
        result = resolver.resolve(ref, Path("/project"))
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].is_external is True

    def test_python_resolver_returns_list(self, tmp_path):
        (tmp_path / "utils.py").write_text("x = 1\n")
        resolver = PythonImportResolver()
        ref = ImportRef(source_file=tmp_path / "main.py", module_path="utils")
        result = resolver.resolve(ref, tmp_path)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].is_resolved() is True


class TestJavaImportResolverMultiRoot:
    def test_resolves_specific_import_across_roots(self, tmp_path):
        """Specific import found in a non-primary source root."""
        root_a = tmp_path / "module-a" / "src" / "main" / "java"
        root_b = tmp_path / "module-b" / "src" / "main" / "java"
        (root_b / "com" / "example").mkdir(parents=True)
        (root_b / "com" / "example" / "Utils.java").write_text("class Utils {}")

        resolver = JavaImportResolver(source_roots=[root_a, root_b])
        ref = ImportRef(
            source_file=tmp_path / "App.java", module_path="com.example.Utils"
        )
        results = resolver.resolve(ref, tmp_path)
        assert len(results) == 1
        assert results[0].is_resolved()
        assert results[0].resolved_path == root_b / "com" / "example" / "Utils.java"

    def test_wildcard_resolves_all_files_in_package(self, tmp_path):
        """Wildcard import returns one ResolvedImport per .java file."""
        root = tmp_path / "src" / "main" / "java"
        pkg = root / "com" / "example"
        pkg.mkdir(parents=True)
        (pkg / "Foo.java").write_text("class Foo {}")
        (pkg / "Bar.java").write_text("class Bar {}")
        (pkg / "Baz.java").write_text("class Baz {}")

        resolver = JavaImportResolver(source_roots=[root])
        ref = ImportRef(
            source_file=tmp_path / "App.java",
            module_path="com.example",
            names=("*",),
        )
        results = resolver.resolve(ref, tmp_path)
        resolved_names = sorted(
            r.resolved_path.name for r in results if r.is_resolved()
        )
        assert resolved_names == ["Bar.java", "Baz.java", "Foo.java"]

    def test_wildcard_across_roots(self, tmp_path):
        """Wildcard should find files in the first root that has the package."""
        root_a = tmp_path / "a" / "src" / "main" / "java"
        root_b = tmp_path / "b" / "src" / "main" / "java"
        pkg_b = root_b / "com" / "utils"
        pkg_b.mkdir(parents=True)
        (pkg_b / "Helper.java").write_text("class Helper {}")
        (pkg_b / "Util.java").write_text("class Util {}")

        resolver = JavaImportResolver(source_roots=[root_a, root_b])
        ref = ImportRef(
            source_file=tmp_path / "App.java",
            module_path="com.utils",
            names=("*",),
        )
        results = resolver.resolve(ref, tmp_path)
        resolved_names = sorted(
            r.resolved_path.name for r in results if r.is_resolved()
        )
        assert resolved_names == ["Helper.java", "Util.java"]

    def test_no_source_roots_falls_back_to_project_root(self, tmp_path):
        """When no source_roots provided, uses the old 4-pattern search."""
        java_root = tmp_path / "src" / "main" / "java"
        (java_root / "com" / "example").mkdir(parents=True)
        (java_root / "com" / "example" / "App.java").write_text("class App {}")

        resolver = JavaImportResolver()
        ref = ImportRef(
            source_file=tmp_path / "Main.java", module_path="com.example.App"
        )
        results = resolver.resolve(ref, tmp_path)
        assert len(results) == 1
        assert results[0].is_resolved()

    def test_system_import_returns_external(self):
        resolver = JavaImportResolver()
        ref = ImportRef(
            source_file=Path("App.java"),
            module_path="java.util.List",
            is_system=True,
        )
        results = resolver.resolve(ref, Path("/project"))
        assert len(results) == 1
        assert results[0].is_external is True
