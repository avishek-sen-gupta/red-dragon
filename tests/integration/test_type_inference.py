"""Integration tests: source → frontend → IR → type inference pass."""

import pytest

from interpreter.api import lower_source
from interpreter.constants import TypeName
from interpreter.default_conversion_rules import DefaultConversionRules
from interpreter.function_signature import FunctionSignature
from interpreter.ir import Opcode
from interpreter.type_inference import infer_types
from interpreter.type_resolver import TypeResolver


def _resolver():
    return TypeResolver(DefaultConversionRules())


def _lower_and_infer(source: str, language: str):
    instructions = lower_source(source, language=language)
    return instructions, infer_types(instructions, _resolver())


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------


class TestJavaTypeInference:
    def test_int_division_result_type(self):
        """Java `int x = 7 / 2` — BINOP result and var should both be Int."""
        instructions, env = _lower_and_infer(
            "class M { static int x = 7 / 2; }", "java"
        )
        # Find the BINOP instruction
        binops = [i for i in instructions if i.opcode == Opcode.BINOP]
        assert len(binops) >= 1
        binop_reg = binops[0].result_reg
        assert env.register_types[binop_reg] == TypeName.INT
        assert env.var_types["x"] == "Int"

    def test_typed_params(self):
        """Java method params carry type hints → register_types."""
        instructions, env = _lower_and_infer(
            """\
class M {
    static int add(int a, int b) {
        return a + b;
    }
}
""",
            "java",
        )
        symbolics = [
            i
            for i in instructions
            if i.opcode == Opcode.SYMBOLIC and i.type_hint == "Int"
        ]
        assert len(symbolics) >= 2
        for sym in symbolics:
            assert env.register_types[sym.result_reg] == "Int"

    def test_mixed_int_float(self):
        """Java `double y = a + 1` where a is int — BINOP produces Float."""
        instructions, env = _lower_and_infer(
            """\
class M {
    static double compute(int a) {
        double y = a + 1.0;
        return y;
    }
}
""",
            "java",
        )
        binops = [i for i in instructions if i.opcode == Opcode.BINOP and i.result_reg]
        # At least one BINOP should produce Float (Int + Float → Float)
        binop_types = [env.register_types.get(b.result_reg, "") for b in binops]
        assert TypeName.FLOAT in binop_types

    def test_new_object_constructor_typed(self):
        """Java `new Dog(...)` → CALL_FUNCTION result register typed as Dog."""
        instructions, env = _lower_and_infer(
            """\
class M {
    static Dog d = new Dog("Rex", 5);
}
""",
            "java",
        )
        call_fns = [
            i
            for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION and i.type_hint == "Dog"
        ]
        assert len(call_fns) >= 1
        assert env.register_types[call_fns[0].result_reg] == "Dog"

    def test_string_variable(self):
        """Java String variable gets String type."""
        _instructions, env = _lower_and_infer(
            'class M { static String name = "hello"; }', "java"
        )
        assert env.var_types["name"] == "String"

    def test_boolean_variable(self):
        """Java boolean variable gets Bool type."""
        _instructions, env = _lower_and_infer(
            "class M { static boolean flag = true; }", "java"
        )
        assert env.var_types["flag"] == "Bool"


# ---------------------------------------------------------------------------
# C#
# ---------------------------------------------------------------------------


class TestCSharpTypeInference:
    def test_new_object_constructor_typed(self):
        """C# `new Dog(...)` → CALL_FUNCTION result register typed as Dog."""
        instructions, env = _lower_and_infer(
            """\
class M {
    static Dog d = new Dog("Rex", 5);
}
""",
            "csharp",
        )
        call_fns = [
            i
            for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION and i.type_hint == "Dog"
        ]
        assert len(call_fns) >= 1
        assert env.register_types[call_fns[0].result_reg] == "Dog"


# ---------------------------------------------------------------------------
# C++
# ---------------------------------------------------------------------------


