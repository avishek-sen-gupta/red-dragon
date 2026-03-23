"""Integration tests for multi-file projects across all supported languages.

Every language with a resolver gets a real multi-file test: two files,
a function defined in the dependency, called from the entry module.
Verifies that the linker produces correct concrete VM execution results.
"""

import os
from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.project.compiler import compile_project
from interpreter.run import execute_cfg, ExecutionStrategies
from interpreter.run_types import VMConfig
from interpreter.types.typed_value import TypedValue


def _run_project_vm(tmp_path, files, entry, language):
    """Write files, compile, link, execute, return VMState."""
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    entry_path = tmp_path / entry
    linked = compile_project(entry_path, language, project_root=tmp_path)
    strategies = ExecutionStrategies(
        func_symbol_table=linked.func_symbol_table,
        class_symbol_table=linked.class_symbol_table,
    )
    vm, _ = execute_cfg(
        linked.merged_cfg,
        linked.merged_cfg.entry,
        linked.merged_registry,
        VMConfig(max_steps=200),
        strategies,
    )
    return vm


def _run_project(tmp_path, files, entry, language):
    """Write files, compile, link, execute, return local_vars dict."""
    vm = _run_project_vm(tmp_path, files, entry, language)
    frame = vm.call_stack[0]
    return {
        k: v.value if isinstance(v, TypedValue) else v
        for k, v in frame.local_vars.items()
    }


# ── Python ───────────────────────────────────────────────────────


class TestPythonMultiFile:
    def test_from_import_function(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "utils.py": "def add(a, b):\n    return a + b\n",
                "main.py": "from utils import add\n\nresult = add(10, 20)\n",
            },
            "main.py",
            Language.PYTHON,
        )
        assert result["result"] == 30

    def test_from_import_variable(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "config.py": "PI = 3.14\n",
                "main.py": "from config import PI\n\nresult = PI\n",
            },
            "main.py",
            Language.PYTHON,
        )
        assert result["result"] == 3.14

    def test_from_import_class(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "models.py": (
                    "class Dog:\n"
                    "    def __init__(self, name):\n"
                    "        self.name = name\n"
                ),
                "main.py": "from models import Dog\n\nd = Dog('Rex')\n",
            },
            "main.py",
            Language.PYTHON,
        )
        assert "d" in result

    def test_transitive_imports(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "base.py": "BASE = 10\n",
                "mid.py": "from base import BASE\n\ndef doubled():\n    return BASE + BASE\n",
                "main.py": "from mid import doubled\n\nresult = doubled()\n",
            },
            "main.py",
            Language.PYTHON,
        )
        assert result["result"] == 20

    def test_cross_module_method_call(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "math_utils.py": "def square(x):\n    return x * x\n",
                "geometry.py": (
                    "from math_utils import square\n\n"
                    "class Circle:\n"
                    "    def __init__(self, r):\n"
                    "        self.r = r\n"
                    "    def area(self):\n"
                    "        return square(self.r)\n"
                ),
                "main.py": "from geometry import Circle\n\nc = Circle(5)\na = c.area()\n",
            },
            "main.py",
            Language.PYTHON,
        )
        assert result["a"] == 25


# ── JavaScript ───────────────────────────────────────────────────


class TestJavaScriptMultiFile:
    def test_esm_named_import(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "math.js": "function add(a, b) { return a + b; }\n",
                "main.js": 'import { add } from "./math.js";\nvar result = add(10, 20);\n',
            },
            "main.js",
            Language.JAVASCRIPT,
        )
        assert result["result"] == 30

    def test_multiple_named_imports(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "ops.js": (
                    "function add(a, b) { return a + b; }\n"
                    "function mul(a, b) { return a * b; }\n"
                ),
                "main.js": (
                    'import { add, mul } from "./ops.js";\n'
                    "var s = add(3, 4);\n"
                    "var p = mul(3, 4);\n"
                ),
            },
            "main.js",
            Language.JAVASCRIPT,
        )
        assert result["s"] == 7
        assert result["p"] == 12


# ── TypeScript ───────────────────────────────────────────────────


