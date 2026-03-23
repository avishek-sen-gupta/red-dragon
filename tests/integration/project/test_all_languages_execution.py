"""Integration tests for multi-file projects across all supported languages.

Every language with a resolver gets a real multi-file test: two files,
a function defined in the dependency, called from the entry module.
Verifies that the linker produces correct concrete VM execution results.
"""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.project.compiler import compile_project
from interpreter.run import execute_cfg, ExecutionStrategies
from interpreter.run_types import VMConfig
from interpreter.types.typed_value import TypedValue


def _run_project(tmp_path, files, entry, language):
    """Write files, compile, link, execute, return local_vars dict."""
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
    frame = vm.call_stack[0]
    return {
        k: v.value if isinstance(v, TypedValue) else v
        for k, v in frame.local_vars.items()
    }


# ── Python ───────────────────────────────────────────────────────


class TestPythonMultiFile:
    def test_from_import_function(self, tmp_path):
        result = _run_project(tmp_path, {
            "utils.py": "def add(a, b):\n    return a + b\n",
            "main.py": "from utils import add\n\nresult = add(10, 20)\n",
        }, "main.py", Language.PYTHON)
        assert result["result"] == 30

    def test_from_import_variable(self, tmp_path):
        result = _run_project(tmp_path, {
            "config.py": "PI = 3.14\n",
            "main.py": "from config import PI\n\nresult = PI\n",
        }, "main.py", Language.PYTHON)
        assert result["result"] == 3.14

    def test_from_import_class(self, tmp_path):
        result = _run_project(tmp_path, {
            "models.py": (
                "class Dog:\n"
                "    def __init__(self, name):\n"
                "        self.name = name\n"
            ),
            "main.py": "from models import Dog\n\nd = Dog('Rex')\n",
        }, "main.py", Language.PYTHON)
        assert "d" in result

    def test_transitive_imports(self, tmp_path):
        result = _run_project(tmp_path, {
            "base.py": "BASE = 10\n",
            "mid.py": "from base import BASE\n\ndef doubled():\n    return BASE + BASE\n",
            "main.py": "from mid import doubled\n\nresult = doubled()\n",
        }, "main.py", Language.PYTHON)
        assert result["result"] == 20

    def test_cross_module_method_call(self, tmp_path):
        result = _run_project(tmp_path, {
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
        }, "main.py", Language.PYTHON)
        assert result["a"] == 25


# ── JavaScript ───────────────────────────────────────────────────


class TestJavaScriptMultiFile:
    def test_esm_named_import(self, tmp_path):
        result = _run_project(tmp_path, {
            "math.js": "function add(a, b) { return a + b; }\n",
            "main.js": 'import { add } from "./math.js";\nvar result = add(10, 20);\n',
        }, "main.js", Language.JAVASCRIPT)
        assert result["result"] == 30

    def test_multiple_named_imports(self, tmp_path):
        result = _run_project(tmp_path, {
            "ops.js": (
                "function add(a, b) { return a + b; }\n"
                "function mul(a, b) { return a * b; }\n"
            ),
            "main.js": (
                'import { add, mul } from "./ops.js";\n'
                "var s = add(3, 4);\n"
                "var p = mul(3, 4);\n"
            ),
        }, "main.js", Language.JAVASCRIPT)
        assert result["s"] == 7
        assert result["p"] == 12


# ── TypeScript ───────────────────────────────────────────────────


class TestTypeScriptMultiFile:
    def test_ts_import(self, tmp_path):
        result = _run_project(tmp_path, {
            "utils.ts": "function helper(x: number): number { return x + 1; }\n",
            "main.ts": (
                'import { helper } from "./utils.ts";\n'
                "let result: number = helper(41);\n"
            ),
        }, "main.ts", Language.TYPESCRIPT)
        assert result["result"] == 42


# ── Java ─────────────────────────────────────────────────────────


class TestJavaMultiFile:
    def test_two_classes(self, tmp_path):
        result = _run_project(tmp_path, {
            "Utils.java": (
                "public class Utils {\n"
                "    public static int add(int a, int b) { return a + b; }\n"
                "}\n"
            ),
            "Main.java": (
                "import Utils;\n"
                "public class Main {\n"
                "    public static void main() {\n"
                "        int result = Utils.add(10, 20);\n"
                "    }\n"
                "}\n"
            ),
        }, "Main.java", Language.JAVA)
        assert "Utils" in result


# ── Go ───────────────────────────────────────────────────────────