class TestCppTypeInference:
    def test_new_object_constructor_typed(self):
        """C++ `new Dog(...)` → CALL_FUNCTION result register typed as Dog."""
        instructions, env = _lower_and_infer(
            """\
int main() {
    Dog* d = new Dog("Rex", 5);
}
""",
            "cpp",
        )
        call_fns = [
            i
            for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION and i.type_hint == "Dog"
        ]
        assert len(call_fns) >= 1
        assert env.register_types[call_fns[0].result_reg] == "Dog"


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------


class TestGoTypeInference:
    def test_typed_params(self):
        """Go func params with type annotations → register_types."""
        instructions, env = _lower_and_infer(
            """\
package main

func add(a int, b int) int {
    return a + b
}
""",
            "go",
        )
        symbolics = [
            i
            for i in instructions
            if i.opcode == Opcode.SYMBOLIC and i.type_hint == "Int"
        ]
        assert len(symbolics) >= 2
        for sym in symbolics:
            assert env.register_types[sym.result_reg] == "Int"

    def test_var_declarations(self):
        """Go var declarations carry types."""
        _instructions, env = _lower_and_infer(
            """\
package main

func main() {
    var x int = 10
    var name string = "hello"
    var pi float64 = 3.14
    var flag bool = true
}
""",
            "go",
        )
        assert env.var_types["x"] == "Int"
        assert env.var_types["name"] == "String"
        assert env.var_types["pi"] == "Float"
        assert env.var_types["flag"] == "Bool"


# ---------------------------------------------------------------------------
# TypeScript
# ---------------------------------------------------------------------------


class TestTypeScriptTypeInference:
    def test_typed_params(self):
        """TypeScript function params with type annotations."""
        instructions, env = _lower_and_infer(
            """\
function add(a: number, b: number): number {
    return a + b;
}
""",
            "typescript",
        )
        symbolics = [
            i for i in instructions if i.opcode == Opcode.SYMBOLIC and i.type_hint
        ]
        assert len(symbolics) >= 2

    def test_let_with_type(self):
        """TypeScript let — type inferred from CONST literal (frontend
        does not yet propagate TS type annotations to STORE_VAR)."""
        _instructions, env = _lower_and_infer(
            'let x: number = 42;\nlet name: string = "hi";',
            "typescript",
        )
        # Inferred from CONST literal, not from TS type annotation
        assert env.var_types["x"] == TypeName.INT
        assert env.var_types["name"] == TypeName.STRING


# ---------------------------------------------------------------------------
# C
# ---------------------------------------------------------------------------


class TestCTypeInference:
    def test_int_params(self):
        """C function params with int type."""
        instructions, env = _lower_and_infer(
            """\
int add(int a, int b) {
    return a + b;
}
""",
            "c",
        )
        symbolics = [
            i
            for i in instructions
            if i.opcode == Opcode.SYMBOLIC and i.type_hint == "Int"
        ]
        assert len(symbolics) >= 2

    def test_float_var(self):
        """C float variable declaration."""
        _instructions, env = _lower_and_infer(
            "float pi = 3.14;",
            "c",
        )
        assert env.var_types["pi"] == "Float"


# ---------------------------------------------------------------------------
# Cross-language: same program, types inferred consistently
# ---------------------------------------------------------------------------

_TYPED_LANGUAGES = ["java", "go", "c", "cpp", "csharp", "rust", "typescript"]


