"""Tests for frontend type annotation extraction — verifies type info flows into builder.

Each test parses a small source snippet through a frontend and inspects
the resulting TypeEnvironmentBuilder for correct type seeding.
"""

from __future__ import annotations

from interpreter.ir import IRInstruction, Opcode
from interpreter.parser import TreeSitterParserFactory


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


def _find_symbolic_params(instructions: list[IRInstruction]) -> list[IRInstruction]:
    return [
        inst
        for inst in instructions
        if inst.opcode == Opcode.SYMBOLIC
        and any("param:" in str(op) for op in inst.operands)
    ]


# ── Java ──────────────────────────────────────────────────────────


class TestJavaTypeExtraction:
    def _parse(self, source: str):
        from interpreter.frontends.java import JavaFrontend

        frontend = JavaFrontend(TreeSitterParserFactory(), "java")
        instructions = frontend.lower(source.encode())
        return instructions, frontend.type_env_builder

    def test_local_var_int_carries_type_hint(self):
        _instructions, builder = self._parse("class M { void f() { int x = 42; } }")
        assert builder.var_types.get("x") == "Int"

    def test_param_int_carries_type_hint(self):
        _instructions, builder = self._parse("class M { void f(int x) { } }")
        # Find param type in func_param_types
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "x"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "Int"

    def test_param_string_carries_type_hint(self):
        _instructions, builder = self._parse("class M { void f(String s) { } }")
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "s"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "String"

    def test_field_decl_carries_type_hint(self):
        _instructions, builder = self._parse("class M { double value = 3.14; }")
        assert builder.var_types.get("value") == "Float"

    def test_this_param_seeded_in_instance_method(self):
        _instructions, builder = self._parse("class Dog { int getAge() { return 1; } }")
        this_params = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "this"
        ]
        assert len(this_params) == 1
        assert this_params[0][1] == "Dog"


# ── Go ────────────────────────────────────────────────────────────


class TestGoTypeExtraction:
    def _parse(self, source: str):
        from interpreter.frontends.go import GoFrontend

        frontend = GoFrontend(TreeSitterParserFactory(), "go")
        instructions = frontend.lower(source.encode())
        return instructions, frontend.type_env_builder

    def test_var_int_carries_type_hint(self):
        _instructions, builder = self._parse("package main\nvar x int = 42")
        assert builder.var_types.get("x") == "Int"

    def test_param_string_carries_type_hint(self):
        _instructions, builder = self._parse(
            "package main\nfunc greet(name string) { }"
        )
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "name"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "String"

    def test_var_without_type_has_empty_hint(self):
        """Short var decl (:=) has no explicit type — var_types should not contain x."""
        _instructions, builder = self._parse("package main\nfunc main() { x := 42 }")
        assert "x" not in builder.var_types


# ── Rust ──────────────────────────────────────────────────────────


class TestRustTypeExtraction:
    def _parse(self, source: str):
        from interpreter.frontends.rust import RustFrontend

        frontend = RustFrontend(TreeSitterParserFactory(), "rust")
        instructions = frontend.lower(source.encode())
        return instructions, frontend.type_env_builder

    def test_let_i32_carries_type_hint(self):
        _instructions, builder = self._parse("fn main() { let x: i32 = 42; }")
        assert builder.var_types.get("x") == "Int"

    def test_param_f64_carries_type_hint(self):
        _instructions, builder = self._parse("fn area(r: f64) -> f64 { r }")
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "r"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "Float"

    def test_const_bool_carries_type_hint(self):
        _instructions, builder = self._parse("const FLAG: bool = true;")
        assert builder.var_types.get("FLAG") == "Bool"


# ── C ─────────────────────────────────────────────────────────────


class TestCTypeExtraction:
    def _parse(self, source: str):
        from interpreter.frontends.c import CFrontend

        frontend = CFrontend(TreeSitterParserFactory(), "c")
        instructions = frontend.lower(source.encode())
        return instructions, frontend.type_env_builder

    def test_declaration_int_carries_type_hint(self):
        _instructions, builder = self._parse("int x = 42;")
        assert builder.var_types.get("x") == "Int"

    def test_param_float_carries_type_hint(self):
        _instructions, builder = self._parse("void f(float x) { }")
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "x"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "Float"


