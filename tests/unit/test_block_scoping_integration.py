"""Unit tests for block-scope integration into language frontends.

Verifies that block-scoped frontends (Java, C, C++, C#, Rust, Go, Kotlin,
Scala, TypeScript) correctly mangle shadowed variable names in IR output
and that function-scoped frontends (Python, JavaScript var) do NOT.
"""

from __future__ import annotations

from interpreter.frontends.java import JavaFrontend
from interpreter.frontends.c import CFrontend
from interpreter.frontends.cpp import CppFrontend
from interpreter.frontends.csharp import CSharpFrontend
from interpreter.frontends.rust import RustFrontend
from interpreter.frontends.go import GoFrontend
from interpreter.frontends.kotlin import KotlinFrontend
from interpreter.frontends.scala import ScalaFrontend
from interpreter.frontends.typescript import TypeScriptFrontend
from interpreter.frontends.python import PythonFrontend
from interpreter.frontends.javascript import JavaScriptFrontend
from interpreter.ir import IRInstruction, Opcode
from interpreter.parser import TreeSitterParserFactory


def _lower(frontend_class, lang: str, source: str) -> list[IRInstruction]:
    frontend = frontend_class(TreeSitterParserFactory(), lang)
    return frontend.lower(source.encode("utf-8"))


def _store_var_names(instructions: list[IRInstruction]) -> list[str]:
    """Extract all variable names from STORE_VAR instructions."""
    return [
        str(inst.operands[0])
        for inst in instructions
        if inst.opcode == Opcode.STORE_VAR and inst.operands
    ]


def _load_var_names(instructions: list[IRInstruction]) -> list[str]:
    """Extract all variable names from LOAD_VAR instructions."""
    return [
        str(inst.operands[0])
        for inst in instructions
        if inst.opcode == Opcode.LOAD_VAR and inst.operands
    ]


# ---------------------------------------------------------------------------
# Java block scoping
# ---------------------------------------------------------------------------


class TestJavaBlockScoping:
    def test_no_shadow_preserves_original_name(self):
        """A single variable declaration should not be mangled."""
        source = "class M { void m() { int x = 10; } }"
        ir = _lower(JavaFrontend, "java", source)
        stores = _store_var_names(ir)
        assert "x" in stores

    def test_shadowed_var_gets_mangled_name(self):
        """Inner block re-declaring x should produce a mangled x$N."""
        source = """
        class M {
            void m() {
                int x = 1;
                {
                    int x = 2;
                }
            }
        }
        """
        ir = _lower(JavaFrontend, "java", source)
        stores = _store_var_names(ir)
        # The outer x should remain "x"
        assert "x" in stores
        # The inner x should be mangled (x$1 or similar)
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1

    def test_inner_reference_resolves_to_mangled(self):
        """Reading x inside the shadow block should use the mangled name."""
        source = """
        class M {
            void m() {
                int x = 1;
                {
                    int x = 2;
                    int y = x + 1;
                }
            }
        }
        """
        ir = _lower(JavaFrontend, "java", source)
        loads = _load_var_names(ir)
        # Inside the inner block, loads of x should use the mangled name
        mangled_loads = [n for n in loads if n.startswith("x$")]
        assert len(mangled_loads) >= 1

    def test_outer_reference_after_block_resolves_to_original(self):
        """After exiting the inner block, x should resolve to the original name."""
        source = """
        class M {
            void m() {
                int x = 1;
                {
                    int x = 2;
                }
                int y = x + 1;
            }
        }
        """
        ir = _lower(JavaFrontend, "java", source)
        # Find all LOAD_VAR instructions
        loads = _load_var_names(ir)
        # The last load of x (after the block) should be the original "x"
        assert "x" in loads

    def test_metadata_recorded_for_mangled_var(self):
        """The frontend should record VarScopeInfo metadata for mangled names."""
        source = """
        class M {
            void m() {
                int x = 1;
                {
                    int x = 2;
                }
            }
        }
        """
        frontend = JavaFrontend(TreeSitterParserFactory(), "java")
        frontend.lower(source.encode("utf-8"))
        metadata = frontend.type_env_builder.var_scope_metadata
        mangled_keys = [k for k in metadata if k.startswith("x$")]
        assert len(mangled_keys) >= 1
        info = metadata[mangled_keys[0]]
        assert info.original_name == "x"
        assert info.scope_depth >= 1


# ---------------------------------------------------------------------------
# C block scoping
# ---------------------------------------------------------------------------