class TestTypeScriptMultiFile:
    def test_ts_import(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "utils.ts": "function helper(x: number): number { return x + 1; }\n",
                "main.ts": (
                    'import { helper } from "./utils.ts";\n'
                    "let result: number = helper(41);\n"
                ),
            },
            "main.ts",
            Language.TYPESCRIPT,
        )
        assert result["result"] == 42


# ── Java ─────────────────────────────────────────────────────────


class TestJavaMultiFile:
    def test_two_classes(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "Utils.java": (
                    "public class Utils {\n"
                    "    public static int add(int a, int b) { return a + b; }\n"
                    "}\n"
                ),
                "Main.java": (
                    "import Utils;\n"
                    "public class Main {\n"
                    "    public static int main() {\n"
                    "        int result = Utils.add(10, 20);\n"
                    "        return result;\n"
                    "    }\n"
                    "}\n"
                    "int answer = Main.main();\n"
                ),
            },
            "Main.java",
            Language.JAVA,
        )
        assert result["answer"] == 30


# ── Go ───────────────────────────────────────────────────────────


class TestGoMultiFile:
    def test_relative_import(self, tmp_path):
        (tmp_path / "utils").mkdir()
        result = _run_project(
            tmp_path,
            {
                "utils/utils.go": (
                    "package utils\n" "func Add(a int, b int) int { return a + b }\n"
                ),
                "main.go": (
                    "package main\n" 'import "./utils"\n' "var result = Add(10, 20)\n"
                ),
            },
            "main.go",
            Language.GO,
        )
        assert result["result"] == 30


# ── Rust ─────────────────────────────────────────────────────────


class TestRustMultiFile:
    def test_mod_declaration(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "utils.rs": "pub fn add(a: i32, b: i32) -> i32 { a + b }\n",
                "main.rs": (
                    "mod utils;\n"
                    "fn main() -> i32 { let result = add(10, 20); result }\n"
                    "let answer = main();\n"
                ),
            },
            "main.rs",
            Language.RUST,
        )
        assert result["answer"] == 30


# ── C ────────────────────────────────────────────────────────────


class TestCMultiFile:
    def test_include(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "helper.h": "int add(int a, int b) { return a + b; }\n",
                "main.c": (
                    '#include "helper.h"\n'
                    "int main() { int result = add(10, 20); return result; }\n"
                    "int answer = main();\n"
                ),
            },
            "main.c",
            Language.C,
        )
        assert result["answer"] == 30


# ── C++ ──────────────────────────────────────────────────────────


class TestCppMultiFile:
    def test_include(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "util.h": "int add(int a, int b) { return a + b; }\n",
                "main.cpp": (
                    '#include "util.h"\n'
                    "int main() { int result = add(10, 20); return result; }\n"
                    "int answer = main();\n"
                ),
            },
            "main.cpp",
            Language.CPP,
        )
        assert result["answer"] == 30


# ── C# ───────────────────────────────────────────────────────────


class TestCSharpMultiFile:
    def test_using_directive(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "MathHelper.cs": (
                    "public class MathHelper {\n"
                    "    public static int Add(int a, int b) { return a + b; }\n"
                    "}\n"
                ),
                "Program.cs": (
                    "using MathHelper;\n"
                    "class Program {\n"
                    "    static int Main() { int result = MathHelper.Add(10, 20); return result; }\n"
                    "}\n"
                    "int answer = Program.Main();\n"
                ),
            },
            "Program.cs",
            Language.CSHARP,
        )
        assert result["answer"] == 30


# ── Kotlin ───────────────────────────────────────────────────────


class TestKotlinMultiFile:
    def test_import(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "Utils.kt": "fun add(a: Int, b: Int): Int { return a + b }\n",
                "Main.kt": "import Utils\nval result = add(10, 20)\n",
            },
            "Main.kt",
            Language.KOTLIN,
        )
        assert result["result"] == 30


# ── Scala ────────────────────────────────────────────────────────


class TestScalaMultiFile:
    def test_import(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "Utils.scala": "def add(a: Int, b: Int): Int = a + b\n",
                "Main.scala": "import Utils\nval result = add(10, 20)\n",
            },
            "Main.scala",
            Language.SCALA,
        )
        assert result["result"] == 30


# ── Ruby ─────────────────────────────────────────────────────────


