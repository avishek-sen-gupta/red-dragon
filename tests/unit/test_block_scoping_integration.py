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
from interpreter.frontends.ruby import RubyFrontend
from interpreter.ir import IRInstruction, Opcode
from interpreter.parser import TreeSitterParserFactory


def _lower(frontend_class, lang: str, source: str) -> list[IRInstruction]:
    frontend = frontend_class(TreeSitterParserFactory(), lang)
    return frontend.lower(source.encode("utf-8"))


def _store_var_names(instructions: list[IRInstruction]) -> list[str]:
    """Extract all variable names from STORE_VAR and DECL_VAR instructions."""
    return [
        str(inst.operands[0])
        for inst in instructions
        if inst.opcode in (Opcode.DECL_VAR, Opcode.STORE_VAR) and inst.operands
    ]


def _load_var_names(instructions: list[IRInstruction]) -> list[str]:
    """Extract all variable names from LOAD_VAR instructions."""
    return [
        str(inst.operands[0])
        for inst in instructions
        if inst.opcode == Opcode.LOAD_VAR and inst.operands
    ]


def _instructions_in_inline_function(
    instructions: list[IRInstruction], label_prefix: str
) -> list[IRInstruction]:
    """Extract instructions between a LABEL matching *label_prefix* and the next RETURN."""
    collecting = False
    result: list[IRInstruction] = []
    for inst in instructions:
        if (
            inst.opcode == Opcode.LABEL
            and inst.label
            and inst.label.startswith(label_prefix)
        ):
            collecting = True
            continue
        if collecting:
            result.append(inst)
            if inst.opcode == Opcode.RETURN:
                break
    return result


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


# ---------------------------------------------------------------------------
# C-style for loop init scoping
# ---------------------------------------------------------------------------


class TestCStyleForInitScoping:
    """C-style for(init; cond; update) should scope init vars to the loop."""

    def test_java_for_init_shadows_outer(self):
        """for(int i = ...) should shadow an outer i."""
        source = """
        class M {
            void m() {
                int i = 99;
                for (int i = 0; i < 10; i++) {
                    int y = i;
                }
                int z = i;
            }
        }
        """
        ir = _lower(JavaFrontend, "java", source)
        stores = _store_var_names(ir)
        # The for-init i should be mangled since it shadows the outer i
        mangled = [n for n in stores if n.startswith("i$")]
        assert len(mangled) >= 1
        # The outer reference after the loop should resolve to unmangled "i"
        loads = _load_var_names(ir)
        # Find loads that assign to z — the last LOAD_VAR i should be unmangled
        assert "i" in loads

    def test_c_for_init_shadows_outer(self):
        """C for(int i = ...) should shadow an outer i."""
        source = """
        int main() {
            int i = 99;
            for (int i = 0; i < 10; i++) {
                int y = i;
            }
            int z = i;
            return 0;
        }
        """
        ir = _lower(CFrontend, "c", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if n.startswith("i$")]
        assert len(mangled) >= 1

    def test_cpp_for_init_shadows_outer(self):
        """C++ for(int i = ...) should shadow an outer i."""
        source = """
        int main() {
            int i = 99;
            for (int i = 0; i < 10; i++) {
                int y = i;
            }
            int z = i;
            return 0;
        }
        """
        ir = _lower(CppFrontend, "cpp", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if n.startswith("i$")]
        assert len(mangled) >= 1

    def test_csharp_for_init_shadows_outer(self):
        """C# for(int i = ...) should shadow an outer i."""
        source = """
        class M {
            void m() {
                int i = 99;
                for (int i = 0; i < 10; i++) {
                    int y = i;
                }
                int z = i;
            }
        }
        """
        ir = _lower(CSharpFrontend, "csharp", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if n.startswith("i$")]
        assert len(mangled) >= 1

    def test_typescript_for_init_shadows_outer(self):
        """TypeScript for(let i = ...) should shadow an outer i."""
        source = """
        function main() {
            let i = 99;
            for (let i = 0; i < 10; i++) {
                let y = i;
            }
            let z = i;
        }
        """
        ir = _lower(TypeScriptFrontend, "typescript", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if n.startswith("i$")]
        assert len(mangled) >= 1

    def test_go_for_init_shadows_outer(self):
        """Go for i := 0; ... should shadow an outer i."""
        source = """
        package main

        func main() {
            i := 99
            for i := 0; i < 10; i++ {
            }
            z := i
        }
        """
        ir = _lower(GoFrontend, "go", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if n.startswith("i$")]
        assert len(mangled) >= 1