class TestCBlockScoping:
    def test_no_shadow_preserves_name(self):
        source = "int main() { int x = 10; return x; }"
        ir = _lower(CFrontend, "c", source)
        stores = _store_var_names(ir)
        assert "x" in stores

    def test_shadowed_var_in_inner_block(self):
        source = """
        int main() {
            int x = 1;
            {
                int x = 2;
            }
            return x;
        }
        """
        ir = _lower(CFrontend, "c", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


# ---------------------------------------------------------------------------
# C++ block scoping
# ---------------------------------------------------------------------------


class TestCppBlockScoping:
    def test_shadowed_var_in_inner_block(self):
        source = """
        int main() {
            int x = 1;
            {
                int x = 2;
            }
            return x;
        }
        """
        ir = _lower(CppFrontend, "cpp", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


# ---------------------------------------------------------------------------
# C# block scoping
# ---------------------------------------------------------------------------


class TestCSharpBlockScoping:
    def test_shadowed_var_in_inner_block(self):
        source = """
        class M {
            void Main() {
                int x = 1;
                {
                    int x = 2;
                }
            }
        }
        """
        ir = _lower(CSharpFrontend, "csharp", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


# ---------------------------------------------------------------------------
# Rust block scoping
# ---------------------------------------------------------------------------


class TestRustBlockScoping:
    def test_shadowed_let_in_inner_block(self):
        source = """
        fn main() {
            let x = 1;
            {
                let x = 2;
            }
        }
        """
        ir = _lower(RustFrontend, "rust", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


# ---------------------------------------------------------------------------
# Go block scoping
# ---------------------------------------------------------------------------


class TestGoBlockScoping:
    def test_shadowed_short_var_in_inner_block(self):
        source = """
        package main
        func main() {
            x := 1
            {
                x := 2
                _ = x
            }
        }
        """
        ir = _lower(GoFrontend, "go", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


# ---------------------------------------------------------------------------
# Kotlin block scoping
# ---------------------------------------------------------------------------


class TestKotlinBlockScoping:
    def test_shadowed_val_in_inner_block(self):
        source = """
        fun main() {
            val x = 1
            if (true) {
                val x = 2
            }
        }
        """
        ir = _lower(KotlinFrontend, "kotlin", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


# ---------------------------------------------------------------------------
# Scala block scoping
# ---------------------------------------------------------------------------


class TestScalaBlockScoping:
    def test_shadowed_val_in_inner_block(self):
        source = """
        object Main {
            def main(): Unit = {
                val x = 1
                {
                    val x = 2
                }
            }
        }
        """
        ir = _lower(ScalaFrontend, "scala", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


# ---------------------------------------------------------------------------
# TypeScript block scoping (let/const are block-scoped)
# ---------------------------------------------------------------------------


class TestTypeScriptBlockScoping:
    def test_shadowed_let_in_inner_block(self):
        source = """
        function main() {
            let x = 1;
            {
                let x = 2;
            }
        }
        """
        ir = _lower(TypeScriptFrontend, "typescript", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


# ---------------------------------------------------------------------------
# Loop variable scoping (P1 gaps)
# ---------------------------------------------------------------------------


class TestJavaForEachScoping:
    def test_enhanced_for_var_shadows_outer(self):
        """Enhanced for loop variable shadowing outer should mangle."""
        source = """
        class M {
            void m() {
                int x = 0;
                int[] arr = {1, 2, 3};
                for (int x : arr) {
                    int y = x;
                }
            }
        }
        """
        ir = _lower(JavaFrontend, "java", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


class TestCppRangeForScoping:
    def test_range_for_var_shadows_outer(self):
        source = """
        int main() {
            int x = 0;
            int arr[] = {1, 2, 3};
            for (int x : arr) {
                int y = x;
            }
        }
        """
        ir = _lower(CppFrontend, "cpp", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


class TestCSharpForeachScoping:
    def test_foreach_var_shadows_outer(self):
        source = """
        class M {
            void Main() {
                int x = 0;
                int[] arr = {1, 2, 3};
                foreach (int x in arr) {
                    int y = x;
                }
            }
        }
        """
        ir = _lower(CSharpFrontend, "csharp", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


class TestRustForInScoping:
    def test_for_in_var_shadows_outer(self):
        source = """
        fn main() {
            let x = 0;
            let arr = vec![1, 2, 3];
            for x in arr {
                let y = x;
            }
        }
        """
        ir = _lower(RustFrontend, "rust", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


class TestGoRangeScoping:
    def test_range_var_shadows_outer(self):
        source = """
        package main
        func main() {
            x := 0
            arr := []int{1, 2, 3}
            for x, _ := range arr {
                _ = x
            }
            _ = x
        }
        """
        ir = _lower(GoFrontend, "go", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


class TestKotlinForScoping:
    def test_for_var_shadows_outer(self):
        source = """
        fun main() {
            val x = 0
            val arr = listOf(1, 2, 3)
            for (x in arr) {
                val y = x
            }
        }
        """
        ir = _lower(KotlinFrontend, "kotlin", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


class TestTypeScriptForOfScoping:
    def test_for_of_var_shadows_outer(self):
        source = """
        function main() {
            let x = 0;
            let arr = [1, 2, 3];
            for (let x of arr) {
                let y = x;
            }
        }
        """
        ir = _lower(TypeScriptFrontend, "typescript", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


# ---------------------------------------------------------------------------
# Catch variable scoping (P2 gap)
# ---------------------------------------------------------------------------


class TestJavaCatchVarScoping:
    def test_catch_var_shadows_outer(self):
        source = """
        class M {
            void m() {
                int e = 0;
                try {
                    int x = 1;
                } catch (Exception e) {
                    int y = 2;
                }
            }
        }
        """
        ir = _lower(JavaFrontend, "java", source)
        stores = _store_var_names(ir)
        assert "e" in stores
        mangled = [n for n in stores if n.startswith("e$")]
        assert len(mangled) >= 1


class TestJavaScriptForInScoping:
    def test_for_in_var_shadows_outer(self):
        source = """
        function main() {
            let x = 0;
            let obj = {a: 1, b: 2};
            for (let x in obj) {
                let y = x;
            }
        }
        """
        ir = _lower(TypeScriptFrontend, "typescript", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


class TestScalaForComprehensionScoping:
    def test_for_comprehension_var_shadows_outer(self):
        source = """
        object Main {
            def main(): Unit = {
                val x = 0
                for (x <- List(1, 2, 3)) {
                    val y = x
                }
            }
        }
        """
        ir = _lower(ScalaFrontend, "scala", source)
        stores = _store_var_names(ir)
        assert "x" in stores
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1


class TestCSharpCatchVarScoping:
    def test_catch_var_shadows_outer(self):
        source = """
        class M {
            void Main() {
                int e = 0;
                try {
                    int x = 1;
                } catch (Exception e) {
                    int y = 2;
                }
            }
        }
        """
        ir = _lower(CSharpFrontend, "csharp", source)
        stores = _store_var_names(ir)
        assert "e" in stores
        mangled = [n for n in stores if n.startswith("e$")]
        assert len(mangled) >= 1


class TestCppCatchVarScoping:
    def test_catch_var_shadows_outer(self):
        source = """
        int main() {
            int e = 0;
            try {
                int x = 1;
            } catch (std::exception& e) {
                int y = 2;
            }
        }
        """
        ir = _lower(CppFrontend, "cpp", source)
        stores = _store_var_names(ir)
        assert "e" in stores
        mangled = [n for n in stores if n.startswith("e$")]
        assert len(mangled) >= 1


class TestKotlinCatchVarScoping:
    def test_catch_var_shadows_outer(self):
        source = """
        fun main() {
            val e = 0
            try {
                val x = 1
            } catch (e: Exception) {
                val y = 2
            }
        }
        """
        ir = _lower(KotlinFrontend, "kotlin", source)
        stores = _store_var_names(ir)
        assert "e" in stores
        mangled = [n for n in stores if n.startswith("e$")]
        assert len(mangled) >= 1


class TestTypeScriptCatchVarScoping:
    def test_catch_var_shadows_outer(self):
        source = """
        function main() {
            let e = 0;
            try {
                let x = 1;
            } catch (e) {
                let y = 2;
            }
        }
        """
        ir = _lower(TypeScriptFrontend, "typescript", source)
        stores = _store_var_names(ir)
        assert "e" in stores
        mangled = [n for n in stores if n.startswith("e$")]
        assert len(mangled) >= 1


class TestScalaCatchVarScoping:
    def test_catch_var_shadows_outer(self):
        source = """
        object Main {
            def main(): Unit = {
                val e = 0
                try {
                    val x = 1
                } catch {
                    case e: Exception => val y = 2
                }
            }
        }
        """
        ir = _lower(ScalaFrontend, "scala", source)
        stores = _store_var_names(ir)
        assert "e" in stores
        mangled = [n for n in stores if n.startswith("e$")]
        assert len(mangled) >= 1


# ---------------------------------------------------------------------------
# Function-scoped languages should NOT mangle
# ---------------------------------------------------------------------------


class TestFunctionScopedNoMangling:
    def test_python_no_mangling(self):
        """Python variables are function-scoped — no mangling should occur."""
        source = """
x = 1
if True:
    x = 2
"""
        ir = _lower(PythonFrontend, "python", source)
        stores = _store_var_names(ir)
        # No mangled names — both stores should be "x"
        assert all(n == "x" for n in stores if n.startswith("x"))
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) == 0

    def test_javascript_no_mangling(self):
        """JavaScript var is function-scoped — no mangling should occur."""
        source = """
        function main() {
            var x = 1;
            if (true) {
                var x = 2;
            }
        }
        """
        ir = _lower(JavaScriptFrontend, "javascript", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) == 0
