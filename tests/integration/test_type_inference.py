"""Integration tests: source → frontend → IR → type inference pass."""

import pytest

from interpreter.constants import Language, TypeName
from interpreter.types.coercion.default_conversion_rules import (
    DefaultTypeConversionRules,
)
from interpreter.frontend import get_frontend
from interpreter.ir import Opcode
from interpreter.types.type_expr import (
    FunctionType,
    ParameterizedType,
    UNBOUND,
    scalar,
    fn_type,
    tuple_of,
)
from interpreter.types.type_inference import infer_types
from interpreter.types.type_resolver import TypeResolver


def _resolver():
    return TypeResolver(DefaultTypeConversionRules())


def _lower_and_infer(source: str, language: str):
    lang = Language(language)
    frontend = get_frontend(lang)
    instructions = frontend.lower(source.encode("utf-8"))
    env = infer_types(
        instructions,
        _resolver(),
        type_env_builder=frontend.type_env_builder,
        func_symbol_table=frontend.func_symbol_table,
    )
    return instructions, env


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
        assert len(binops) == 1
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
            if i.opcode == Opcode.SYMBOLIC
            and i.result_reg
            and env.register_types.get(i.result_reg) == "Int"
        ]
        assert len(symbolics) == 2

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
            if i.opcode == Opcode.CALL_FUNCTION
            and i.result_reg
            and env.register_types.get(i.result_reg) == "Dog"
        ]
        assert len(call_fns) == 1

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
            if i.opcode == Opcode.CALL_FUNCTION
            and i.result_reg
            and env.register_types.get(i.result_reg) == "Dog"
        ]
        assert len(call_fns) >= 1


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
            if i.opcode == Opcode.CALL_FUNCTION
            and i.result_reg
            and env.register_types.get(i.result_reg) == "Dog"
        ]
        assert len(call_fns) >= 1


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
            if i.opcode == Opcode.SYMBOLIC
            and i.result_reg
            and env.register_types.get(i.result_reg) == "Int"
        ]
        assert len(symbolics) >= 2

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
            i
            for i in instructions
            if i.opcode == Opcode.SYMBOLIC
            and i.result_reg
            and env.register_types.get(i.result_reg) == "Float"
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
            if i.opcode == Opcode.SYMBOLIC
            and i.result_reg
            and env.register_types.get(i.result_reg) == "Int"
        ]
        assert len(symbolics) >= 2

    def test_float_var(self):
        """C float variable declaration."""
        _instructions, env = _lower_and_infer(
            "float pi = 3.14;",
            "c",
        )
        assert env.var_types["pi"] == "Float"

    def test_pointer_variable_typed_as_pointer_int(self):
        """C int *ptr should infer var type Pointer[Int]."""
        _instructions, env = _lower_and_infer(
            "void f() { int *ptr; }",
            "c",
        )
        assert env.var_types["ptr"] == "Pointer[Int]"

    def test_double_pointer(self):
        """C int **pp should infer Pointer[Pointer[Int]]."""
        _instructions, env = _lower_and_infer(
            "void f() { int **pp; }",
            "c",
        )
        assert env.var_types["pp"] == "Pointer[Pointer[Int]]"

    def test_pointer_parameter_type(self):
        """C function with int *arr param should have Pointer[Int] in signature."""
        _instructions, env = _lower_and_infer(
            "void f(int *arr) { }",
            "c",
        )
        assert "f" in env.method_signatures.get(UNBOUND, {})
        param_types = dict(env.get_func_signature("f").params)
        assert param_types["arr"] == "Pointer[Int]"

    def test_pointer_return_type_propagated(self):
        """Pointer variable typed as Pointer[Int] should propagate through LOAD_VAR."""
        instructions, env = _lower_and_infer(
            """\
void f() {
    int *p;
    int *q = p;
}
""",
            "c",
        )
        assert env.var_types["p"] == "Pointer[Int]"
        assert env.var_types["q"] == "Pointer[Int]"


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

    def test_x_typed_as_int(self, lang_env):
        lang, env = lang_env
        assert (
            "x" in env.var_types
        ), f"[{lang}] expected 'x' in var_types, got: {dict(env.var_types)}"
        assert (
            env.var_types["x"] == TypeName.INT
        ), f"[{lang}] expected x typed as Int, got {env.var_types['x']!r}"