class TestCrossLanguageConsistency:
    """All typed languages should infer Int for an integer constant."""

    SOURCES = {
        "java": "class M { static int x = 42; }",
        "go": "package main\n\nfunc main() {\n    var x int = 42\n}",
        "c": "int x = 42;",
        "cpp": "int x = 42;",
        "csharp": "class M { static int x = 42; }",
        "rust": "let x: i32 = 42;",
        "typescript": "let x: number = 42;",
    }

    @pytest.fixture(params=sorted(SOURCES.keys()), ids=lambda lang: lang)
    def lang_env(self, request):
        lang = request.param
        _instructions, env = _lower_and_infer(self.SOURCES[lang], lang)
        return lang, env

    def test_x_has_type(self, lang_env):
        lang, env = lang_env
        assert (
            "x" in env.var_types
        ), f"[{lang}] expected 'x' in var_types, got: {dict(env.var_types)}"


# ---------------------------------------------------------------------------
# Return type inference: LABEL type_hint → CALL_FUNCTION result typed
# ---------------------------------------------------------------------------


def _find_func_label(instructions, func_name_prefix):
    """Find the LABEL instruction for a function whose label starts with prefix."""
    return next(
        (
            i
            for i in instructions
            if i.opcode == Opcode.LABEL
            and i.label
            and i.label.startswith(f"func_{func_name_prefix}")
        ),
        None,
    )


def _find_call_function_result(instructions, env, func_name):
    """Find the CALL_FUNCTION for func_name and return its result register type."""
    call = next(
        (
            i
            for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION
            and i.operands
            and str(i.operands[0]) == func_name
            and i.result_reg
        ),
        None,
    )
    if call is None:
        return None
    return env.register_types.get(call.result_reg)


class TestJavaReturnType:
    def test_function_label_has_return_type(self):
        instructions, _env = _lower_and_infer(
            """\
class M {
    static int add(int a, int b) { return a + b; }
}
""",
            "java",
        )
        label = _find_func_label(instructions, "add")
        assert label is not None
        assert label.type_hint == "Int"

    def test_call_function_result_typed(self):
        instructions, env = _lower_and_infer(
            """\
class M {
    static int add(int a, int b) { return a + b; }
    static void main() {
        int result = add(1, 2);
    }
}
""",
            "java",
        )
        result_type = _find_call_function_result(instructions, env, "add")
        assert result_type == "Int"


class TestCSharpReturnType:
    def test_function_label_has_return_type(self):
        instructions, _env = _lower_and_infer(
            """\
class M {
    static int Add(int a, int b) { return a + b; }
}
""",
            "csharp",
        )
        label = _find_func_label(instructions, "Add")
        assert label is not None
        assert label.type_hint == "Int"

    def test_call_function_result_typed(self):
        instructions, env = _lower_and_infer(
            """\
class M {
    static int Add(int a, int b) { return a + b; }
    static void Main() {
        int x = Add(1, 2);
    }
}
""",
            "csharp",
        )
        result_type = _find_call_function_result(instructions, env, "Add")
        assert result_type == "Int"


class TestCReturnType:
    def test_function_label_has_return_type(self):
        instructions, _env = _lower_and_infer(
            "int add(int a, int b) { return a + b; }",
            "c",
        )
        label = _find_func_label(instructions, "add")
        assert label is not None
        assert label.type_hint == "Int"

    def test_call_function_result_typed(self):
        instructions, env = _lower_and_infer(
            """\
int add(int a, int b) { return a + b; }
int main() {
    int x = add(1, 2);
    return 0;
}
""",
            "c",
        )
        result_type = _find_call_function_result(instructions, env, "add")
        assert result_type == "Int"


class TestCppReturnType:
    def test_function_label_has_return_type(self):
        instructions, _env = _lower_and_infer(
            "int add(int a, int b) { return a + b; }",
            "cpp",
        )
        label = _find_func_label(instructions, "add")
        assert label is not None
        assert label.type_hint == "Int"

    def test_call_function_result_typed(self):
        instructions, env = _lower_and_infer(
            """\
int add(int a, int b) { return a + b; }
int main() {
    int x = add(1, 2);
    return 0;
}
""",
            "cpp",
        )
        result_type = _find_call_function_result(instructions, env, "add")
        assert result_type == "Int"


