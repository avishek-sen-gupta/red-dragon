"""Tests for frontend type annotation extraction — verifies type_hint flows through IR.

Each test parses a small source snippet through a frontend and inspects
the resulting IR instructions for correct type_hint values.
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
    def _parse(self, source: str) -> list[IRInstruction]:
        from interpreter.frontends.java import JavaFrontend

        return JavaFrontend(TreeSitterParserFactory(), "java").lower(source.encode())

    def test_local_var_int_carries_type_hint(self):
        instructions = self._parse("class M { void f() { int x = 42; } }")
        stores = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_VAR and "x" in i.operands
        ]
        assert any(i.type_hint == "Int" for i in stores)

    def test_param_int_carries_type_hint(self):
        instructions = self._parse("class M { void f(int x) { } }")
        params = _find_symbolic_params(instructions)
        param_x = [p for p in params if any("param:x" in str(op) for op in p.operands)]
        assert len(param_x) >= 1
        assert param_x[0].type_hint == "Int"

    def test_param_string_carries_type_hint(self):
        instructions = self._parse("class M { void f(String s) { } }")
        params = _find_symbolic_params(instructions)
        param_s = [p for p in params if any("param:s" in str(op) for op in p.operands)]
        assert len(param_s) >= 1
        assert param_s[0].type_hint == "String"

    def test_field_decl_carries_type_hint(self):
        instructions = self._parse("class M { double value = 3.14; }")
        stores = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_VAR and "value" in i.operands
        ]
        assert any(i.type_hint == "Float" for i in stores)


# ── Go ────────────────────────────────────────────────────────────


class TestGoTypeExtraction:
    def _parse(self, source: str) -> list[IRInstruction]:
        from interpreter.frontends.go import GoFrontend

        return GoFrontend(TreeSitterParserFactory(), "go").lower(source.encode())

    def test_var_int_carries_type_hint(self):
        instructions = self._parse("package main\nvar x int = 42")
        stores = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_VAR and "x" in i.operands
        ]
        assert any(i.type_hint == "Int" for i in stores)

    def test_param_string_carries_type_hint(self):
        instructions = self._parse("package main\nfunc greet(name string) { }")
        params = _find_symbolic_params(instructions)
        param_name = [
            p for p in params if any("param:name" in str(op) for op in p.operands)
        ]
        assert len(param_name) >= 1
        assert param_name[0].type_hint == "String"

    def test_var_without_type_has_empty_hint(self):
        """Short var decl (:=) has no explicit type — type_hint should be empty."""
        instructions = self._parse("package main\nfunc main() { x := 42 }")
        stores = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_VAR and "x" in i.operands
        ]
        assert all(i.type_hint == "" for i in stores)


# ── Rust ──────────────────────────────────────────────────────────


class TestRustTypeExtraction:
    def _parse(self, source: str) -> list[IRInstruction]:
        from interpreter.frontends.rust import RustFrontend

        return RustFrontend(TreeSitterParserFactory(), "rust").lower(source.encode())

    def test_let_i32_carries_type_hint(self):
        instructions = self._parse("fn main() { let x: i32 = 42; }")
        stores = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_VAR and "x" in i.operands
        ]
        assert any(i.type_hint == "Int" for i in stores)

    def test_param_f64_carries_type_hint(self):
        instructions = self._parse("fn area(r: f64) -> f64 { r }")
        params = _find_symbolic_params(instructions)
        param_r = [p for p in params if any("param:r" in str(op) for op in p.operands)]
        assert len(param_r) >= 1
        assert param_r[0].type_hint == "Float"

    def test_const_bool_carries_type_hint(self):
        instructions = self._parse("const FLAG: bool = true;")
        stores = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_VAR and "FLAG" in i.operands
        ]
        assert any(i.type_hint == "Bool" for i in stores)


# ── C ─────────────────────────────────────────────────────────────


class TestCTypeExtraction:
    def _parse(self, source: str) -> list[IRInstruction]:
        from interpreter.frontends.c import CFrontend

        return CFrontend(TreeSitterParserFactory(), "c").lower(source.encode())

    def test_declaration_int_carries_type_hint(self):
        instructions = self._parse("int x = 42;")
        stores = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_VAR and "x" in i.operands
        ]
        assert any(i.type_hint == "Int" for i in stores)

    def test_param_float_carries_type_hint(self):
        instructions = self._parse("void f(float x) { }")
        params = _find_symbolic_params(instructions)
        param_x = [p for p in params if any("param:x" in str(op) for op in p.operands)]
        assert len(param_x) >= 1
        assert param_x[0].type_hint == "Float"


# ── C++ ───────────────────────────────────────────────────────────


class TestCppTypeExtraction:
    def _parse(self, source: str) -> list[IRInstruction]:
        from interpreter.frontends.cpp import CppFrontend

        return CppFrontend(TreeSitterParserFactory(), "cpp").lower(source.encode())

    def test_declaration_int_carries_type_hint(self):
        instructions = self._parse("int x = 42;")
        stores = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_VAR and "x" in i.operands
        ]
        assert any(i.type_hint == "Int" for i in stores)

    def test_param_double_carries_type_hint(self):
        instructions = self._parse("void f(double x) { }")
        params = _find_symbolic_params(instructions)
        param_x = [p for p in params if any("param:x" in str(op) for op in p.operands)]
        assert len(param_x) >= 1
        assert param_x[0].type_hint == "Float"


# ── C# ────────────────────────────────────────────────────────────


class TestCSharpTypeExtraction:
    def _parse(self, source: str) -> list[IRInstruction]:
        from interpreter.frontends.csharp import CSharpFrontend

        return CSharpFrontend(TreeSitterParserFactory(), "csharp").lower(
            source.encode()
        )

    def test_local_var_int_carries_type_hint(self):
        instructions = self._parse("class M { void F() { int x = 42; } }")
        stores = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_VAR and "x" in i.operands
        ]
        assert any(i.type_hint == "Int" for i in stores)

    def test_param_string_carries_type_hint(self):
        instructions = self._parse("class M { void F(string s) { } }")
        params = _find_symbolic_params(instructions)
        param_s = [p for p in params if any("param:s" in str(op) for op in p.operands)]
        assert len(param_s) >= 1
        assert param_s[0].type_hint == "String"


# ── Kotlin ────────────────────────────────────────────────────────


class TestKotlinTypeExtraction:
    def _parse(self, source: str) -> list[IRInstruction]:
        from interpreter.frontends.kotlin import KotlinFrontend

        return KotlinFrontend(TreeSitterParserFactory(), "kotlin").lower(
            source.encode()
        )

    def test_param_int_carries_type_hint(self):
        instructions = self._parse("fun add(x: Int, y: Int): Int { return x }")
        params = _find_symbolic_params(instructions)
        param_x = [p for p in params if any("param:x" in str(op) for op in p.operands)]
        assert len(param_x) >= 1
        assert param_x[0].type_hint == "Int"

    def test_property_string_carries_type_hint(self):
        instructions = self._parse('val name: String = "Alice"')
        stores = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_VAR and "name" in i.operands
        ]
        assert any(i.type_hint == "String" for i in stores)


# ── Scala ─────────────────────────────────────────────────────────


class TestScalaTypeExtraction:
    def _parse(self, source: str) -> list[IRInstruction]:
        from interpreter.frontends.scala import ScalaFrontend

        return ScalaFrontend(TreeSitterParserFactory(), "scala").lower(source.encode())

    def test_param_int_carries_type_hint(self):
        instructions = self._parse("def add(x: Int, y: Int): Int = x")
        params = _find_symbolic_params(instructions)
        param_x = [p for p in params if any("param:x" in str(op) for op in p.operands)]
        assert len(param_x) >= 1
        assert param_x[0].type_hint == "Int"

    def test_val_string_carries_type_hint(self):
        instructions = self._parse('val name: String = "Alice"')
        stores = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_VAR and "name" in i.operands
        ]
        assert any(i.type_hint == "String" for i in stores)


# ── Pascal ────────────────────────────────────────────────────────


class TestPascalTypeExtraction:
    def _parse(self, source: str) -> list[IRInstruction]:
        from interpreter.frontends.pascal import PascalFrontend

        return PascalFrontend(TreeSitterParserFactory(), "pascal").lower(
            source.encode()
        )

    def test_var_integer_carries_type_hint(self):
        instructions = self._parse("program test;\nvar x: integer;\nbegin\nend.")
        stores = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_VAR and "x" in i.operands
        ]
        assert any(i.type_hint == "Int" for i in stores)

    def test_param_integer_carries_type_hint(self):
        instructions = self._parse(
            "program test;\nprocedure foo(x: integer);\nbegin\nend;\nbegin\nend."
        )
        params = _find_symbolic_params(instructions)
        param_x = [p for p in params if any("param:x" in str(op) for op in p.operands)]
        assert len(param_x) >= 1
        assert param_x[0].type_hint == "Int"


# ── TypeScript ────────────────────────────────────────────────────


class TestTypeScriptTypeExtraction:
    def _parse(self, source: str) -> list[IRInstruction]:
        from interpreter.frontends.typescript import TypeScriptFrontend

        return TypeScriptFrontend(TreeSitterParserFactory(), "typescript").lower(
            source.encode()
        )

    def test_param_number_carries_type_hint(self):
        instructions = self._parse(
            "function add(x: number, y: number): number { return x + y; }"
        )
        params = _find_symbolic_params(instructions)
        param_x = [p for p in params if any("param:x" in str(op) for op in p.operands)]
        assert len(param_x) >= 1
        assert param_x[0].type_hint == "Float"

    def test_param_string_carries_type_hint(self):
        instructions = self._parse(
            "function greet(name: string): string { return name; }"
        )
        params = _find_symbolic_params(instructions)
        param_name = [
            p for p in params if any("param:name" in str(op) for op in p.operands)
        ]
        assert len(param_name) >= 1
        assert param_name[0].type_hint == "String"


# ── Python ────────────────────────────────────────────────────────


class TestPythonTypeExtraction:
    def _parse(self, source: str) -> list[IRInstruction]:
        from interpreter.frontends.python import PythonFrontend

        return PythonFrontend(TreeSitterParserFactory(), "python").lower(
            source.encode()
        )

    def test_typed_param_int_carries_type_hint(self):
        instructions = self._parse("def add(x: int, y: int) -> int:\n    return x + y")
        params = _find_symbolic_params(instructions)
        param_x = [p for p in params if any("param:x" in str(op) for op in p.operands)]
        assert len(param_x) >= 1
        assert param_x[0].type_hint == "Int"

    def test_untyped_param_has_empty_hint(self):
        instructions = self._parse("def f(x):\n    return x")
        params = _find_symbolic_params(instructions)
        param_x = [p for p in params if any("param:x" in str(op) for op in p.operands)]
        assert len(param_x) >= 1
        assert param_x[0].type_hint == ""


# ── PHP ───────────────────────────────────────────────────────────


class TestPHPTypeExtraction:
    def _parse(self, source: str) -> list[IRInstruction]:
        from interpreter.frontends.php import PhpFrontend

        return PhpFrontend(TreeSitterParserFactory(), "php").lower(source.encode())

    def test_param_int_carries_type_hint(self):
        instructions = self._parse(
            "<?php function add(int $x, int $y): int { return $x + $y; }"
        )
        params = _find_symbolic_params(instructions)
        param_x = [p for p in params if any("param:$x" in str(op) for op in p.operands)]
        assert len(param_x) >= 1
        assert param_x[0].type_hint == "Int"

    def test_param_string_carries_type_hint(self):
        instructions = self._parse(
            "<?php function greet(string $name): string { return $name; }"
        )
        params = _find_symbolic_params(instructions)
        param_name = [
            p for p in params if any("param:$name" in str(op) for op in p.operands)
        ]
        assert len(param_name) >= 1
        assert param_name[0].type_hint == "String"