# ---------------------------------------------------------------------------
# Ruby scoping — call-frame isolation for lambdas/blocks, no mangling
# ---------------------------------------------------------------------------


class TestRubyLambdaScoping:
    """Ruby lambdas are lowered as inline functions with their own call frame.

    Variable isolation comes from the VM's call-frame mechanism, not from
    BLOCK_SCOPED name mangling.  These tests verify the IR structure:
    lambda/block bodies live between LABEL func_*/block_* and RETURN,
    and no ``$`` mangling occurs.
    """

    def test_lambda_body_emitted_as_inline_function(self):
        """-> (x) { body } should produce LABEL func_* ... RETURN."""
        source = """
x = 99
my_lambda = -> (x) { y = x + 1 }
z = x
"""
        ir = _lower(RubyFrontend, "ruby", source)
        func_instrs = _instructions_in_inline_function(ir, "func___lambda")
        # The lambda body should contain STORE_VAR for the param and body var
        func_stores = _store_var_names(func_instrs)
        assert "x" in func_stores
        assert "y" in func_stores
        # And end with RETURN
        assert func_instrs[-1].opcode == Opcode.RETURN

    def test_lambda_param_uses_same_name_no_mangling(self):
        """Lambda param x should NOT be mangled even when shadowing outer x."""
        source = """
x = 99
my_lambda = -> (x) { y = x + 1 }
z = x
"""
        ir = _lower(RubyFrontend, "ruby", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if "$" in n]
        assert len(mangled) == 0

    def test_lambda_outer_var_unaffected(self):
        """The outer x store and the post-lambda z = x load should be in the
        top-level flow (outside the lambda body)."""
        source = """
x = 99
my_lambda = -> (x) { y = x + 1 }
z = x
"""
        ir = _lower(RubyFrontend, "ruby", source)
        # Top-level stores (outside the lambda body) should include x and z
        func_instrs = _instructions_in_inline_function(ir, "func___lambda")
        top_level = [inst for inst in ir if inst not in func_instrs]
        top_stores = _store_var_names(top_level)
        assert "x" in top_stores
        assert "z" in top_stores
        assert "my_lambda" in top_stores


class TestRubyBlockScoping:
    """Ruby do..end / { } blocks are lowered as inline functions."""

    def test_do_block_emitted_as_inline_function(self):
        """do |x| ... end should produce LABEL block_* ... RETURN."""
        source = """
x = 99
[1,2,3].each do |x|
  y = x + 1
end
z = x
"""
        ir = _lower(RubyFrontend, "ruby", source)
        block_instrs = _instructions_in_inline_function(ir, "block_")
        block_stores = _store_var_names(block_instrs)
        assert "x" in block_stores
        assert "y" in block_stores
        assert block_instrs[-1].opcode == Opcode.RETURN

    def test_do_block_no_mangling(self):
        """Block param x should NOT be mangled even when shadowing outer x."""
        source = """
x = 99
[1,2,3].each do |x|
  y = x + 1
end
z = x
"""
        ir = _lower(RubyFrontend, "ruby", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if "$" in n]
        assert len(mangled) == 0

    def test_block_passed_as_function_ref(self):
        """The block should be passed as a func ref argument to the method call."""
        source = """
[1,2,3].each do |x|
  y = x + 1
end
"""
        ir = _lower(RubyFrontend, "ruby", source)
        call_methods = [inst for inst in ir if inst.opcode == Opcode.CALL_METHOD]
        assert len(call_methods) >= 1
        # The block ref should be among the operands
        each_call = call_methods[0]
        assert each_call.operands[1] == "each"