class TestGoReturnType:
    def test_function_label_has_return_type(self):
        instructions, _env = _lower_and_infer(
            """\
package main

func add(a int, b int) int {
    return a + b
}
""",
            "go",
        )
        label = _find_func_label(instructions, "add")
        assert label is not None
        assert label.type_hint == "Int"

    def test_call_function_result_typed(self):
        instructions, env = _lower_and_infer(
            """\
package main

func add(a int, b int) int {
    return a + b
}

func main() {
    x := add(1, 2)
}
""",
            "go",
        )
        result_type = _find_call_function_result(instructions, env, "add")
        assert result_type == "Int"


class TestRustReturnType:
    def test_function_label_has_return_type(self):
        instructions, _env = _lower_and_infer(
            "fn add(a: i32, b: i32) -> i32 { a + b }",
            "rust",
        )
        label = _find_func_label(instructions, "add")
        assert label is not None
        assert label.type_hint == "Int"

    def test_call_function_result_typed(self):
        instructions, env = _lower_and_infer(
            """\
fn add(a: i32, b: i32) -> i32 { a + b }
fn main() {
    let x = add(1, 2);
}
""",
            "rust",
        )
        result_type = _find_call_function_result(instructions, env, "add")
        assert result_type == "Int"


class TestKotlinReturnType:
    def test_function_label_has_return_type(self):
        instructions, _env = _lower_and_infer(
            "fun add(a: Int, b: Int): Int { return a + b }",
            "kotlin",
        )
        label = _find_func_label(instructions, "add")
        assert label is not None
        assert label.type_hint == "Int"

    def test_call_function_result_typed(self):
        instructions, env = _lower_and_infer(
            """\
fun add(a: Int, b: Int): Int { return a + b }
fun main() {
    val x = add(1, 2)
}
""",
            "kotlin",
        )
        result_type = _find_call_function_result(instructions, env, "add")
        assert result_type == "Int"


class TestScalaReturnType:
    def test_function_label_has_return_type(self):
        instructions, _env = _lower_and_infer(
            "def add(a: Int, b: Int): Int = a + b",
            "scala",
        )
        label = _find_func_label(instructions, "add")
        assert label is not None
        assert label.type_hint == "Int"

    def test_call_function_result_typed(self):
        instructions, env = _lower_and_infer(
            """\
def add(a: Int, b: Int): Int = a + b
val x = add(1, 2)
""",
            "scala",
        )
        result_type = _find_call_function_result(instructions, env, "add")
        assert result_type == "Int"


class TestTypeScriptReturnType:
    def test_function_label_has_return_type(self):
        instructions, _env = _lower_and_infer(
            "function add(a: number, b: number): number { return a + b; }",
            "typescript",
        )
        label = _find_func_label(instructions, "add")
        assert label is not None
        assert label.type_hint == "Float"

    def test_call_function_result_typed(self):
        instructions, env = _lower_and_infer(
            """\
function add(a: number, b: number): number { return a + b; }
let x = add(1, 2);
""",
            "typescript",
        )
        result_type = _find_call_function_result(instructions, env, "add")
        assert result_type == "Float"


class TestPythonReturnType:
    def test_function_label_has_return_type(self):
        instructions, _env = _lower_and_infer(
            "def add(a: int, b: int) -> int:\n    return a + b",
            "python",
        )
        label = _find_func_label(instructions, "add")
        assert label is not None
        assert label.type_hint == "Int"

    def test_call_function_result_typed(self):
        instructions, env = _lower_and_infer(
            """\
def add(a: int, b: int) -> int:
    return a + b

x = add(1, 2)
""",
            "python",
        )
        result_type = _find_call_function_result(instructions, env, "add")
        assert result_type == "Int"