# ── C++ ───────────────────────────────────────────────────────────


class TestCppTypeExtraction:
    def _parse(self, source: str):
        from interpreter.frontends.cpp import CppFrontend

        frontend = CppFrontend(TreeSitterParserFactory(), "cpp")
        instructions = frontend.lower(source.encode())
        return instructions, frontend.type_env_builder

    def test_declaration_int_carries_type_hint(self):
        _instructions, builder = self._parse("int x = 42;")
        assert builder.var_types.get("x") == "Int"

    def test_param_double_carries_type_hint(self):
        _instructions, builder = self._parse("void f(double x) { }")
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "x"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "Float"

    def test_this_param_seeded_in_instance_method(self):
        _instructions, builder = self._parse(
            "class Dog { int getAge() { return 1; } };"
        )
        this_params = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "this"
        ]
        assert len(this_params) == 1
        assert this_params[0][1] == "Dog"


# ── C# ────────────────────────────────────────────────────────────


class TestCSharpTypeExtraction:
    def _parse(self, source: str):
        from interpreter.frontends.csharp import CSharpFrontend

        frontend = CSharpFrontend(TreeSitterParserFactory(), "csharp")
        instructions = frontend.lower(source.encode())
        return instructions, frontend.type_env_builder

    def test_local_var_int_carries_type_hint(self):
        _instructions, builder = self._parse("class M { void F() { int x = 42; } }")
        assert builder.var_types.get("x") == "Int"

    def test_param_string_carries_type_hint(self):
        _instructions, builder = self._parse("class M { void F(string s) { } }")
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "s"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "String"

    def test_this_param_seeded_in_instance_method(self):
        _instructions, builder = self._parse("class Dog { int GetAge() { return 1; } }")
        this_params = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "this"
        ]
        assert len(this_params) == 1
        assert this_params[0][1] == "Dog"


# ── Kotlin ────────────────────────────────────────────────────────


class TestKotlinTypeExtraction:
    def _parse(self, source: str):
        from interpreter.frontends.kotlin import KotlinFrontend

        frontend = KotlinFrontend(TreeSitterParserFactory(), "kotlin")
        instructions = frontend.lower(source.encode())
        return instructions, frontend.type_env_builder

    def test_param_int_carries_type_hint(self):
        _instructions, builder = self._parse(
            "fun add(x: Int, y: Int): Int { return x }"
        )
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "x"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "Int"

    def test_property_string_carries_type_hint(self):
        _instructions, builder = self._parse('val name: String = "Alice"')
        assert builder.var_types.get("name") == "String"

    def test_this_param_seeded_in_instance_method(self):
        _instructions, builder = self._parse(
            "class Dog { fun getAge(): Int { return 1 } }"
        )
        this_params = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "this"
        ]
        assert len(this_params) == 1
        assert this_params[0][1] == "Dog"


# ── Scala ─────────────────────────────────────────────────────────


class TestScalaTypeExtraction:
    def _parse(self, source: str):
        from interpreter.frontends.scala import ScalaFrontend

        frontend = ScalaFrontend(TreeSitterParserFactory(), "scala")
        instructions = frontend.lower(source.encode())
        return instructions, frontend.type_env_builder

    def test_param_int_carries_type_hint(self):
        _instructions, builder = self._parse("def add(x: Int, y: Int): Int = x")
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "x"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "Int"

    def test_val_string_carries_type_hint(self):
        _instructions, builder = self._parse('val name: String = "Alice"')
        assert builder.var_types.get("name") == "String"

    def test_this_param_seeded_in_instance_method(self):
        _instructions, builder = self._parse("class Dog { def getAge(): Int = 1 }")
        this_params = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "this"
        ]
        assert len(this_params) == 1
        assert this_params[0][1] == "Dog"


# ── JavaScript ────────────────────────────────────────────────────