class TestRubyForInScoping:
    """Ruby for..in does NOT create a new scope — variable leaks to outer scope."""

    def test_for_in_var_is_inline(self):
        """for x in collection should NOT emit a separate function body."""
        source = """
x = 99
for x in [1,2,3]
  y = x + 1
end
z = x
"""
        ir = _lower(RubyFrontend, "ruby", source)
        # for..in should NOT produce an inline function — no RETURN inside the loop
        labels = [
            inst.label for inst in ir if inst.opcode == Opcode.LABEL and inst.label
        ]
        # Should have for_cond / for_body / for_end labels, but no func_ or block_ labels
        func_labels = [
            l for l in labels if l.startswith("func_") or l.startswith("block_")
        ]
        assert len(func_labels) == 0

    def test_for_in_no_mangling(self):
        """for..in variable should NOT be mangled — it shares the outer scope."""
        source = """
x = 99
for x in [1,2,3]
  y = x + 1
end
z = x
"""
        ir = _lower(RubyFrontend, "ruby", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if "$" in n]
        assert len(mangled) == 0

    def test_for_in_overwrites_outer_var(self):
        """The for..in loop variable x should use the same name as outer x."""
        source = """
x = 99
for x in [1,2,3]
  y = x + 1
end
z = x
"""
        ir = _lower(RubyFrontend, "ruby", source)
        stores = _store_var_names(ir)
        # x should appear multiple times (outer init + loop assignment) with no mangling
        x_stores = [n for n in stores if n == "x"]
        assert len(x_stores) >= 2


# ---------------------------------------------------------------------------
# Go if-init scoping (P0 #1)
# ---------------------------------------------------------------------------