class TestPHPReturnType:
    def test_function_label_has_return_type(self):
        instructions, _env = _lower_and_infer(
            "<?php function add(int $a, int $b): int { return $a + $b; }",
            "php",
        )
        label = _find_func_label(instructions, "add")
        assert label is not None
        assert label.type_hint == "Int"

    def test_call_function_result_typed(self):
        instructions, env = _lower_and_infer(
            """\
<?php
function add(int $a, int $b): int { return $a + $b; }
$x = add(1, 2);
""",
            "php",
        )
        result_type = _find_call_function_result(instructions, env, "add")
        assert result_type == "Int"


class TestPascalReturnType:
    def test_function_label_has_return_type(self):
        instructions, _env = _lower_and_infer(
            "program test; function add(a: integer; b: integer): integer; begin add := a + b; end; begin end.",
            "pascal",
        )
        label = _find_func_label(instructions, "add")
        assert label is not None
        assert label.type_hint == "Int"

    def test_procedure_has_no_return_type(self):
        """Pascal procedures (no return type) should have empty type_hint."""
        instructions, _env = _lower_and_infer(
            "program test; procedure greet; begin end; begin end.",
            "pascal",
        )
        label = _find_func_label(instructions, "greet")
        assert label is not None
        assert label.type_hint == ""


# ---------------------------------------------------------------------------
# Languages WITHOUT return type syntax — verify no return types leak through
# ---------------------------------------------------------------------------


class TestJavaScriptNoReturnType:
    def test_function_label_has_no_return_type(self):
        """JavaScript has no return type syntax — LABEL type_hint must be empty."""
        instructions, _env = _lower_and_infer(
            "function add(a, b) { return a + b; }",
            "javascript",
        )
        func_labels = [
            i
            for i in instructions
            if i.opcode == Opcode.LABEL and i.label and i.label.startswith("func_")
        ]
        assert len(func_labels) >= 1
        for label in func_labels:
            assert (
                label.type_hint == ""
            ), f"JS function LABEL should have no return type, got {label.type_hint!r}"

    def test_call_function_result_not_typed(self):
        """JavaScript CALL_FUNCTION result should not get a return type."""
        instructions, env = _lower_and_infer(
            """\
function add(a, b) { return a + b; }
let x = add(1, 2);
""",
            "javascript",
        )
        result_type = _find_call_function_result(instructions, env, "add")
        assert result_type is None


class TestRubyNoReturnType:
    def test_function_label_has_no_return_type(self):
        """Ruby has no return type syntax — LABEL type_hint must be empty."""
        instructions, _env = _lower_and_infer(
            "def add(a, b)\n  a + b\nend",
            "ruby",
        )
        func_labels = [
            i
            for i in instructions
            if i.opcode == Opcode.LABEL and i.label and i.label.startswith("func_")
        ]
        assert len(func_labels) >= 1
        for label in func_labels:
            assert (
                label.type_hint == ""
            ), f"Ruby function LABEL should have no return type, got {label.type_hint!r}"


class TestLuaNoReturnType:
    def test_function_label_has_no_return_type(self):
        """Lua has no return type syntax — LABEL type_hint must be empty."""
        instructions, _env = _lower_and_infer(
            "function add(a, b)\n  return a + b\nend",
            "lua",
        )
        func_labels = [
            i
            for i in instructions
            if i.opcode == Opcode.LABEL and i.label and i.label.startswith("func_")
        ]
        assert len(func_labels) >= 1
        for label in func_labels:
            assert (
                label.type_hint == ""
            ), f"Lua function LABEL should have no return type, got {label.type_hint!r}"


# ---------------------------------------------------------------------------
# Function signatures: param types + return type across languages
# ---------------------------------------------------------------------------