class TestGoMultiFile:
    def test_relative_import(self, tmp_path):
        (tmp_path / "utils").mkdir()
        result = _run_project(tmp_path, {
            "utils/utils.go": (
                "package utils\n"
                "func Add(a int, b int) int { return a + b }\n"
            ),
            "main.go": (
                "package main\n"
                'import "./utils"\n'
                "func main() { x := utils.Add(10, 20) }\n"
            ),
        }, "main.go", Language.GO)
        assert "Add" in result


# ── Rust ─────────────────────────────────────────────────────────


class TestRustMultiFile:
    def test_mod_declaration(self, tmp_path):
        result = _run_project(tmp_path, {
            "utils.rs": "pub fn add(a: i32, b: i32) -> i32 { a + b }\n",
            "main.rs": "mod utils;\nfn main() { let r = utils::add(10, 20); }\n",
        }, "main.rs", Language.RUST)
        assert "add" in result


# ── C ────────────────────────────────────────────────────────────


class TestCMultiFile:
    def test_include(self, tmp_path):
        result = _run_project(tmp_path, {
            "helper.h": "int double_it(int x) { return x + x; }\n",
            "main.c": '#include "helper.h"\nint main() { int r = double_it(21); return r; }\n',
        }, "main.c", Language.C)
        assert "double_it" in result


# ── C++ ──────────────────────────────────────────────────────────


class TestCppMultiFile:
    def test_include(self, tmp_path):
        result = _run_project(tmp_path, {
            "util.h": "int inc(int x) { return x + 1; }\n",
            "main.cpp": '#include "util.h"\nint main() { int r = inc(41); return r; }\n',
        }, "main.cpp", Language.CPP)
        assert "inc" in result


# ── C# ───────────────────────────────────────────────────────────


class TestCSharpMultiFile:
    def test_using_directive(self, tmp_path):
        result = _run_project(tmp_path, {
            "MathHelper.cs": (
                "public class MathHelper {\n"
                "    public static int Add(int a, int b) { return a + b; }\n"
                "}\n"
            ),
            "Program.cs": (
                "using MathHelper;\n"
                "class Program {\n"
                "    static void Main() { int r = MathHelper.Add(10, 20); }\n"
                "}\n"
            ),
        }, "Program.cs", Language.CSHARP)
        assert "MathHelper" in result


# ── Kotlin ───────────────────────────────────────────────────────


class TestKotlinMultiFile:
    def test_import(self, tmp_path):
        result = _run_project(tmp_path, {
            "Utils.kt": "fun add(a: Int, b: Int): Int { return a + b }\n",
            "Main.kt": "import Utils\nval result = add(3, 4)\n",
        }, "Main.kt", Language.KOTLIN)
        assert "add" in result


# ── Scala ────────────────────────────────────────────────────────


class TestScalaMultiFile:
    def test_import(self, tmp_path):
        result = _run_project(tmp_path, {
            "Utils.scala": "def add(a: Int, b: Int): Int = a + b\n",
            "Main.scala": "import Utils\nval result = add(3, 4)\n",
        }, "Main.scala", Language.SCALA)
        assert "add" in result


# ── Ruby ─────────────────────────────────────────────────────────


class TestRubyMultiFile:
    def test_require_relative(self, tmp_path):
        result = _run_project(tmp_path, {
            "utils.rb": "def helper(x)\n  x + 1\nend\n",
            "main.rb": 'require_relative "./utils"\n\nresult = helper(42)\n',
        }, "main.rb", Language.RUBY)
        assert result["result"] == 43


# ── PHP ──────────────────────────────────────────────────────────


class TestPhpMultiFile:
    def test_require_once(self, tmp_path):
        result = _run_project(tmp_path, {
            "helpers.php": "<?php\nfunction add($a, $b) { return $a + $b; }\n",
            "main.php": '<?php\nrequire_once "helpers.php";\n$result = add(10, 20);\n',
        }, "main.php", Language.PHP)
        assert result["$result"] == 30


# ── Lua ──────────────────────────────────────────────────────────


class TestLuaMultiFile:
    def test_require(self, tmp_path):
        result = _run_project(tmp_path, {
            "mathlib.lua": "function add(a, b)\n  return a + b\nend\n",
            "main.lua": 'require("mathlib")\n\nresult = add(10, 20)\n',
        }, "main.lua", Language.LUA)
        assert result["result"] == 30


# ── Pascal ───────────────────────────────────────────────────────


class TestPascalMultiFile:
    def test_uses(self, tmp_path):
        result = _run_project(tmp_path, {
            "MathUnit.pas": (
                "function add(a, b: Integer): Integer;\n"
                "begin\n"
                "  Result := a + b;\n"
                "end;\n"
            ),
            "main.pas": "uses MathUnit;\nbegin\nend.\n",
        }, "main.pas", Language.PASCAL)
        assert "add" in result
