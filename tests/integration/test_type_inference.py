"""Integration tests: source → frontend → IR → type inference pass."""

import pytest

from interpreter.api import lower_source
from interpreter.constants import TypeName
from interpreter.default_conversion_rules import DefaultConversionRules
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