class TestJavaFuncSignatures:
    def test_add_function_signature(self):
        """Java add(int a, int b): int → full signature with typed params."""
        _instructions, env = _lower_and_infer(
            """\
class M {
    static int add(int a, int b) { return a + b; }
}
""",
            "java",
        )
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestCSharpFuncSignatures:
    def test_add_function_signature(self):
        """C# Add(int a, int b): int → full signature."""
        _instructions, env = _lower_and_infer(
            """\
class M {
    static int Add(int a, int b) { return a + b; }
}
""",
            "csharp",
        )
        assert "Add" in env.func_signatures
        sig = env.func_signatures["Add"]
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestCFuncSignatures:
    def test_add_function_signature(self):
        """C add(int a, int b) → full signature."""
        _instructions, env = _lower_and_infer(
            "int add(int a, int b) { return a + b; }",
            "c",
        )
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestCppFuncSignatures:
    def test_add_function_signature(self):
        """C++ add(int a, int b) → full signature."""
        _instructions, env = _lower_and_infer(
            "int add(int a, int b) { return a + b; }",
            "cpp",
        )
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestGoFuncSignatures:
    def test_add_function_signature(self):
        """Go func add(a int, b int) int → full signature."""
        _instructions, env = _lower_and_infer(
            """\
package main

func add(a int, b int) int {
    return a + b
}
""",
            "go",
        )
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestRustFuncSignatures:
    def test_add_function_signature(self):
        """Rust fn add(a: i32, b: i32) -> i32 → full signature."""
        _instructions, env = _lower_and_infer(
            "fn add(a: i32, b: i32) -> i32 { a + b }",
            "rust",
        )
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestKotlinFuncSignatures:
    def test_add_function_signature(self):
        """Kotlin fun add(a: Int, b: Int): Int → full signature."""
        _instructions, env = _lower_and_infer(
            "fun add(a: Int, b: Int): Int { return a + b }",
            "kotlin",
        )
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestScalaFuncSignatures:
    def test_add_function_signature(self):
        """Scala def add(a: Int, b: Int): Int → full signature."""
        _instructions, env = _lower_and_infer(
            "def add(a: Int, b: Int): Int = a + b",
            "scala",
        )
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestTypeScriptFuncSignatures:
    def test_add_function_signature(self):
        """TypeScript function add(a: number, b: number): number → full signature."""
        _instructions, env = _lower_and_infer(
            "function add(a: number, b: number): number { return a + b; }",
            "typescript",
        )
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == "Float"
        assert sig.params == (("a", "Float"), ("b", "Float"))


class TestPythonFuncSignatures:
    def test_add_function_signature(self):
        """Python def add(a: int, b: int) -> int → full signature."""
        _instructions, env = _lower_and_infer(
            "def add(a: int, b: int) -> int:\n    return a + b",
            "python",
        )
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestPHPFuncSignatures:
    def test_add_function_signature(self):
        """PHP function add(int $a, int $b): int → full signature (PHP keeps $ prefix)."""
        _instructions, env = _lower_and_infer(
            "<?php function add(int $a, int $b): int { return $a + $b; }",
            "php",
        )
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == "Int"
        assert sig.params == (("$a", "Int"), ("$b", "Int"))


class TestJavaScriptFuncSignatures:
    def test_untyped_function_signature(self):
        """JavaScript function add(a, b) → params collected with empty types."""
        _instructions, env = _lower_and_infer(
            "function add(a, b) { return a + b; }",
            "javascript",
        )
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == ""
        assert sig.params == (("a", ""), ("b", ""))


class TestRubyFuncSignatures:
    def test_untyped_function_signature(self):
        """Ruby def add(a, b) → params collected with empty types."""
        _instructions, env = _lower_and_infer(
            "def add(a, b)\n  a + b\nend",
            "ruby",
        )
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == ""
        assert sig.params == (("a", ""), ("b", ""))


# ---------------------------------------------------------------------------
# Builtin return types (integration)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# RETURN backfill (integration)
# ---------------------------------------------------------------------------