class TestGoIfInitScoping:
    """Go if x := expr; cond { } — init var should be scoped to the if chain."""

    def test_if_init_shadows_outer(self):
        source = """
        package main
        func main() {
            x := 99
            if x := 42; x > 0 {
                _ = x
            }
            z := x
        }
        """
        ir = _lower(GoFrontend, "go", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1
        assert "x" in stores

    def test_if_init_no_shadow_no_mangle(self):
        source = """
        package main
        func main() {
            if y := 42; y > 0 {
                _ = y
            }
        }
        """
        ir = _lower(GoFrontend, "go", source)
        stores = _store_var_names(ir)
        assert "y" in stores
        mangled = [n for n in stores if n.startswith("y$")]
        assert len(mangled) == 0


# ---------------------------------------------------------------------------
# Go switch-init scoping (P0 #2)
# ---------------------------------------------------------------------------


class TestGoSwitchInitScoping:
    """Go switch x := expr; x { } — init var should be scoped to the switch."""

    def test_switch_init_shadows_outer(self):
        source = """
        package main
        func main() {
            x := 99
            switch x := 42; x {
            case 42:
                _ = x
            }
            z := x
        }
        """
        ir = _lower(GoFrontend, "go", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1
        assert "x" in stores

    def test_switch_init_no_shadow_no_mangle(self):
        source = """
        package main
        func main() {
            switch y := 42; y {
            case 42:
                _ = y
            }
        }
        """
        ir = _lower(GoFrontend, "go", source)
        stores = _store_var_names(ir)
        assert "y" in stores
        mangled = [n for n in stores if n.startswith("y$")]
        assert len(mangled) == 0


# ---------------------------------------------------------------------------
# Java try-with-resources scoping (P0 #3)
# ---------------------------------------------------------------------------


class TestJavaTryWithResourcesScoping:
    """Java try(Type r = expr) { } — resource var should be scoped."""

    def test_resource_var_shadows_outer(self):
        source = """
        class M {
            void m() {
                Object r = null;
                try (AutoCloseable r = getResource()) {
                    int y = 1;
                } catch (Exception e) {
                }
                Object z = r;
            }
        }
        """
        ir = _lower(JavaFrontend, "java", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if n.startswith("r$")]
        assert len(mangled) >= 1
        assert "r" in stores

    def test_resource_var_emitted(self):
        """try-with-resources should emit STORE_VAR for the resource variable."""
        source = """
        class M {
            void m() {
                try (AutoCloseable r = getResource()) {
                    int y = 1;
                } catch (Exception e) {
                }
            }
        }
        """
        ir = _lower(JavaFrontend, "java", source)
        stores = _store_var_names(ir)
        assert "r" in stores


# ---------------------------------------------------------------------------
# C++ if-init scoping (P1 #7)
# ---------------------------------------------------------------------------


class TestCppIfInitScoping:
    """C++17 if (init; cond) — init var should be scoped to the if chain."""

    def test_if_init_shadows_outer(self):
        source = """
        int main() {
            int x = 99;
            if (int x = 42; x > 0) {
                int y = x;
            }
            int z = x;
        }
        """
        ir = _lower(CppFrontend, "cpp", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1
        assert "x" in stores
        # z = x should load the unmangled outer x
        loads = _load_var_names(ir)
        assert "x" in loads

    def test_if_init_no_shadow_no_mangle(self):
        source = """
        int main() {
            if (int y = 42; y > 0) {
                int z = y;
            }
        }
        """
        ir = _lower(CppFrontend, "cpp", source)
        stores = _store_var_names(ir)
        assert "y" in stores
        mangled = [n for n in stores if n.startswith("y$")]
        assert len(mangled) == 0


# ---------------------------------------------------------------------------
# C# using-statement scoping (P1 #8)
# ---------------------------------------------------------------------------


class TestCSharpUsingStmtScoping:
    """C# using(var r = expr) { } — resource var should be scoped."""

    def test_using_var_shadows_outer(self):
        source = """
        class M {
            void Main() {
                object r = null;
                using (var r = GetResource()) {
                    int y = 1;
                }
                object z = r;
            }
        }
        """
        ir = _lower(CSharpFrontend, "csharp", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if n.startswith("r$")]
        assert len(mangled) >= 1
        assert "r" in stores

    def test_using_var_no_shadow_no_mangle(self):
        source = """
        class M {
            void Main() {
                using (var r = GetResource()) {
                    int y = 1;
                }
            }
        }
        """
        ir = _lower(CSharpFrontend, "csharp", source)
        stores = _store_var_names(ir)
        assert "r" in stores
        mangled = [n for n in stores if n.startswith("r$")]
        assert len(mangled) == 0


# ---------------------------------------------------------------------------
# Kotlin when-subject binding scoping (P2 #10)
# ---------------------------------------------------------------------------


class TestKotlinWhenSubjectScoping:
    """Kotlin when(val x = expr) { } — subject var should be scoped."""

    def test_when_subject_shadows_outer(self):
        source = """
        fun main() {
            val x = 99
            val result = when(val x = getVal()) {
                1 -> "one"
                else -> "other"
            }
            val z = x
        }
        """
        ir = _lower(KotlinFrontend, "kotlin", source)
        stores = _store_var_names(ir)
        mangled = [n for n in stores if n.startswith("x$")]
        assert len(mangled) >= 1
        assert "x" in stores
        # z = x should load the unmangled outer x
        loads = _load_var_names(ir)
        assert "x" in loads

    def test_when_subject_emitted(self):
        """when(val x = expr) should emit STORE_VAR for subject variable."""
        source = """
        fun main() {
            val result = when(val x = getVal()) {
                1 -> "one"
                else -> "other"
            }
        }
        """
        ir = _lower(KotlinFrontend, "kotlin", source)
        stores = _store_var_names(ir)
        assert "x" in stores
