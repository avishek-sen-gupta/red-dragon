# tests/integration/project/test_java_namespace_resolution.py
"""End-to-end integration test for Java namespace resolution.

Verifies that fully-qualified Java references (java.util.Arrays, etc.)
produce LoadVar(short_name) instead of cascading LOAD_FIELD chains,
and that the linked program compiles correctly with stdlib stubs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.ir import Opcode
from interpreter.project.compiler import compile_directory
from interpreter.project.types import LinkedProgram


class TestJavaNamespaceResolutionE2E:
    @pytest.fixture
    def qualified_ref_project(self, tmp_path: Path) -> Path:
        """Java project with fully-qualified stdlib references."""
        main_src = """\
package com.app;

public class Main {
    public static void run() {
        double val = java.lang.Math.sqrt(16.0);
    }
}
"""
        main_dir = tmp_path / "src" / "main" / "java" / "com" / "app"
        main_dir.mkdir(parents=True)
        (main_dir / "Main.java").write_text(main_src)
        return tmp_path

    def test_no_cascading_load_var_java(self, qualified_ref_project: Path):
        """LOAD_VAR 'java' should not appear; LoadVar('Math') should."""
        linked = compile_directory(qualified_ref_project, Language.JAVA)

        load_vars = [i for i in linked.merged_ir if i.opcode == Opcode.LOAD_VAR]
        names = [i.name.value for i in load_vars]

        assert "Math" in names, f"Expected LoadVar('Math'), got: {names}"
        assert "java" not in names, f"Cascading LoadVar('java') should be gone: {names}"

    def test_no_cascading_load_field_lang(self, qualified_ref_project: Path):
        """LOAD_FIELD 'lang' should not appear in the user module IR."""
        linked = compile_directory(qualified_ref_project, Language.JAVA)

        load_fields = [i for i in linked.merged_ir if i.opcode == Opcode.LOAD_FIELD]
        field_names = [i.field_name.value for i in load_fields]

        assert (
            "lang" not in field_names
        ), f"Cascading LoadField('lang') should be gone: {field_names}"

    @pytest.fixture
    def cross_module_qualified_project(self, tmp_path: Path) -> Path:
        """Project where one module references another via qualified name."""
        helper_src = """\
package com.lib;

public class Helper {
    public static int doubleIt(int n) {
        return n * 2;
    }
}
"""
        main_src = """\
package com.app;

public class Main {
    public static void run() {
        int result = com.lib.Helper.doubleIt(21);
    }
}
"""
        lib_dir = tmp_path / "src" / "main" / "java" / "com" / "lib"
        lib_dir.mkdir(parents=True)
        (lib_dir / "Helper.java").write_text(helper_src)

        app_dir = tmp_path / "src" / "main" / "java" / "com" / "app"
        app_dir.mkdir(parents=True)
        (app_dir / "Main.java").write_text(main_src)
        return tmp_path

    def test_cross_module_qualified_resolves(
        self, cross_module_qualified_project: Path
    ):
        """com.lib.Helper.doubleIt(21) should resolve Helper via namespace tree."""
        linked = compile_directory(cross_module_qualified_project, Language.JAVA)

        load_vars = [i for i in linked.merged_ir if i.opcode == Opcode.LOAD_VAR]
        names = [i.name.value for i in load_vars]

        assert "Helper" in names
        assert "com" not in names
