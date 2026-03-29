"""Integration tests for the full multi-file project pipeline.

Tests: discover imports → resolve → compile → link → execute/analyze.
"""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.var_name import VarName
from interpreter.project.compiler import compile_module, compile_project
from interpreter.project.types import LinkedProgram, ModuleUnit
from interpreter.func_name import FuncName
from interpreter.class_name import ClassName


class TestCompileModulePython:
    """Test single-module compilation produces correct ModuleUnit."""

    def test_simple_module(self, tmp_path):
        source = "def helper(x):\n    return x + 1\n"
        f = tmp_path / "utils.py"
        f.write_text(source)

        unit = compile_module(f, Language.PYTHON)

        assert isinstance(unit, ModuleUnit)
        assert unit.path == f
        assert unit.language == Language.PYTHON
        assert len(unit.ir) > 0
        assert FuncName("helper") in unit.exports.functions

    def test_module_with_class(self, tmp_path):
        source = "class User:\n    def greet(self):\n        return 'hi'\n"
        f = tmp_path / "models.py"
        f.write_text(source)

        unit = compile_module(f, Language.PYTHON)

        assert ClassName("User") in unit.exports.classes

    def test_module_with_imports(self, tmp_path):
        source = "import os\nfrom pathlib import Path\n\ndef main(): pass\n"
        f = tmp_path / "main.py"
        f.write_text(source)

        unit = compile_module(f, Language.PYTHON)

        assert len(unit.imports) == 2

    def test_module_exports_top_level_vars(self, tmp_path):
        source = "PI = 3.14\ndef area(r):\n    return PI * r * r\n"
        f = tmp_path / "math_utils.py"
        f.write_text(source)

        unit = compile_module(f, Language.PYTHON)

        assert VarName("PI") in unit.exports.variables
        assert FuncName("area") in unit.exports.functions


class TestCompileProjectPython:
    """Test full multi-file Python project compilation and linking."""

    @pytest.fixture
    def two_file_project(self, tmp_path):
        """main.py imports helper from utils.py."""
        (tmp_path / "utils.py").write_text("def helper(x):\n    return x + 1\n")
        (tmp_path / "main.py").write_text(
            "from utils import helper\n\nresult = helper(42)\n"
        )
        return tmp_path

    @pytest.fixture
    def three_file_chain(self, tmp_path):
        """main → utils → constants: chain of imports."""
        (tmp_path / "constants.py").write_text("MAGIC = 42\n")
        (tmp_path / "utils.py").write_text(
            "from constants import MAGIC\n\ndef helper():\n    return MAGIC\n"
        )
        (tmp_path / "main.py").write_text(
            "from utils import helper\n\nresult = helper()\n"
        )
        return tmp_path

    @pytest.fixture
    def package_project(self, tmp_path):
        """Project with package structure."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "models.py").write_text("class User:\n    pass\n")
        (tmp_path / "main.py").write_text("from pkg.models import User\n\nu = User()\n")
        return tmp_path

    def test_two_file_links(self, two_file_project):
        linked = compile_project(
            two_file_project / "main.py",
            Language.PYTHON,
            project_root=two_file_project,
        )

        assert isinstance(linked, LinkedProgram)
        assert len(linked.modules) == 2
        assert linked.entry_module == two_file_project / "main.py"
        assert len(linked.merged_ir) > 0
        assert len(linked.merged_cfg.blocks) > 0

    def test_two_file_merged_registry_has_both(self, two_file_project):
        linked = compile_project(
            two_file_project / "main.py",
            Language.PYTHON,
            project_root=two_file_project,
        )

        # The merged registry should contain the helper function (namespaced)
        func_labels = list(linked.merged_registry.func_params.keys())
        assert any("helper" in label for label in func_labels)

    def test_three_file_chain(self, three_file_chain):
        linked = compile_project(
            three_file_chain / "main.py",
            Language.PYTHON,
            project_root=three_file_chain,
        )

        assert len(linked.modules) == 3
        # All three files should be in the import graph
        assert three_file_chain / "main.py" in linked.import_graph
        assert three_file_chain / "utils.py" in linked.import_graph
        assert three_file_chain / "constants.py" in linked.import_graph

    def test_package_project(self, package_project):
        linked = compile_project(
            package_project / "main.py",
            Language.PYTHON,
            project_root=package_project,
        )

        assert (
            len(linked.modules) >= 2
        )  # main.py + pkg/models.py (+ possibly __init__.py)

    def test_system_imports_not_resolved(self, tmp_path):
        """System imports (os, sys) should not cause file resolution."""
        (tmp_path / "main.py").write_text(
            "import os\nimport sys\n\ndef main():\n    return os.getcwd()\n"
        )

        linked = compile_project(
            tmp_path / "main.py",
            Language.PYTHON,
            project_root=tmp_path,
        )

        # Only main.py should be compiled (os/sys are system)
        assert len(linked.modules) == 1

    def test_merged_cfg_has_entry(self, two_file_project):
        linked = compile_project(
            two_file_project / "main.py",
            Language.PYTHON,
            project_root=two_file_project,
        )

        assert linked.merged_cfg.entry is not None
        assert linked.merged_cfg.entry in linked.merged_cfg.blocks


class TestCompileModuleJavaScript:
    def test_esm_module(self, tmp_path):
        source = "export function add(a, b) { return a + b; }\n"
        f = tmp_path / "math.js"
        f.write_text(source)

        unit = compile_module(f, Language.JAVASCRIPT)

        assert isinstance(unit, ModuleUnit)
        assert len(unit.ir) > 0
        assert FuncName("add") in unit.exports.functions

    def test_js_project_with_import(self, tmp_path):
        (tmp_path / "utils.js").write_text("function helper(x) { return x + 1; }\n")
        (tmp_path / "main.js").write_text(
            'import { helper } from "./utils.js";\nvar result = helper(42);\n'
        )

        linked = compile_project(
            tmp_path / "main.js",
            Language.JAVASCRIPT,
            project_root=tmp_path,
        )

        assert len(linked.modules) == 2


class TestCompileModuleJava:
    def test_java_class(self, tmp_path):
        source = "public class Utils {\n    public static int add(int a, int b) {\n        return a + b;\n    }\n}\n"
        f = tmp_path / "Utils.java"
        f.write_text(source)

        unit = compile_module(f, Language.JAVA)

        assert isinstance(unit, ModuleUnit)
        assert ClassName("Utils") in unit.exports.classes


class TestCompileModuleC:
    def test_c_with_local_include(self, tmp_path):
        (tmp_path / "helper.h").write_text("int helper(int x);\n")
        (tmp_path / "main.c").write_text(
            '#include "helper.h"\nint main() { return helper(42); }\n'
        )

        linked = compile_project(
            tmp_path / "main.c",
            Language.C,
            project_root=tmp_path,
        )

        assert len(linked.modules) == 2