class TestRubyMultiFile:
    def test_require_relative(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "utils.rb": "def helper(x)\n  x + 1\nend\n",
                "main.rb": 'require_relative "./utils"\n\nresult = helper(42)\n',
            },
            "main.rb",
            Language.RUBY,
        )
        assert result["result"] == 43


# ── PHP ──────────────────────────────────────────────────────────


class TestPhpMultiFile:
    def test_require_once(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "helpers.php": "<?php\nfunction add($a, $b) { return $a + $b; }\n",
                "main.php": '<?php\nrequire_once "helpers.php";\n$result = add(10, 20);\n',
            },
            "main.php",
            Language.PHP,
        )
        assert result["$result"] == 30


# ── Lua ──────────────────────────────────────────────────────────


class TestLuaMultiFile:
    def test_require(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "mathlib.lua": "function add(a, b)\n  return a + b\nend\n",
                "main.lua": 'require("mathlib")\n\nresult = add(10, 20)\n',
            },
            "main.lua",
            Language.LUA,
        )
        assert result["result"] == 30


# ── Pascal ───────────────────────────────────────────────────────


class TestPascalMultiFile:
    def test_uses(self, tmp_path):
        result = _run_project(
            tmp_path,
            {
                "MathUnit.pas": (
                    "function add(a, b: Integer): Integer;\n"
                    "begin\n"
                    "  Result := a + b;\n"
                    "end;\n"
                ),
                "main.pas": (
                    "uses MathUnit;\n"
                    "var answer: Integer;\n"
                    "begin\n"
                    "  answer := add(10, 20);\n"
                    "end.\n"
                ),
            },
            "main.pas",
            Language.PASCAL,
        )
        assert result["answer"] == 30


# ── COBOL ────────────────────────────────────────────────────────


_COBOL_JAR_PATH = os.environ.get(
    "PROLEAP_BRIDGE_JAR",
    os.path.expanduser(
        "~/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
    ),
)


class TestCobolMultiFile:
    """COBOL multi-file via CALL 'program-name'.

    Requires the ProLeap bridge JAR.
    """

    @pytest.fixture(autouse=True)
    def _set_bridge_jar(self):
        old = os.environ.get("PROLEAP_BRIDGE_JAR")
        os.environ["PROLEAP_BRIDGE_JAR"] = _COBOL_JAR_PATH
        yield
        if old is None:
            os.environ.pop("PROLEAP_BRIDGE_JAR", None)
        else:
            os.environ["PROLEAP_BRIDGE_JAR"] = old

    def test_call_subprogram(self, tmp_path):
        vm = _run_project_vm(
            tmp_path,
            {
                "HELPER.cbl": (
                    "       IDENTIFICATION DIVISION.\n"
                    "       PROGRAM-ID. HELPER.\n"
                    "       DATA DIVISION.\n"
                    "       WORKING-STORAGE SECTION.\n"
                    "       01 WS-VAL PIC 9(4) VALUE 0.\n"
                    "       PROCEDURE DIVISION.\n"
                    "           COMPUTE WS-VAL = 99.\n"
                ),
                "MAIN.cbl": (
                    "       IDENTIFICATION DIVISION.\n"
                    "       PROGRAM-ID. MAIN-PROG.\n"
                    "       DATA DIVISION.\n"
                    "       WORKING-STORAGE SECTION.\n"
                    "       01 WS-RESULT PIC 9(4) VALUE 0.\n"
                    "       PROCEDURE DIVISION.\n"
                    "           CALL 'HELPER'.\n"
                    "           COMPUTE WS-RESULT = 42.\n"
                    "           STOP RUN.\n"
                ),
            },
            "MAIN.cbl",
            Language.COBOL,
        )
        # Both modules compiled, linked, and executed.
        # HELPER runs first (dependency order), then MAIN.
        # Note: HELPER omits STOP RUN — in the linked model, STOP RUN
        # terminates the entire merged program. Only the entry module
        # should have STOP RUN. This is a simplification vs. real COBOL
        # runtime semantics where CALL returns control to the caller.
        assert len(vm.regions) == 2
        # Second region is MAIN's WS-RESULT: PIC 9(4) zoned = 0042
        main_region = vm.regions[list(vm.regions.keys())[1]]
        digits = [main_region[i] & 0x0F for i in range(4)]
        value = sum(d * (10 ** (3 - i)) for i, d in enumerate(digits))
        assert value == 42