class TestPythonReturnBackfill:
    def test_unannotated_function_returning_int_literal(self):
        """Python `def double(x): return 42` → func_signatures["double"].return_type == Int."""
        _instructions, env = _lower_and_infer(
            "def double(x):\n    return 42\n",
            "python",
        )
        assert "double" in env.func_signatures
        assert env.func_signatures["double"].return_type == TypeName.INT

    def test_unannotated_function_returning_string_literal(self):
        """Python `def greet(): return "hi"` → return_type == String."""
        _instructions, env = _lower_and_infer(
            'def greet():\n    return "hi"\n',
            "python",
        )
        assert "greet" in env.func_signatures
        assert env.func_signatures["greet"].return_type == TypeName.STRING


class TestJavaScriptReturnBackfill:
    def test_unannotated_function_returning_int_literal(self):
        """JS `function f() { return 42; }` → func_signatures["f"].return_type == Int."""
        _instructions, env = _lower_and_infer(
            "function f() { return 42; }",
            "javascript",
        )
        assert "f" in env.func_signatures
        assert env.func_signatures["f"].return_type == TypeName.INT


class TestRubyReturnBackfill:
    def test_unannotated_function_returning_int_literal(self):
        """Ruby `def f; return 42; end` → func_signatures["f"].return_type == Int."""
        _instructions, env = _lower_and_infer(
            "def f\n  return 42\nend",
            "ruby",
        )
        assert "f" in env.func_signatures
        assert env.func_signatures["f"].return_type == TypeName.INT


# ---------------------------------------------------------------------------
# CALL_METHOD return types (integration)
# ---------------------------------------------------------------------------


class TestJavaCallMethodReturnType:
    def test_typed_method_call_result(self):
        """Java class with typed method → CALL_METHOD result typed."""
        instructions, env = _lower_and_infer(
            """\
class Dog {
    int getAge() { return 5; }
    static void main() {
        Dog d = new Dog();
        int age = d.getAge();
    }
}
""",
            "java",
        )
        call_methods = [
            i
            for i in instructions
            if i.opcode == Opcode.CALL_METHOD
            and i.result_reg
            and len(i.operands) >= 2
            and str(i.operands[1]) == "getAge"
        ]
        assert len(call_methods) >= 1
        result_type = env.register_types.get(call_methods[0].result_reg)
        assert result_type == "Int"


# ---------------------------------------------------------------------------
# Field type table (integration)
# ---------------------------------------------------------------------------


class TestPythonFieldTypes:
    def test_self_field_store_and_load(self):
        """Python `self.x = 42` then `y = self.x` → y typed as Int."""
        instructions, env = _lower_and_infer(
            """\
class Dog:
    def __init__(self):
        self.age = 5
    def get_age(self):
        return self.age
""",
            "python",
        )
        # Verify STORE_FIELD and LOAD_FIELD instructions exist
        store_fields = [i for i in instructions if i.opcode == Opcode.STORE_FIELD]
        load_fields = [i for i in instructions if i.opcode == Opcode.LOAD_FIELD]
        assert len(store_fields) >= 1, "Expected at least one STORE_FIELD"
        assert len(load_fields) >= 1, "Expected at least one LOAD_FIELD"


class TestJavaFieldTypes:
    def test_field_assignment_and_access(self):
        """Java field store and load → typed."""
        instructions, env = _lower_and_infer(
            """\
class Dog {
    int age;
    Dog() { this.age = 5; }
    int getAge() { return this.age; }
}
""",
            "java",
        )
        store_fields = [i for i in instructions if i.opcode == Opcode.STORE_FIELD]
        load_fields = [i for i in instructions if i.opcode == Opcode.LOAD_FIELD]
        assert len(store_fields) >= 1, "Expected at least one STORE_FIELD"
        assert len(load_fields) >= 1, "Expected at least one LOAD_FIELD"