# ---------------------------------------------------------------------------
# Return type inference: func_signatures → CALL_FUNCTION result typed
# ---------------------------------------------------------------------------


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
        _instructions, env = _lower_and_infer(
            """\
class M {
    static int add(int a, int b) { return a + b; }
}
""",
            "java",
        )
        sig = env.get_func_signature("add", class_name=scalar("M"))
        assert sig.return_type == "Int"

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
        _instructions, env = _lower_and_infer(
            """\
class M {
    static int Add(int a, int b) { return a + b; }
}
""",
            "csharp",
        )
        sig = env.get_func_signature("Add", class_name=scalar("M"))
        assert sig.return_type == "Int"

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
        _instructions, env = _lower_and_infer(
            "int add(int a, int b) { return a + b; }",
            "c",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("add").return_type == "Int"

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
        _instructions, env = _lower_and_infer(
            "int add(int a, int b) { return a + b; }",
            "cpp",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("add").return_type == "Int"

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
        _instructions, env = _lower_and_infer(
            """\
package main

func add(a int, b int) int {
    return a + b
}
""",
            "go",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("add").return_type == "Int"

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
        _instructions, env = _lower_and_infer(
            "fn add(a: i32, b: i32) -> i32 { a + b }",
            "rust",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("add").return_type == "Int"

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
        _instructions, env = _lower_and_infer(
            "fun add(a: Int, b: Int): Int { return a + b }",
            "kotlin",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("add").return_type == "Int"

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
        _instructions, env = _lower_and_infer(
            "def add(a: Int, b: Int): Int = a + b",
            "scala",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("add").return_type == "Int"

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
        _instructions, env = _lower_and_infer(
            "function add(a: number, b: number): number { return a + b; }",
            "typescript",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("add").return_type == "Float"

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
        _instructions, env = _lower_and_infer(
            "def add(a: int, b: int) -> int:\n    return a + b",
            "python",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("add").return_type == "Int"

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
        _instructions, env = _lower_and_infer(
            "<?php function add(int $a, int $b): int { return $a + $b; }",
            "php",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("add").return_type == "Int"

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
        _instructions, env = _lower_and_infer(
            "program test; function add(a: integer; b: integer): integer; begin add := a + b; end; begin end.",
            "pascal",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("add").return_type == "Int"

    def test_procedure_has_no_return_type(self):
        """Pascal procedures (no return type) should have empty return_type."""
        _instructions, env = _lower_and_infer(
            "program test; procedure greet; begin end; begin end.",
            "pascal",
        )
        assert "greet" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("greet").return_type == ""


# ---------------------------------------------------------------------------
# Languages WITHOUT return type syntax — verify no return types leak through
# ---------------------------------------------------------------------------


class TestJavaScriptNoReturnType:
    def test_function_label_has_no_return_type(self):
        """JavaScript has no return type syntax — func_signatures return_type must be empty."""
        _instructions, env = _lower_and_infer(
            "function add(a, b) { return a + b; }",
            "javascript",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert (
            sig.return_type == ""
        ), f"JS function should have no return type, got {sig.return_type!r}"

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
        """Ruby has no return type syntax — func_signatures return_type must be empty."""
        _instructions, env = _lower_and_infer(
            "def add(a, b)\n  a + b\nend",
            "ruby",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert (
            sig.return_type == ""
        ), f"Ruby function should have no return type, got {sig.return_type!r}"


class TestLuaNoReturnType:
    def test_function_label_has_no_return_type(self):
        """Lua has no return type syntax — func_signatures return_type must be empty."""
        _instructions, env = _lower_and_infer(
            "function add(a, b)\n  return a + b\nend",
            "lua",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert (
            sig.return_type == ""
        ), f"Lua function should have no return type, got {sig.return_type!r}"


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
        sig = env.get_func_signature("add", class_name=scalar("M"))
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
        sig = env.get_func_signature("Add", class_name=scalar("M"))
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestCFuncSignatures:
    def test_add_function_signature(self):
        """C add(int a, int b) → full signature."""
        _instructions, env = _lower_and_infer(
            "int add(int a, int b) { return a + b; }",
            "c",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestCppFuncSignatures:
    def test_add_function_signature(self):
        """C++ add(int a, int b) → full signature."""
        _instructions, env = _lower_and_infer(
            "int add(int a, int b) { return a + b; }",
            "cpp",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
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
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestRustFuncSignatures:
    def test_add_function_signature(self):
        """Rust fn add(a: i32, b: i32) -> i32 → full signature."""
        _instructions, env = _lower_and_infer(
            "fn add(a: i32, b: i32) -> i32 { a + b }",
            "rust",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestKotlinFuncSignatures:
    def test_add_function_signature(self):
        """Kotlin fun add(a: Int, b: Int): Int → full signature."""
        _instructions, env = _lower_and_infer(
            "fun add(a: Int, b: Int): Int { return a + b }",
            "kotlin",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestScalaFuncSignatures:
    def test_add_function_signature(self):
        """Scala def add(a: Int, b: Int): Int → full signature."""
        _instructions, env = _lower_and_infer(
            "def add(a: Int, b: Int): Int = a + b",
            "scala",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestTypeScriptFuncSignatures:
    def test_add_function_signature(self):
        """TypeScript function add(a: number, b: number): number → full signature."""
        _instructions, env = _lower_and_infer(
            "function add(a: number, b: number): number { return a + b; }",
            "typescript",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert sig.return_type == "Float"
        assert sig.params == (("a", "Float"), ("b", "Float"))


class TestPythonFuncSignatures:
    def test_add_function_signature(self):
        """Python def add(a: int, b: int) -> int → full signature."""
        _instructions, env = _lower_and_infer(
            "def add(a: int, b: int) -> int:\n    return a + b",
            "python",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))


class TestPHPFuncSignatures:
    def test_add_function_signature(self):
        """PHP function add(int $a, int $b): int → full signature (PHP keeps $ prefix)."""
        _instructions, env = _lower_and_infer(
            "<?php function add(int $a, int $b): int { return $a + $b; }",
            "php",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert sig.return_type == "Int"
        assert sig.params == (("$a", "Int"), ("$b", "Int"))


class TestJavaScriptFuncSignatures:
    def test_untyped_function_signature(self):
        """JavaScript function add(a, b) → params collected with empty types."""
        _instructions, env = _lower_and_infer(
            "function add(a, b) { return a + b; }",
            "javascript",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert sig.return_type == ""
        assert sig.params == (("a", ""), ("b", ""))


class TestRubyFuncSignatures:
    def test_untyped_function_signature(self):
        """Ruby def add(a, b) → params collected with empty types."""
        _instructions, env = _lower_and_infer(
            "def add(a, b)\n  a + b\nend",
            "ruby",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
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
        assert "double" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("double").return_type == TypeName.INT

    def test_unannotated_function_returning_string_literal(self):
        """Python `def greet(): return "hi"` → return_type == String."""
        _instructions, env = _lower_and_infer(
            'def greet():\n    return "hi"\n',
            "python",
        )
        assert "greet" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("greet").return_type == TypeName.STRING


class TestJavaScriptReturnBackfill:
    def test_unannotated_function_returning_int_literal(self):
        """JS `function f() { return 42; }` → func_signatures["f"].return_type == Int."""
        _instructions, env = _lower_and_infer(
            "function f() { return 42; }",
            "javascript",
        )
        assert "f" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("f").return_type == TypeName.INT


class TestRubyReturnBackfill:
    def test_unannotated_function_returning_int_literal(self):
        """Ruby `def f; return 42; end` → func_signatures["f"].return_type == Int."""
        _instructions, env = _lower_and_infer(
            "def f\n  return 42\nend",
            "ruby",
        )
        assert "f" in env.method_signatures.get(UNBOUND, {})
        assert env.get_func_signature("f").return_type == TypeName.INT


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
        """Python `self.age = 5` then `return self.age` → LOAD_FIELD result typed as Int."""
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
        store_fields = [i for i in instructions if i.opcode == Opcode.STORE_FIELD]
        load_fields = [
            i
            for i in instructions
            if i.opcode == Opcode.LOAD_FIELD
            and i.result_reg
            and len(i.operands) >= 2
            and str(i.operands[1]) == "age"
        ]
        assert len(store_fields) >= 1, "Expected at least one STORE_FIELD"
        assert len(load_fields) >= 1, "Expected at least one LOAD_FIELD for 'age'"
        assert (
            env.register_types[load_fields[0].result_reg] == TypeName.INT
        ), f"Expected LOAD_FIELD result typed as Int, got {env.register_types.get(load_fields[0].result_reg)!r}"


class TestJavaFieldTypes:
    def test_field_assignment_and_access(self):
        """Java field store and load → LOAD_FIELD result typed as Int."""
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
        load_fields = [
            i
            for i in instructions
            if i.opcode == Opcode.LOAD_FIELD
            and i.result_reg
            and len(i.operands) >= 2
            and str(i.operands[1]) == "age"
        ]
        assert len(store_fields) >= 1, "Expected at least one STORE_FIELD"
        assert len(load_fields) >= 1, "Expected at least one LOAD_FIELD for 'age'"
        assert (
            env.register_types[load_fields[0].result_reg] == TypeName.INT
        ), f"Expected LOAD_FIELD result typed as Int, got {env.register_types.get(load_fields[0].result_reg)!r}"


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
        # Verify the store's object register is typed as Dog
        obj_reg = str(store_fields[0].operands[0])
        assert (
            obj_reg in env.register_types
        ), f"Expected STORE_FIELD object register {obj_reg} to be typed"
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


class TestThisParamInFuncSignatures:
    """Verify that this/$this param is seeded with class name in func_signatures."""

    def test_java_this_param_in_func_signature(self):
        _instructions, env = _lower_and_infer(
            """\
class Dog {
    int age;
    int getAge() { return this.age; }
}
""",
            "java",
        )
        sig = env.get_func_signature("getAge", class_name=scalar("Dog"))
        this_params = [p for p in sig.params if p[0] == "this"]
        assert len(this_params) == 1
        assert this_params[0][1] == "Dog"

    def test_cpp_this_param_in_func_signature(self):
        _instructions, env = _lower_and_infer(
            "class Vec3 { double length() { return 0; } };",
            "cpp",
        )
        sig = env.get_func_signature("length", class_name=scalar("Vec3"))
        this_params = [p for p in sig.params if p[0] == "this"]
        assert len(this_params) == 1
        assert this_params[0][1] == "Vec3"

    def test_csharp_this_param_in_func_signature(self):
        _instructions, env = _lower_and_infer(
            "class Cat { int GetLives() { return 9; } }",
            "csharp",
        )
        sig = env.get_func_signature("GetLives", class_name=scalar("Cat"))
        this_params = [p for p in sig.params if p[0] == "this"]
        assert len(this_params) == 1
        assert this_params[0][1] == "Cat"

    def test_javascript_this_param_in_func_signature(self):
        _instructions, env = _lower_and_infer(
            "class Box { getSize() { return 1; } }",
            "javascript",
        )
        sig = env.get_func_signature("getSize", class_name=scalar("Box"))
        this_params = [p for p in sig.params if p[0] == "this"]
        assert len(this_params) == 1
        assert this_params[0][1] == "Box"

    def test_typescript_this_param_in_func_signature(self):
        _instructions, env = _lower_and_infer(
            "class Box { getSize(): number { return 1; } }",
            "typescript",
        )
        sig = env.get_func_signature("getSize", class_name=scalar("Box"))
        this_params = [p for p in sig.params if p[0] == "this"]
        assert len(this_params) == 1
        assert this_params[0][1] == "Box"

    def test_kotlin_this_param_in_func_signature(self):
        _instructions, env = _lower_and_infer(
            "class Circle { fun area(): Double { return 3.14 } }",
            "kotlin",
        )
        sig = env.get_func_signature("area", class_name=scalar("Circle"))
        this_params = [p for p in sig.params if p[0] == "this"]
        assert len(this_params) == 1
        assert this_params[0][1] == "Circle"

    def test_scala_this_param_in_func_signature(self):
        _instructions, env = _lower_and_infer(
            "class Circle { def area(): Double = 3.14 }",
            "scala",
        )
        sig = env.get_func_signature("area", class_name=scalar("Circle"))
        this_params = [p for p in sig.params if p[0] == "this"]
        assert len(this_params) == 1
        assert this_params[0][1] == "Circle"

    def test_php_this_param_in_func_signature(self):
        _instructions, env = _lower_and_infer(
            '<?php class User { function greet(): string { return "hi"; } }',
            "php",
        )
        sig = env.get_func_signature("greet", class_name=scalar("User"))
        this_params = [p for p in sig.params if p[0] == "$this"]
        assert len(this_params) == 1
        assert this_params[0][1] == "User"


class TestLuaFuncSignatures:
    def test_untyped_function_signature(self):
        """Lua function add(a, b) → params collected with empty types."""
        _instructions, env = _lower_and_infer(
            "function add(a, b)\n  return a + b\nend",
            "lua",
        )
        assert "add" in env.method_signatures.get(UNBOUND, {})
        sig = env.get_func_signature("add")
        assert sig.return_type == ""
        assert sig.params == (("a", ""), ("b", ""))


# ---------------------------------------------------------------------------
# Cross-language BINOP: int + int → Int
# ---------------------------------------------------------------------------


class TestBinopIntPlusInt:
    """All 15 languages: `x = 3 + 4` → BINOP result typed as Int."""

    SOURCES = {
        "python": "x = 3 + 4",
        "java": "class M { static int x = 3 + 4; }",
        "typescript": "let x = 3 + 4;",
        "kotlin": "val x = 3 + 4",
        "scala": "val x = 3 + 4",
        "csharp": "class M { static int x = 3 + 4; }",
        "cpp": "int x = 3 + 4;",
        "php": "<?php $x = 3 + 4;",
        "c": "int x = 3 + 4;",
        "go": "package main\n\nfunc main() {\n\tx := 3 + 4\n}",
        "rust": "let x = 3 + 4;",
        "pascal": "program test; var x: integer; begin x := 3 + 4; end.",
        "javascript": "let x = 3 + 4;",
        "ruby": "x = 3 + 4",
        "lua": "local x = 3 + 4",
    }

    @pytest.fixture(params=sorted(SOURCES.keys()), ids=lambda lang: lang)
    def lang_env(self, request):
        lang = request.param
        instructions, env = _lower_and_infer(self.SOURCES[lang], lang)
        return lang, instructions, env

    def test_binop_result_is_int(self, lang_env):
        lang, instructions, env = lang_env
        binops = [i for i in instructions if i.opcode == Opcode.BINOP and i.result_reg]
        assert len(binops) >= 1, f"[{lang}] expected at least one BINOP"
        result_type = env.register_types.get(binops[0].result_reg)
        assert (
            result_type == TypeName.INT
        ), f"[{lang}] expected Int, got {result_type!r}"


# ---------------------------------------------------------------------------
# Cross-language BINOP: int + float → Float
# ---------------------------------------------------------------------------


class TestBinopIntPlusFloat:
    """All 15 languages: `y = 3 + 4.0` → BINOP result typed as Float."""

    SOURCES = {
        "python": "y = 3 + 4.0",
        "java": "class M { static double y = 3 + 4.0; }",
        "typescript": "let y = 3 + 4.0;",
        "kotlin": "val y = 3 + 4.0",
        "scala": "val y = 3 + 4.0",
        "csharp": "class M { static double y = 3 + 4.0; }",
        "cpp": "double y = 3 + 4.0;",
        "php": "<?php $y = 3 + 4.0;",
        "c": "double y = 3 + 4.0;",
        "go": "package main\n\nfunc main() {\n\ty := 3 + 4.0\n}",
        "rust": "let y = 3.0 + 4.0;",
        "pascal": "program test; var y: real; begin y := 3 + 4.0; end.",
        "javascript": "let y = 3 + 4.0;",
        "ruby": "y = 3 + 4.0",
        "lua": "local y = 3 + 4.0",
    }

    @pytest.fixture(params=sorted(SOURCES.keys()), ids=lambda lang: lang)
    def lang_env(self, request):
        lang = request.param
        instructions, env = _lower_and_infer(self.SOURCES[lang], lang)
        return lang, instructions, env

    def test_binop_result_is_float(self, lang_env):
        lang, instructions, env = lang_env
        binops = [i for i in instructions if i.opcode == Opcode.BINOP and i.result_reg]
        assert len(binops) >= 1, f"[{lang}] expected at least one BINOP"
        result_type = env.register_types.get(binops[0].result_reg)
        assert (
            result_type == TypeName.FLOAT
        ), f"[{lang}] expected Float, got {result_type!r}"


# ---------------------------------------------------------------------------
# Cross-language BINOP: comparison → Bool
# ---------------------------------------------------------------------------


class TestBinopComparisonYieldsBool:
    """All 15 languages: `y = 3 > 4` → BINOP result typed as Bool."""

    SOURCES = {
        "python": "y = 3 > 4",
        "java": "class M { static boolean y = 3 > 4; }",
        "typescript": "let y = 3 > 4;",
        "kotlin": "val y = 3 > 4",
        "scala": "val y = 3 > 4",
        "csharp": "class M { static bool y = 3 > 4; }",
        "cpp": "bool y = 3 > 4;",
        "php": "<?php $y = 3 > 4;",
        "c": "int y = 3 > 4;",
        "go": "package main\n\nfunc main() {\n\ty := 3 > 4\n}",
        "rust": "let y = 3 > 4;",
        "pascal": "program test; var y: boolean; begin y := 3 > 4; end.",
        "javascript": "let y = 3 > 4;",
        "ruby": "y = 3 > 4",
        "lua": "local y = 3 > 4",
    }

    @pytest.fixture(params=sorted(SOURCES.keys()), ids=lambda lang: lang)
    def lang_env(self, request):
        lang = request.param
        instructions, env = _lower_and_infer(self.SOURCES[lang], lang)
        return lang, instructions, env

    def test_binop_result_is_bool(self, lang_env):
        lang, instructions, env = lang_env
        binops = [i for i in instructions if i.opcode == Opcode.BINOP and i.result_reg]
        assert len(binops) >= 1, f"[{lang}] expected at least one BINOP"
        result_type = env.register_types.get(binops[0].result_reg)
        assert (
            result_type == TypeName.BOOL
        ), f"[{lang}] expected Bool, got {result_type!r}"


# ---------------------------------------------------------------------------
# Cross-language UNOP: not/! → Bool
# ---------------------------------------------------------------------------


class TestUnopNotBangYieldsBool:
    """14 languages (excluding Pascal): `y = !true` → UNOP result typed as Bool."""

    SOURCES = {
        "python": "y = not True",
        "java": "class M { static boolean y = !true; }",
        "typescript": "let y = !true;",
        "kotlin": "val y = !true",
        "scala": "val y = !true",
        "csharp": "class M { static bool y = !true; }",
        "cpp": "bool y = !true;",
        "php": "<?php $y = !true;",
        "c": "int y = !1;",
        "go": "package main\n\nfunc main() {\n\ty := !true\n}",
        "rust": "let y = !true;",
        "javascript": "let y = !true;",
        "ruby": "y = !true",
        "lua": "local y = not true",
    }

    @pytest.fixture(params=sorted(SOURCES.keys()), ids=lambda lang: lang)
    def lang_env(self, request):
        lang = request.param
        instructions, env = _lower_and_infer(self.SOURCES[lang], lang)
        return lang, instructions, env

    def test_unop_result_is_bool(self, lang_env):
        lang, instructions, env = lang_env
        unops = [i for i in instructions if i.opcode == Opcode.UNOP and i.result_reg]
        assert len(unops) >= 1, f"[{lang}] expected at least one UNOP"
        result_type = env.register_types.get(unops[0].result_reg)
        assert (
            result_type == TypeName.BOOL
        ), f"[{lang}] expected Bool, got {result_type!r}"


# ---------------------------------------------------------------------------
# Lua UNOP: # (length) → Int
# ---------------------------------------------------------------------------


class TestUnopLuaHashYieldsInt:
    """Lua `local n = #t` → UNOP result typed as Int."""

    def test_hash_length_operator_yields_int(self):
        instructions, env = _lower_and_infer(
            "local t = {1, 2, 3}\nlocal n = #t",
            "lua",
        )
        unops = [i for i in instructions if i.opcode == Opcode.UNOP and i.result_reg]
        assert len(unops) >= 1, "expected at least one UNOP for # operator"
        result_type = env.register_types.get(unops[0].result_reg)
        assert result_type == TypeName.INT, f"expected Int, got {result_type!r}"


# ---------------------------------------------------------------------------
# Return backfill: unannotated functions returning literals
# ---------------------------------------------------------------------------


class TestReturnBackfillAllLanguages:
    """Languages where return type can be omitted: backfill from return literal."""

    SOURCES = {
        "lua": "function f()\n  return 42\nend",
        "php": "<?php function f() { return 42; }",
        "typescript": "function f() { return 42; }",
        "kotlin": "fun f() { return 42 }",
        "scala": "object M { def f() = 42 }",
    }

    @pytest.fixture(params=sorted(SOURCES.keys()), ids=lambda lang: lang)
    def lang_env(self, request):
        lang = request.param
        _instructions, env = _lower_and_infer(self.SOURCES[lang], lang)
        return lang, env

    # Scala wraps in object M, so f is class-scoped
    CLASS_NAMES = {"scala": "M"}

    def test_return_type_backfilled_to_int(self, lang_env):
        lang, env = lang_env
        class_name = self.CLASS_NAMES.get(lang)
        if class_name:
            sig = env.get_func_signature("f", class_name=scalar(class_name))
        else:
            assert "f" in env.method_signatures.get(
                UNBOUND, {}
            ), f"[{lang}] expected 'f' in func_signatures"
            sig = env.get_func_signature("f")
        assert (
            sig.return_type == TypeName.INT
        ), f"[{lang}] expected return_type Int, got {sig.return_type!r}"


# ---------------------------------------------------------------------------
# Typed params seeding: SYMBOLIC register types from param annotations
# ---------------------------------------------------------------------------


class TestTypedParamsSeeding:
    """Languages missing SYMBOLIC register type checks for typed params."""

    SOURCES = {
        "python": "def add(a: int, b: int) -> int:\n    return a + b",
        "kotlin": "fun add(a: Int, b: Int): Int { return a + b }",
        "scala": "def add(a: Int, b: Int): Int = a + b",
        "php": "<?php function add(int $a, int $b): int { return $a + $b; }",
        "rust": "fn add(a: i32, b: i32) -> i32 { a + b }",
        "pascal": "program test; function add(a: integer; b: integer): integer; begin add := a + b; end; begin end.",
    }

    @pytest.fixture(params=sorted(SOURCES.keys()), ids=lambda lang: lang)
    def lang_env(self, request):
        lang = request.param
        instructions, env = _lower_and_infer(self.SOURCES[lang], lang)
        return lang, instructions, env

    def test_param_registers_typed_as_int(self, lang_env):
        lang, instructions, env = lang_env
        symbolics = [
            i
            for i in instructions
            if i.opcode == Opcode.SYMBOLIC
            and i.result_reg
            and env.register_types.get(i.result_reg) == "Int"
        ]
        assert (
            len(symbolics) >= 2
        ), f"[{lang}] expected >= 2 Int-typed SYMBOLIC registers, got {len(symbolics)}"


# ---------------------------------------------------------------------------
# Field type tracking: STORE_FIELD + LOAD_FIELD on self/this
# ---------------------------------------------------------------------------


class TestFieldTypeTrackingOOP:
    """OOP languages: this.age = 5 (store) then this.age (load) → LOAD_FIELD typed as Int."""

    SOURCES = {
        "csharp": """\
class Dog {
    int age;
    void SetAge() { this.age = 5; }
    int GetAge() { return this.age; }
}
""",
        "cpp": """\
class Dog {
    int age;
    void setAge() { this->age = 5; }
    int getAge() { return this->age; }
};
""",
        "javascript": """\
class Dog {
    constructor() { this.age = 5; }
    getAge() { return this.age; }
}
""",
        "typescript": """\
class Dog {
    age: number;
    constructor() { this.age = 5; }
    getAge(): number { return this.age; }
}
""",
        "kotlin": """\
class Dog {
    var age: Int = 0
    fun setAge() { this.age = 5 }
    fun getAge(): Int { return this.age }
}
""",
        "scala": """\
class Dog {
    var age: Int = 0
    def setAge(): Unit = { this.age = 5 }
    def getAge(): Int = this.age
}
""",
        "php": """\
<?php class Dog {
    public $age;
    function setAge() { $this->age = 5; }
    function getAge(): int { return $this->age; }
}
""",
        "ruby": """\
class Dog
    def initialize
        @age = 5
    end
    def get_age
        @age
    end
end
""",
    }

    @pytest.fixture(params=sorted(SOURCES.keys()), ids=lambda lang: lang)
    def lang_env(self, request):
        lang = request.param
        instructions, env = _lower_and_infer(self.SOURCES[lang], lang)
        return lang, instructions, env

    def test_store_field_exists(self, lang_env):
        lang, instructions, _env = lang_env
        store_fields = [i for i in instructions if i.opcode == Opcode.STORE_FIELD]
        assert len(store_fields) >= 1, f"[{lang}] expected at least one STORE_FIELD"

    def test_load_field_exists(self, lang_env):
        lang, instructions, _env = lang_env
        load_fields = [i for i in instructions if i.opcode == Opcode.LOAD_FIELD]
        assert len(load_fields) >= 1, f"[{lang}] expected at least one LOAD_FIELD"

    def test_load_field_typed_as_int(self, lang_env):
        lang, instructions, env = lang_env
        load_fields = [
            i
            for i in instructions
            if i.opcode == Opcode.LOAD_FIELD
            and i.result_reg
            and len(i.operands) >= 2
            and str(i.operands[1]) == "age"
        ]
        assert len(load_fields) >= 1, f"[{lang}] expected LOAD_FIELD for 'age'"
        result_type = env.register_types.get(load_fields[0].result_reg)
        assert (
            result_type == TypeName.INT
        ), f"[{lang}] expected LOAD_FIELD result Int, got {result_type!r}"


# ---------------------------------------------------------------------------
# CALL_METHOD return types: typed method → call result typed
# ---------------------------------------------------------------------------


def _find_call_method_result(instructions, env, method_name):
    """Find the CALL_METHOD for method_name and return its result register type."""
    call = next(
        (
            i
            for i in instructions
            if i.opcode == Opcode.CALL_METHOD
            and i.result_reg
            and len(i.operands) >= 2
            and str(i.operands[1]) == method_name
        ),
        None,
    )
    if call is None:
        return None
    return env.register_types.get(call.result_reg)


class TestCallMethodReturnTypesOOP:
    """OOP languages: class with typed method, then d.getAge() → CALL_METHOD result typed."""

    SOURCES = {
        "python": """\
class Dog:
    def get_age(self) -> int:
        return 5

d = Dog()
age = d.get_age()
""",
        "csharp": """\
class Dog {
    int GetAge() { return 5; }
    static void Main() {
        Dog d = new Dog();
        int age = d.GetAge();
    }
}
""",
        "cpp": """\
class Dog {
public:
    int getAge() { return 5; }
};
int main() {
    Dog d;
    int age = d.getAge();
}
""",
        "javascript": """\
class Dog {
    getAge() { return 5; }
}
let d = new Dog();
let age = d.getAge();
""",
        "typescript": """\
class Dog {
    getAge(): number { return 5; }
}
let d = new Dog();
let age = d.getAge();
""",
        "kotlin": """\
class Dog {
    fun getAge(): Int { return 5 }
}
val d = Dog()
val age = d.getAge()
""",
        "scala": """\
class Dog {
    def getAge(): Int = 5
}
val d = new Dog()
val age = d.getAge()
""",
        "php": """\
<?php class Dog {
    function getAge(): int { return 5; }
}
$d = new Dog();
$age = $d->getAge();
""",
        "ruby": """\
class Dog
    def get_age
        5
    end
end
d = Dog.new
age = d.get_age
""",
    }

    METHOD_NAMES = {
        "python": "get_age",
        "csharp": "GetAge",
        "cpp": "getAge",
        "javascript": "getAge",
        "typescript": "getAge",
        "kotlin": "getAge",
        "scala": "getAge",
        "php": "getAge",
        "ruby": "get_age",
    }

    # TypeScript maps `number` → Float (no separate int type)
    EXPECTED_TYPES = {
        "typescript": "Float",
    }

    @pytest.fixture(params=sorted(SOURCES.keys()), ids=lambda lang: lang)
    def lang_env(self, request):
        lang = request.param
        instructions, env = _lower_and_infer(self.SOURCES[lang], lang)
        return lang, instructions, env

    def test_call_method_result_typed(self, lang_env):
        lang, instructions, env = lang_env
        method_name = self.METHOD_NAMES[lang]
        expected = self.EXPECTED_TYPES.get(lang, "Int")
        result_type = _find_call_method_result(instructions, env, method_name)
        assert (
            result_type == expected
        ), f"[{lang}] expected CALL_METHOD({method_name}) result {expected}, got {result_type!r}"


# ---------------------------------------------------------------------------
# NEW_OBJECT typing: new Dog() → register typed as "Dog"
# ---------------------------------------------------------------------------


class TestNewObjectTypingOOP:
    """Languages missing new-object typing: new Dog() → register typed as Dog."""

    SOURCES = {
        "javascript": "class Dog {}\nlet d = new Dog();",
        "typescript": "class Dog {}\nlet d = new Dog();",
        "php": "<?php class Dog {}\n$d = new Dog();",
        "ruby": "class Dog; end\nd = Dog.new",
        "scala": "class Dog\nval d = new Dog()",
    }

    @pytest.fixture(params=sorted(SOURCES.keys()), ids=lambda lang: lang)
    def lang_env(self, request):
        lang = request.param
        instructions, env = _lower_and_infer(self.SOURCES[lang], lang)
        return lang, instructions, env

    def test_new_object_register_typed_as_dog(self, lang_env):
        lang, instructions, env = lang_env
        # Check CALL_FUNCTION or NEW_OBJECT producing Dog-typed result
        dog_typed = [
            i
            for i in instructions
            if i.opcode in (Opcode.CALL_FUNCTION, Opcode.NEW_OBJECT)
            and i.result_reg
            and env.register_types.get(i.result_reg) == "Dog"
        ]
        # For Ruby, Dog.new is CALL_METHOD
        if lang == "ruby":
            dog_typed = [
                i
                for i in instructions
                if i.result_reg and env.register_types.get(i.result_reg) == "Dog"
            ]
        assert (
            len(dog_typed) >= 1
        ), f"[{lang}] expected at least one register typed as 'Dog'"


# ---------------------------------------------------------------------------
# Builtin method return types (ADR-081)
# ---------------------------------------------------------------------------


class TestBuiltinMethodReturnTypesPython:
    def test_upper_returns_string(self):
        _instructions, env = _lower_and_infer("x = 'hello'.upper()", "python")
        assert env.var_types["x"] == TypeName.STRING

    def test_split_returns_array(self):
        _instructions, env = _lower_and_infer("x = 'a,b'.split(',')", "python")
        assert env.var_types["x"] == TypeName.ARRAY

    def test_find_returns_int(self):
        _instructions, env = _lower_and_infer("x = 'hello'.find('l')", "python")
        assert env.var_types["x"] == TypeName.INT

    def test_startswith_returns_bool(self):
        _instructions, env = _lower_and_infer("x = 'hello'.startswith('h')", "python")
        assert env.var_types["x"] == TypeName.BOOL

    def test_keys_returns_array(self):
        _instructions, env = _lower_and_infer("d = {}; x = d.keys()", "python")
        assert env.var_types["x"] == TypeName.ARRAY

    def test_values_returns_array(self):
        _instructions, env = _lower_and_infer("d = {}; x = d.values()", "python")
        assert env.var_types["x"] == TypeName.ARRAY

    def test_replace_returns_string(self):
        _instructions, env = _lower_and_infer("x = 'hello'.replace('l','r')", "python")
        assert env.var_types["x"] == TypeName.STRING

    def test_count_returns_int(self):
        _instructions, env = _lower_and_infer("x = [1,2,1].count(1)", "python")
        assert env.var_types["x"] == TypeName.INT


class TestBuiltinMethodReturnTypesJavaScript:
    def test_toUpperCase_returns_string(self):
        _instructions, env = _lower_and_infer(
            "let x = 'hello'.toUpperCase();", "javascript"
        )
        assert env.var_types["x"] == TypeName.STRING

    def test_split_returns_array(self):
        _instructions, env = _lower_and_infer("let x = 'a,b'.split(',');", "javascript")
        assert env.var_types["x"] == TypeName.ARRAY

    def test_indexOf_returns_int(self):
        _instructions, env = _lower_and_infer(
            "let x = 'hello'.indexOf('l');", "javascript"
        )
        assert env.var_types["x"] == TypeName.INT

    def test_includes_returns_bool(self):
        _instructions, env = _lower_and_infer(
            "let x = 'hello'.includes('l');", "javascript"
        )
        assert env.var_types["x"] == TypeName.BOOL

    def test_trim_returns_string(self):
        _instructions, env = _lower_and_infer("let x = ' hello '.trim();", "javascript")
        assert env.var_types["x"] == TypeName.STRING


class TestBuiltinMethodReturnTypesJava:
    def test_toUpperCase_returns_string(self):
        _instructions, env = _lower_and_infer(
            'class M { static String x = "hello".toUpperCase(); }', "java"
        )
        assert env.var_types["x"] == TypeName.STRING

    def test_indexOf_returns_int(self):
        _instructions, env = _lower_and_infer(
            'class M { static int x = "hello".indexOf("l"); }', "java"
        )
        assert env.var_types["x"] == TypeName.INT

    def test_contains_returns_bool(self):
        _instructions, env = _lower_and_infer(
            'class M { static boolean x = "hello".contains("l"); }', "java"
        )
        assert env.var_types["x"] == TypeName.BOOL


class TestBuiltinMethodReturnTypesRuby:
    def test_upcase_returns_string(self):
        _instructions, env = _lower_and_infer("x = 'hello'.upcase", "ruby")
        assert env.var_types["x"] == TypeName.STRING

    def test_downcase_returns_string(self):
        _instructions, env = _lower_and_infer("x = 'hello'.downcase", "ruby")
        assert env.var_types["x"] == TypeName.STRING

    def test_split_returns_array(self):
        _instructions, env = _lower_and_infer("x = 'a,b'.split(',')", "ruby")
        assert env.var_types["x"] == TypeName.ARRAY

    def test_gsub_returns_string(self):
        _instructions, env = _lower_and_infer("x = 'hello'.gsub('l','r')", "ruby")
        assert env.var_types["x"] == TypeName.STRING


class TestBuiltinMethodReturnTypesKotlin:
    def test_toUpperCase_returns_string(self):
        _instructions, env = _lower_and_infer(
            'fun main() { val x = "hello".toUpperCase() }', "kotlin"
        )
        assert env.var_types["x"] == TypeName.STRING

    def test_indexOf_returns_int(self):
        _instructions, env = _lower_and_infer(
            'fun main() { val x = "hello".indexOf("l") }', "kotlin"
        )
        assert env.var_types["x"] == TypeName.INT

    def test_contains_returns_bool(self):
        _instructions, env = _lower_and_infer(
            'fun main() { val x = "hello".contains("l") }', "kotlin"
        )
        assert env.var_types["x"] == TypeName.BOOL


# ---------------------------------------------------------------------------
# Forward reference resolution (fixpoint) — ADR-082
# ---------------------------------------------------------------------------


class TestForwardReferencePython:
    def test_call_before_def_resolves_return_type(self):
        """Python: main() calls helper() defined later → return type resolves."""
        source = """\
def main():
    return helper()

def helper():
    return 42
"""
        _instructions, env = _lower_and_infer(source, "python")
        assert env.get_func_signature("helper").return_type == TypeName.INT
        assert env.get_func_signature("main").return_type == TypeName.INT

    def test_forward_ref_var_assignment(self):
        """Python: x = helper() where helper is defined later → x typed."""
        source = """\
def compute():
    x = make_value()
    return x

def make_value():
    return 3.14
"""
        _instructions, env = _lower_and_infer(source, "python")
        assert env.get_func_signature("make_value").return_type == TypeName.FLOAT


class TestForwardReferenceJavaScript:
    def test_call_before_def_resolves_return_type(self):
        """JavaScript: main() calls helper() defined later → return type resolves."""
        source = """\
function main() {
    return helper();
}

function helper() {
    return 42;
}
"""
        _instructions, env = _lower_and_infer(source, "javascript")
        assert env.get_func_signature("helper").return_type == TypeName.INT
        assert env.get_func_signature("main").return_type == TypeName.INT


class TestForwardReferenceRuby:
    def test_call_before_def_resolves_return_type(self):
        """Ruby: main() calls helper() defined later → return type resolves."""
        source = """\
def main()
    return helper()
end

def helper()
    return 42
end
"""
        _instructions, env = _lower_and_infer(source, "ruby")
        assert env.get_func_signature("helper").return_type == TypeName.INT
        assert env.get_func_signature("main").return_type == TypeName.INT


# ---------------------------------------------------------------------------
# Variable type scoping — same var name, different types in different functions
# ---------------------------------------------------------------------------

_SCOPING_SOURCES: dict[str, str] = {
    "python": """\
def make_int():
    x = 42
    return x

def make_str():
    x = "hello"
    return x
""",
    "javascript": """\
function make_int() {
    let x = 42;
    return x;
}

function make_str() {
    let x = "hello";
    return x;
}
""",
    "java": """\
class Main {
    static int make_int() {
        int x = 42;
        return x;
    }

    static String make_str() {
        String x = "hello";
        return x;
    }
}
""",
    "typescript": """\
function make_int(): number {
    let x: number = 42;
    return x;
}

function make_str(): string {
    let x: string = "hello";
    return x;
}
""",
    "kotlin": """\
fun make_int(): Int {
    val x = 42
    return x
}

fun make_str(): String {
    val x = "hello"
    return x
}
""",
    "csharp": """\
class Main {
    static int make_int() {
        int x = 42;
        return x;
    }

    static string make_str() {
        string x = "hello";
        return x;
    }
}
""",
    "go": """\
func make_int() int {
    x := 42
    return x
}

func make_str() string {
    x := "hello"
    return x
}
""",
    "rust": """\
fn make_int() -> i32 {
    let x = 42;
    return x;
}

fn make_str() -> String {
    let x = "hello";
    return x;
}
""",
    "scala": """\
def make_int(): Int = {
    val x = 42
    return x
}

def make_str(): String = {
    val x = "hello"
    return x
}
""",
    "lua": """\
function make_int()
    local x = 42
    return x
end

function make_str()
    local x = "hello"
    return x
end
""",
    "ruby": """\
def make_int()
  x = 42
  return x
end

def make_str()
  x = "hello"
  return x
end
""",
    "php": """\
<?php
function make_int() {
    $x = 42;
    return $x;
}

function make_str() {
    $x = "hello";
    return $x;
}
""",
    "c": """\
int make_int() {
    int x = 42;
    return x;
}

float make_str() {
    float x = 3.14;
    return x;
}
""",
    "cpp": """\
int make_int() {
    int x = 42;
    return x;
}

string make_str() {
    string x = "hello";
    return x;
}
""",
    "pascal": """\
function make_int: integer;
var x: integer;
begin
    x := 42;
    make_int := x;
end;

function make_str: string;
var x: string;
begin
    x := 'hello';
    make_str := x;
end;
""",
}


@pytest.fixture(params=sorted(_SCOPING_SOURCES.keys()))
def scoping_lang(request):
    return request.param


# Per-language canonical type for "integer 42" and "string hello"
_EXPECTED_INT_TYPE: dict[str, str] = {
    "typescript": TypeName.FLOAT,  # TS `number` → Float
}
_EXPECTED_STR_TYPE: dict[str, str] = {
    "c": TypeName.FLOAT,  # C has no string type; use float to test scoping
}


class TestVarTypeScopingCrossLanguage:
    # Languages that wrap functions in a class
    _CLASS_WRAPPED = {"java": "Main", "csharp": "Main"}

    def test_same_var_name_different_types_scoped(self, scoping_lang):
        """Variable 'x' in make_int is Int, 'x' in make_str is String — no collision."""
        source = _SCOPING_SOURCES[scoping_lang]
        instructions, env = _lower_and_infer(source, scoping_lang)
        expected_int = _EXPECTED_INT_TYPE.get(scoping_lang, TypeName.INT)
        expected_str = _EXPECTED_STR_TYPE.get(scoping_lang, TypeName.STRING)
        cls = self._CLASS_WRAPPED.get(scoping_lang)
        class_kw = {"class_name": scalar(cls)} if cls else {}
        # Both functions should have their return types correctly inferred
        assert (
            env.get_func_signature("make_int", **class_kw).return_type == expected_int
        )
        assert (
            env.get_func_signature("make_str", **class_kw).return_type == expected_str
        )
        # Key: the two return types must be DIFFERENT (scoping works)
        assert (
            env.get_func_signature("make_int", **class_kw).return_type
            != env.get_func_signature("make_str", **class_kw).return_type
        )


# ---------------------------------------------------------------------------
# Generic type extraction → type inference (end-to-end)
# ---------------------------------------------------------------------------


class TestJavaGenericTypeInference:
    """End-to-end: Java generic type annotations flow through inference."""

    def test_list_of_string_var_type(self):
        instructions, env = _lower_and_infer(
            "class M { void m() { List<String> items = new ArrayList<>(); } }",
            "java",
        )
        assert env.var_types["items"] == "List[String]"

    def test_map_generic_normalises_inner_types(self):
        instructions, env = _lower_and_infer(
            "class M { void m() { Map<String, Integer> m = new HashMap<>(); } }",
            "java",
        )
        assert env.var_types["m"] == "Map[String, Int]"

    def test_generic_return_type_in_signature(self):
        instructions, env = _lower_and_infer(
            "class M { List<String> getNames() { return null; } }",
            "java",
        )
        sig = env.get_func_signature("getNames", class_name=scalar("M"))
        assert sig.return_type == "List[String]"


class TestCSharpGenericTypeInference:
    """End-to-end: C# generic type annotations flow through inference."""

    def test_list_of_string_var_type(self):
        instructions, env = _lower_and_infer(
            "class M { void m() { List<string> items = new List<string>(); } }",
            "csharp",
        )
        assert env.var_types["items"] == "List[String]"

    def test_dictionary_normalises_inner_types(self):
        instructions, env = _lower_and_infer(
            "class M { void m() { Dictionary<string, int> d = new Dictionary<string, int>(); } }",
            "csharp",
        )
        assert env.var_types["d"] == "Dictionary[String, Int]"


class TestScalaGenericTypeInference:
    """End-to-end: Scala generic type annotations flow through inference."""

    def test_list_of_string_var_type(self):
        instructions, env = _lower_and_infer(
            'object M { val items: List[String] = List("a") }',
            "scala",
        )
        assert env.var_types["items"] == "List[String]"

    def test_map_generic_var_type(self):
        instructions, env = _lower_and_infer(
            "object M { val m: Map[String, Int] = Map() }",
            "scala",
        )
        assert env.var_types["m"] == "Map[String, Int]"


class TestKotlinGenericTypeInference:
    """End-to-end: Kotlin generic type annotations flow through inference."""

    def test_list_of_string_var_type(self):
        instructions, env = _lower_and_infer(
            'fun main() { val items: List<String> = listOf("a") }',
            "kotlin",
        )
        assert env.var_types["items"] == "List[String]"

    def test_map_generic_var_type(self):
        instructions, env = _lower_and_infer(
            "fun main() { val m: Map<String, Int> = mapOf() }",
            "kotlin",
        )
        assert env.var_types["m"] == "Map[String, Int]"


# ---------------------------------------------------------------------------
# Array element type promotion → Array[ElementType]
# ---------------------------------------------------------------------------


class TestArrayElementTypePromotion:
    """End-to-end: array element types are promoted to Array[ElementType]."""

    def test_python_list_element_type_int(self):
        """Python items = [1, 2, 3] should infer Array[Int] for items."""
        instructions, env = _lower_and_infer(
            "items = [1, 2, 3]",
            "python",
        )
        assert env.var_types["items"] == "Array[Int]"

    def test_python_list_element_type_string(self):
        """Python names = ['a', 'b'] should infer Array[String] for names."""
        instructions, env = _lower_and_infer(
            'names = ["a", "b"]',
            "python",
        )
        assert env.var_types["names"] == "Array[String]"

    def test_javascript_array_element_type(self):
        """JS const items = [1, 2, 3] should infer Array[Int] for items."""
        instructions, env = _lower_and_infer(
            "const items = [1, 2, 3];",
            "javascript",
        )
        assert env.var_types["items"] == "Array[Int]"

    def test_ruby_array_element_type(self):
        """Ruby items = [1, 2, 3] should infer Array[Int] for items."""
        instructions, env = _lower_and_infer(
            "items = [1, 2, 3]",
            "ruby",
        )
        assert env.var_types["items"] == "Array[Int]"


# ---------------------------------------------------------------------------
# Union type inference (variable assigned different types)
# ---------------------------------------------------------------------------


class TestUnionTypeInference:
    def test_python_var_assigned_int_then_string(self):
        """Python: x = 5; x = 'hello' → x is Union[Int, String]."""
        source = 'x = 5\nx = "hello"'
        _, env = _lower_and_infer(source, "python")
        assert env.var_types["x"] == "Union[Int, String]"

    def test_javascript_var_assigned_different_types(self):
        """JS: let x = 5; x = 'hello' → x is Union[Int, String]."""
        source = 'let x = 5;\nx = "hello";'
        _, env = _lower_and_infer(source, "javascript")
        assert env.var_types["x"] == "Union[Int, String]"

    def test_python_var_same_type_no_union(self):
        """Python: x = 5; x = 10 → x is Int (no union)."""
        source = "x = 5\nx = 10"
        _, env = _lower_and_infer(source, "python")
        assert env.var_types["x"] == "Int"

    def test_python_three_types(self):
        """Python: x = 5; x = 'hi'; x = True → Union[Bool, Int, String]."""
        source = 'x = 5\nx = "hi"\nx = True'
        _, env = _lower_and_infer(source, "python")
        assert env.var_types["x"] == "Union[Bool, Int, String]"


# ---------------------------------------------------------------------------
# FunctionType inference from source programs
# ---------------------------------------------------------------------------


class TestFunctionTypeInferenceIntegration:
    def test_python_function_with_seeded_types_produces_function_type(self):
        """Python def add(a, b): return a + b with seeded Int types → FunctionType."""
        source = """\
def add(a, b):
    return a + b
"""
        lang = Language("python")
        frontend = get_frontend(lang)
        instructions = frontend.lower(source.encode("utf-8"))
        # Seed param and return types to exercise FunctionType inference
        builder = frontend.type_env_builder
        # Find the func label for add
        func_labels = [k for k in builder.func_param_types if k.startswith("func_add")]
        # If frontend doesn't seed params, seed them manually
        if not func_labels:
            # Find the label from the IR
            labels = [
                i.label
                for i in instructions
                if i.opcode == Opcode.LABEL
                and i.label
                and i.label.value.startswith("func_add")
            ]
            func_label = labels[0].value if labels else "func_add_0"
            builder.func_param_types[func_label] = [
                ("a", scalar("Int")),
                ("b", scalar("Int")),
            ]
            builder.func_return_types[func_label] = scalar("Int")
        else:
            func_label = func_labels[0]
            builder.func_param_types[func_label] = [
                ("a", scalar("Int")),
                ("b", scalar("Int")),
            ]
            builder.func_return_types[func_label] = scalar("Int")

        env = infer_types(
            instructions,
            _resolver(),
            type_env_builder=builder,
            func_symbol_table=frontend.func_symbol_table,
        )
        # The CONST for function ref should produce a FunctionType register
        func_ref_consts = [
            i
            for i in instructions
            if i.opcode == Opcode.CONST
            and i.result_reg
            and i.operands
            and str(i.operands[0]).startswith("func_add_")
        ]
        assert len(func_ref_consts) >= 1
        func_reg = func_ref_consts[0].result_reg
        assert func_reg in env.register_types
        func_type = env.register_types[func_reg]
        assert isinstance(func_type, FunctionType)
        assert func_type.return_type == scalar("Int")

    def test_java_typed_function_produces_function_type(self):
        """Java static int add(int a, int b) → FunctionType register."""
        source = """\
class M {
    static int add(int a, int b) {
        return a + b;
    }
}
"""
        instructions, env = _lower_and_infer(source, "java")
        # Find function ref CONST for add
        func_ref_consts = [
            i
            for i in instructions
            if i.opcode == Opcode.CONST
            and i.result_reg
            and i.operands
            and str(i.operands[0]).startswith("func_add_")
        ]
        assert len(func_ref_consts) >= 1
        func_reg = func_ref_consts[0].result_reg
        assert func_reg in env.register_types
        func_type = env.register_types[func_reg]
        assert isinstance(func_type, FunctionType)
        assert func_type.return_type == scalar("Int")
        assert len(func_type.params) >= 2

    def test_python_function_ref_stored_in_variable(self):
        """Python: f = add assigns FunctionType to variable f."""
        source = """\
def add(a, b):
    return a + b

f = add
"""
        lang = Language("python")
        frontend = get_frontend(lang)
        instructions = frontend.lower(source.encode("utf-8"))
        builder = frontend.type_env_builder
        # Find and seed the func label
        labels = [
            i.label
            for i in instructions
            if i.opcode == Opcode.LABEL
            and i.label.is_present()
            and i.label.value.startswith("func_add")
        ]
        func_label = labels[0].value if labels else "func_add_0"
        builder.func_param_types[func_label] = [
            ("a", scalar("Int")),
            ("b", scalar("Int")),
        ]
        builder.func_return_types[func_label] = scalar("Int")

        env = infer_types(
            instructions,
            _resolver(),
            type_env_builder=builder,
            func_symbol_table=frontend.func_symbol_table,
        )
        # Find if 'f' or 'add' got a FunctionType
        # The add variable should get the FunctionType from STORE_VAR
        # (since the CONST func ref gets FunctionType, and STORE_VAR propagates it)
        func_ref_consts = [
            i
            for i in instructions
            if i.opcode == Opcode.CONST
            and i.result_reg
            and i.operands
            and str(i.operands[0]).startswith("func_add_")
        ]
        assert len(func_ref_consts) >= 1
        func_reg = func_ref_consts[0].result_reg
        assert isinstance(env.register_types[func_reg], FunctionType)


# ---------------------------------------------------------------------------
# Tuple Types
# ---------------------------------------------------------------------------


class TestTupleTypeInferenceIntegration:
    """Integration: Python tuple literals produce Tuple[T1, T2, ...] types."""

    def test_python_homogeneous_tuple(self):
        """Python (1, 2, 3) → Tuple[Int, Int, Int]."""
        source = "x = (1, 2, 3)\n"
        _, env = _lower_and_infer(source, "python")
        assert env.var_types["x"] == tuple_of(
            scalar("Int"), scalar("Int"), scalar("Int")
        )

    def test_python_heterogeneous_tuple(self):
        """Python (1, 'hello') → Tuple[Int, String]."""
        source = 'x = (1, "hello")\n'
        _, env = _lower_and_infer(source, "python")
        assert env.var_types["x"] == tuple_of(scalar("Int"), scalar("String"))

    def test_python_tuple_element_access(self):
        """Python y = t[0] where t = (1, 'hi') → y is Int."""
        source = """\
t = (1, "hi")
y = t[0]
"""
        _, env = _lower_and_infer(source, "python")
        assert env.var_types["t"] == tuple_of(scalar("Int"), scalar("String"))
        assert env.var_types["y"] == scalar("Int")

    def test_python_nested_tuple(self):
        """Python ((1, 2), 'a') → Tuple[Tuple[Int, Int], String]."""
        source = """\
inner = (1, 2)
outer = (inner, "a")
"""
        _, env = _lower_and_infer(source, "python")
        assert env.var_types["inner"] == tuple_of(scalar("Int"), scalar("Int"))


# ---------------------------------------------------------------------------
# Type Aliases
# ---------------------------------------------------------------------------


class TestTypeAliasIntegration:
    """Integration: C typedef seeds type aliases and resolves them."""

    def test_c_typedef_seeds_alias(self):
        """C: typedef int UserId; UserId x = 42; → x is Int."""
        source = """\
typedef int UserId;
UserId x = 42;
"""
        _, env = _lower_and_infer(source, "c")
        assert env.var_types["x"] == scalar("Int")
        assert "UserId" in env.type_aliases
        assert env.type_aliases["UserId"] == scalar("Int")

    def test_c_typedef_pointer_alias(self):
        """C: typedef int* IntPtr; IntPtr p; → p is Pointer[Int]."""
        source = """\
typedef int* IntPtr;
IntPtr p;
"""
        _, env = _lower_and_infer(source, "c")
        from interpreter.types.type_expr import pointer

        assert env.var_types["p"] == pointer(scalar("Int"))
        assert "IntPtr" in env.type_aliases


# ---------------------------------------------------------------------------
# Interface/Trait Typing
# ---------------------------------------------------------------------------


class TestInterfaceTypingIntegration:
    """Integration: Java implements extracts interface relationships."""

    def test_java_implements_single_interface(self):
        """Java: class Dog implements Comparable → interface_implementations includes it."""
        source = """\
class Dog implements Comparable {
    int compareTo(Object o) {
        return 0;
    }
}
"""
        _, env = _lower_and_infer(source, "java")
        assert "Dog" in env.interface_implementations
        assert "Comparable" in env.interface_implementations["Dog"]

    def test_java_implements_multiple_interfaces(self):
        """Java: class Dog implements A, B → both recorded."""
        source = """\
class Dog implements Comparable, Serializable {
    int compareTo(Object o) { return 0; }
}
"""
        _, env = _lower_and_infer(source, "java")
        assert "Dog" in env.interface_implementations
        impls = env.interface_implementations["Dog"]
        assert "Comparable" in impls
        assert "Serializable" in impls


class TestVarianceIntegration:
    """Integration: source → inference → variance-annotated TypeGraph subtype checks."""

    def test_java_list_inferred_type_with_invariant_variance(self):
        """Java List<String> inferred type checked against invariant variance rules."""
        from interpreter.types.type_graph import TypeGraph, DEFAULT_TYPE_NODES
        from interpreter.constants import Variance

        _, env = _lower_and_infer(
            "class M { void m() { List<String> items = new ArrayList<>(); } }",
            "java",
        )
        inferred_type = env.var_types["items"]
        assert inferred_type == "List[String]"

        # With invariant variance, List[String] should NOT be subtype of List[Any]
        graph = TypeGraph(
            DEFAULT_TYPE_NODES,
            variance_registry={"List": (Variance.INVARIANT,)},
        )
        assert not graph.is_subtype_expr(
            inferred_type, ParameterizedType("List", (scalar("Any"),))
        )
        # But IS subtype of itself
        assert graph.is_subtype_expr(inferred_type, inferred_type)

    def test_java_map_inferred_type_with_mixed_variance(self):
        """Java Map<String, Integer> checked with invariant key, covariant value."""
        from interpreter.types.type_graph import TypeGraph, DEFAULT_TYPE_NODES
        from interpreter.constants import Variance

        _, env = _lower_and_infer(
            "class M { void m() { Map<String, Integer> m = new HashMap<>(); } }",
            "java",
        )
        inferred_type = env.var_types["m"]
        assert inferred_type == "Map[String, Int]"

        graph = TypeGraph(
            DEFAULT_TYPE_NODES,
            variance_registry={"Map": (Variance.INVARIANT, Variance.COVARIANT)},
        )
        # Same key, wider value: Map[String, Int] <: Map[String, Number] (covariant value)
        assert graph.is_subtype_expr(
            inferred_type,
            ParameterizedType("Map", (scalar("String"), scalar("Number"))),
        )
        # Different key: NOT subtype (invariant key)
        assert not graph.is_subtype_expr(
            inferred_type,
            ParameterizedType("Map", (scalar("Any"), scalar("Int"))),
        )

    def test_kotlin_list_inferred_type_covariant_default(self):
        """Kotlin List<String> with default covariant variance allows widening."""
        from interpreter.types.type_graph import TypeGraph, DEFAULT_TYPE_NODES

        _, env = _lower_and_infer(
            'fun main() { val items: List<String> = listOf("a") }',
            "kotlin",
        )
        inferred_type = env.var_types["items"]
        assert inferred_type == "List[String]"

        # Default covariant: List[String] IS subtype of List[Any]
        graph = TypeGraph(DEFAULT_TYPE_NODES)
        assert graph.is_subtype_expr(
            inferred_type, ParameterizedType("List", (scalar("Any"),))
        )


class TestBoundedTypeVarIntegration:
    """Integration: source → inference → TypeVar bound checks against inferred types."""

    def test_java_inferred_int_satisfies_number_bound(self):
        """Java int var inferred as Int satisfies TypeVar bounded by Number."""
        from interpreter.types.type_graph import TypeGraph, DEFAULT_TYPE_NODES
        from interpreter.types.type_expr import typevar, scalar
        from interpreter.constants import TypeName

        _, env = _lower_and_infer(
            "class M { static int x_tv1 = 42; }",
            "java",
        )
        inferred = env.var_types["x_tv1"]
        assert inferred == "Int"

        graph = TypeGraph(DEFAULT_TYPE_NODES)
        t_num = typevar("T", bound=scalar(TypeName.NUMBER))
        # Inferred Int satisfies T: Number
        assert graph.is_subtype_expr(inferred, t_num)

    def test_java_inferred_string_fails_number_bound(self):
        """Java String var does NOT satisfy TypeVar bounded by Number."""
        from interpreter.types.type_graph import TypeGraph, DEFAULT_TYPE_NODES
        from interpreter.types.type_expr import typevar, scalar
        from interpreter.constants import TypeName

        _, env = _lower_and_infer(
            'class M { void m() { String s_tv1 = "hello"; } }',
            "java",
        )
        inferred = env.var_types["s_tv1"]
        assert inferred == "String"

        graph = TypeGraph(DEFAULT_TYPE_NODES)
        t_num = typevar("T", bound=scalar(TypeName.NUMBER))
        # String does NOT satisfy T: Number
        assert not graph.is_subtype_expr(inferred, t_num)

    def test_java_generic_list_satisfies_typevar_container_bound(self):
        """Java List[Int] checked against List[T: Number] with TypeVar argument."""
        from interpreter.types.type_graph import TypeGraph, DEFAULT_TYPE_NODES
        from interpreter.types.type_expr import typevar, scalar, array_of
        from interpreter.constants import TypeName

        _, env = _lower_and_infer(
            "class M { void m() { List<Integer> nums_tv1 = new ArrayList<>(); } }",
            "java",
        )
        inferred = env.var_types["nums_tv1"]
        assert inferred == "List[Int]"

        graph = TypeGraph(DEFAULT_TYPE_NODES)
        t_num = typevar("T", bound=scalar(TypeName.NUMBER))
        list_t = ParameterizedType("List", (t_num,))
        # List[Int] <: List[T: Number] because Int <: T: Number (bound=Number)
        assert graph.is_subtype_expr(inferred, list_t)


class TestJavaInterfaceTypeInference:
    """Java interface methods should have return types available in func_return_types."""

    def test_interface_method_return_type_seeded(self):
        """Interface method with declared return type seeds method_signatures."""
        _instructions, env = _lower_and_infer(
            """\
interface Calculator {
    int compute(int x);
}
""",
            "java",
        )
        sig = env.get_func_signature("compute", class_name=scalar("Calculator"))
        assert (
            sig.return_type == "Int"
        ), f"Expected 'compute' in method_signatures[Calculator], got: {env.method_signatures}"

    def test_interface_chain_walk_resolves_method(self):
        """When class implements interface, method type resolves via chain walk."""
        _instructions, env = _lower_and_infer(
            """\
interface Greeter {
    String greet();
}

class HelloGreeter implements Greeter {
    public String greet() {
        return "hello";
    }
}

class Main {
    public static void main(String[] args) {
        HelloGreeter g = new HelloGreeter();
        String msg = g.greet();
    }
}
""",
            "java",
        )
        assert env.var_types.get("msg") == scalar(
            "String"
        ), f"Expected 'msg' typed as String, got: {env.var_types.get('msg')}"
        assert env.interface_implementations.get("HelloGreeter") == (
            "Greeter",
        ), f"Expected HelloGreeter implements Greeter, got: {env.interface_implementations}"


class TestGoInterfaceTypeInference:
    """Go interface methods should have return types available in func_signatures."""

    def test_interface_method_return_type_seeded(self):
        """Interface method with declared return type seeds method_signatures."""
        _instructions, env = _lower_and_infer(
            """\
package main

type Shape interface {
    Area() float64
}
""",
            "go",
        )
        sig = env.get_func_signature("Area", class_name=scalar("Shape"))
        assert (
            sig.return_type == "Float"
        ), f"Expected 'Area' in method_signatures[Shape], got: {env.method_signatures}"


class TestCSharpInterfaceChainWalk:
    """C# classes implementing interfaces should seed interface_implementations."""

    def test_csharp_implements_seeds_interface(self):
        _instructions, env = _lower_and_infer(
            """\
interface ICalculator {
    int Compute(int x);
}

class SimpleCalc : ICalculator {
    public int Compute(int x) {
        return x * 2;
    }
}
""",
            "csharp",
        )
        assert "ICalculator" in [
            iface for impls in env.interface_implementations.values() for iface in impls
        ], f"Expected ICalculator in interface_implementations, got: {env.interface_implementations}"


class TestTypeScriptInterfaceChainWalk:
    """TS classes implementing interfaces should seed interface_implementations."""

    def test_ts_implements_seeds_interface(self):
        _instructions, env = _lower_and_infer(
            """\
interface Calculator {
    compute(x: number): number;
}

class SimpleCalc implements Calculator {
    compute(x: number): number {
        return x * 2;
    }
}
""",
            "typescript",
        )
        assert env.interface_implementations.get("SimpleCalc") == (
            "Calculator",
        ), f"Expected SimpleCalc implements Calculator, got: {env.interface_implementations}"


class TestKotlinInterfaceTypeInference:
    """Kotlin interface methods should have return types available in func_signatures."""

    def test_interface_method_return_type_seeded(self):
        """Interface method with declared return type seeds method_signatures."""
        _instructions, env = _lower_and_infer(
            """\
interface Calculator {
    fun compute(x: Int): Int
}
""",
            "kotlin",
        )
        sig = env.get_func_signature("compute", class_name=scalar("Calculator"))
        assert (
            sig.return_type == "Int"
        ), f"Expected 'compute' in method_signatures[Calculator], got: {env.method_signatures}"

    def test_kotlin_implements_seeds_interface(self):
        _instructions, env = _lower_and_infer(
            """\
interface Calculator {
    fun compute(x: Int): Int
}

class SimpleCalc : Calculator {
    override fun compute(x: Int): Int {
        return x * 2
    }
}
""",
            "kotlin",
        )
        assert "Calculator" in [
            iface for impls in env.interface_implementations.values() for iface in impls
        ], f"Expected Calculator in interface_implementations, got: {env.interface_implementations}"


# ---------------------------------------------------------------------------
# Class-scoped method signatures
# ---------------------------------------------------------------------------


class TestClassScopedMethodSignatures:
    """method_signatures should separate methods by class."""

    def test_java_overloaded_methods_in_method_signatures(self):
        """Java class with overloaded add() should have both in method_signatures."""
        from interpreter.types.type_expr import scalar

        _instructions, env = _lower_and_infer(
            """\
class Calc {
    int add(int a, int b) { return a + b; }
    int add(int a, int b, int c) { return a + b + c; }
}
""",
            "java",
        )
        calc_type = scalar("Calc")
        assert calc_type in env.method_signatures
        sigs = env.method_signatures[calc_type].get("add", [])
        assert len(sigs) == 2
        # First overload: this + 2 params
        assert len(sigs[0].params) == 3
        # Second overload: this + 3 params
        assert len(sigs[1].params) == 4

    def test_different_classes_dont_collide(self):
        """Dog.speak and Animal.speak should be in separate class scopes."""
        from interpreter.types.type_expr import scalar

        _instructions, env = _lower_and_infer(
            """\
class Animal {
    void speak() {}
}
class Dog extends Animal {
    void speak() {}
    void fetch(String toy) {}
}
""",
            "java",
        )
        animal_speak = env.get_func_signature("speak", class_name=scalar("Animal"))
        dog_speak = env.get_func_signature("speak", class_name=scalar("Dog"))
        dog_fetch = env.get_func_signature("fetch", class_name=scalar("Dog"))
        # Animal.speak has 1 param (this)
        assert len(animal_speak.params) == 1
        # Dog.speak has 1 param (this)
        assert len(dog_speak.params) == 1
        # Dog.fetch has 2 params (this, toy)
        assert len(dog_fetch.params) == 2
        # Animal should NOT have fetch
        from interpreter.types.type_environment import _NULL_SIGNATURE

        assert (
            env.get_func_signature("fetch", class_name=scalar("Animal"))
            is _NULL_SIGNATURE
        )