class TestJavaScriptTypeExtraction:
    def _parse(self, source: str):
        from interpreter.frontends.javascript import JavaScriptFrontend

        frontend = JavaScriptFrontend(TreeSitterParserFactory(), "javascript")
        instructions = frontend.lower(source.encode())
        return instructions, frontend.type_env_builder

    def test_this_param_seeded_in_instance_method(self):
        _instructions, builder = self._parse("class Dog { getAge() { return 1; } }")
        this_params = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "this"
        ]
        assert len(this_params) == 1
        assert this_params[0][1] == "Dog"


# ── Pascal ────────────────────────────────────────────────────────


class TestPascalTypeExtraction:
    def _parse(self, source: str):
        from interpreter.frontends.pascal import PascalFrontend

        frontend = PascalFrontend(TreeSitterParserFactory(), "pascal")
        instructions = frontend.lower(source.encode())
        return instructions, frontend.type_env_builder

    def test_var_integer_carries_type_hint(self):
        _instructions, builder = self._parse(
            "program test;\nvar x: integer;\nbegin\nend."
        )
        assert builder.var_types.get("x") == "Int"

    def test_param_integer_carries_type_hint(self):
        _instructions, builder = self._parse(
            "program test;\nprocedure foo(x: integer);\nbegin\nend;\nbegin\nend."
        )
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "x"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "Int"


# ── TypeScript ────────────────────────────────────────────────────


class TestTypeScriptTypeExtraction:
    def _parse(self, source: str):
        from interpreter.frontends.typescript import TypeScriptFrontend

        frontend = TypeScriptFrontend(TreeSitterParserFactory(), "typescript")
        instructions = frontend.lower(source.encode())
        return instructions, frontend.type_env_builder

    def test_param_number_carries_type_hint(self):
        _instructions, builder = self._parse(
            "function add(x: number, y: number): number { return x + y; }"
        )
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "x"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "Float"

    def test_param_string_carries_type_hint(self):
        _instructions, builder = self._parse(
            "function greet(name: string): string { return name; }"
        )
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "name"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "String"

    def test_this_param_seeded_in_instance_method(self):
        _instructions, builder = self._parse("class Dog { getAge() { return 1; } }")
        this_params = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "this"
        ]
        assert len(this_params) == 1
        assert this_params[0][1] == "Dog"


# ── Python ────────────────────────────────────────────────────────


class TestPythonTypeExtraction:
    def _parse(self, source: str):
        from interpreter.frontends.python import PythonFrontend

        frontend = PythonFrontend(TreeSitterParserFactory(), "python")
        instructions = frontend.lower(source.encode())
        return instructions, frontend.type_env_builder

    def test_typed_param_int_carries_type_hint(self):
        _instructions, builder = self._parse(
            "def add(x: int, y: int) -> int:\n    return x + y"
        )
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "x"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "Int"

    def test_untyped_param_has_empty_hint(self):
        _instructions, builder = self._parse("def f(x):\n    return x")
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "x"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == ""


# ── PHP ───────────────────────────────────────────────────────────


class TestPHPTypeExtraction:
    def _parse(self, source: str):
        from interpreter.frontends.php import PhpFrontend

        frontend = PhpFrontend(TreeSitterParserFactory(), "php")
        instructions = frontend.lower(source.encode())
        return instructions, frontend.type_env_builder

    def test_param_int_carries_type_hint(self):
        _instructions, builder = self._parse(
            "<?php function add(int $x, int $y): int { return $x + $y; }"
        )
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "$x"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "Int"

    def test_param_string_carries_type_hint(self):
        _instructions, builder = self._parse(
            "<?php function greet(string $name): string { return $name; }"
        )
        param_types = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "$name"
        ]
        assert len(param_types) == 1
        assert param_types[0][1] == "String"

    def test_this_param_seeded_in_instance_method(self):
        _instructions, builder = self._parse(
            "<?php class Dog { function getAge() { return 1; } }"
        )
        this_params = [
            pt
            for pts in builder.func_param_types.values()
            for pt in pts
            if pt[0] == "$this"
        ]
        assert len(this_params) == 1
        assert this_params[0][1] == "Dog"