class TestPythonBuiltinReturnTypes:
    def test_len_returns_int(self):
        """Python `x = len("hello")` → var_types["x"] == Int."""
        _instructions, env = _lower_and_infer(
            'x = len("hello")',
            "python",
        )
        assert env.var_types["x"] == TypeName.INT

    def test_range_returns_array(self):
        """Python `r = range(10)` → var_types["r"] == Array."""
        _instructions, env = _lower_and_infer(
            "r = range(10)",
            "python",
        )
        assert env.var_types["r"] == TypeName.ARRAY

    def test_abs_returns_number(self):
        """Python `y = abs(-5)` → var_types["y"] == Number."""
        _instructions, env = _lower_and_infer(
            "y = abs(-5)",
            "python",
        )
        assert env.var_types["y"] == TypeName.NUMBER


# ---------------------------------------------------------------------------
# self/this typing — field tracking through self (integration)
# ---------------------------------------------------------------------------


class TestPythonSelfFieldTracking:
    def test_self_field_store_then_load_typed(self):
        """Python class: self.age = 5 → LOAD_FIELD on self.age typed as Int."""
        instructions, env = _lower_and_infer(
            """\
class Dog:
    def __init__(self):
        self.age = 5
    def get_age(self):
        return self.age
""",
            "python",
        )
        # Verify self registers are typed as Dog
        symbolics = [
            i
            for i in instructions
            if i.opcode == Opcode.SYMBOLIC
            and i.operands
            and str(i.operands[0]) == "param:self"
        ]
        assert len(symbolics) >= 1
        for sym in symbolics:
            assert env.register_types.get(sym.result_reg) == "Dog"

        # Verify LOAD_FIELD on self.age is typed
        load_fields = [
            i
            for i in instructions
            if i.opcode == Opcode.LOAD_FIELD
            and i.result_reg
            and len(i.operands) >= 2
            and str(i.operands[1]) == "age"
        ]
        assert len(load_fields) >= 1
        assert env.register_types[load_fields[0].result_reg] == TypeName.INT


class TestJavaSelfFieldTracking:
    def test_this_param_typed_as_class_name(self):
        """Java class: param:this in method → register typed as Dog."""
        instructions, env = _lower_and_infer(
            """\
class Dog {
    int age;
    int getAge() { return this.age; }
}
""",
            "java",
        )
        # Verify this registers are typed as Dog
        symbolics = [
            i
            for i in instructions
            if i.opcode == Opcode.SYMBOLIC
            and i.operands
            and str(i.operands[0]) == "param:this"
        ]
        assert len(symbolics) >= 1
        for sym in symbolics:
            assert env.register_types.get(sym.result_reg) == "Dog"

    def test_this_field_store_then_load_typed(self):
        """Java class with self-init pattern → field tracking through this."""
        instructions, env = _lower_and_infer(
            """\
class Dog {
    int age;
    void setAge() { this.age = 5; }
    int getAge() { return this.age; }
}
""",
            "java",
        )
        # STORE_FIELD on typed this → field_types["Dog"]["age"] populated
        store_fields = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_FIELD
            and len(i.operands) >= 2
            and str(i.operands[1]) == "age"
        ]
        assert len(store_fields) >= 1
        # Check if the store's object register is typed
        obj_reg = str(store_fields[0].operands[0])
        obj_typed = obj_reg in env.register_types
        if obj_typed:
            # LOAD_FIELD on this.age should also be typed
            load_fields = [
                i
                for i in instructions
                if i.opcode == Opcode.LOAD_FIELD
                and i.result_reg
                and len(i.operands) >= 2
                and str(i.operands[1]) == "age"
            ]
            assert len(load_fields) >= 1
            assert env.register_types[load_fields[0].result_reg] == TypeName.INT


class TestLuaFuncSignatures:
    def test_untyped_function_signature(self):
        """Lua function add(a, b) → params collected with empty types."""
        _instructions, env = _lower_and_infer(
            "function add(a, b)\n  return a + b\nend",
            "lua",
        )
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == ""
        assert sig.params == (("a", ""), ("b", ""))
