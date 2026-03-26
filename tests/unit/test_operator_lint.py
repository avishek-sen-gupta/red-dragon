"""Tests for per-language operator lint pass."""

import pytest

from interpreter.operator_kind import BinopKind, UnopKind
from interpreter.frontends.operator_sets import (
    VALID_BINOPS,
    VALID_UNOPS,
    lint_operators,
    OperatorViolation,
)


class TestOperatorSetsCompleteness:
    """Every language must have an entry in both VALID_BINOPS and VALID_UNOPS."""

    LANGUAGES = frozenset(
        {
            "python",
            "java",
            "javascript",
            "typescript",
            "kotlin",
            "ruby",
            "lua",
            "go",
            "rust",
            "c",
            "cpp",
            "csharp",
            "php",
            "pascal",
            "scala",
        }
    )

    def test_all_languages_have_binop_set(self):
        for lang in self.LANGUAGES:
            assert lang in VALID_BINOPS, f"Missing VALID_BINOPS for {lang}"

    def test_all_languages_have_unop_set(self):
        for lang in self.LANGUAGES:
            assert lang in VALID_UNOPS, f"Missing VALID_UNOPS for {lang}"

    def test_every_binop_set_is_nonempty(self):
        for lang, ops in VALID_BINOPS.items():
            assert len(ops) > 0, f"VALID_BINOPS[{lang}] is empty"

    def test_every_unop_set_is_nonempty(self):
        for lang, ops in VALID_UNOPS.items():
            assert len(ops) > 0, f"VALID_UNOPS[{lang}] is empty"


class TestOperatorSetsContent:
    """Spot-check specific language-operator memberships."""

    def test_python_has_power_and_in(self):
        assert BinopKind.POWER in VALID_BINOPS["python"]
        assert BinopKind.IN in VALID_BINOPS["python"]

    def test_lua_has_concat_and_ne(self):
        assert BinopKind.CONCAT_LUA in VALID_BINOPS["lua"]
        assert BinopKind.NE_LUA in VALID_BINOPS["lua"]

    def test_lua_missing_strict_eq(self):
        assert BinopKind.STRICT_EQ not in VALID_BINOPS["lua"]

    def test_javascript_has_strict_eq(self):
        assert BinopKind.STRICT_EQ in VALID_BINOPS["javascript"]

    def test_kotlin_has_elvis_and_double_bang(self):
        assert BinopKind.NULLISH_COALESCE in VALID_BINOPS["kotlin"]
        assert UnopKind.DOUBLE_BANG in VALID_UNOPS["kotlin"]

    def test_csharp_has_null_coalesce(self):
        assert BinopKind.NULLISH_COALESCE_CSHARP in VALID_BINOPS["csharp"]

    def test_go_has_chan_receive(self):
        assert UnopKind.CHAN_RECEIVE in VALID_UNOPS["go"]

    def test_pascal_has_mod_word(self):
        assert BinopKind.MOD_WORD in VALID_BINOPS["pascal"]


class TestLintOperators:
    """lint_operators detects invalid operators in emitted IR."""

    def test_valid_python_program_has_no_violations(self):
        from interpreter.constants import Language
        from interpreter.frontend import get_frontend

        frontend = get_frontend(Language("python"))
        instructions = frontend.lower(b"x = 1 + 2")
        violations = lint_operators(instructions, "python")
        assert violations == []

    def test_detects_violation_for_injected_invalid_binop(self):
        from interpreter.instructions import Binop
        from interpreter.register import Register

        # Lua concat in Python IR is invalid
        fake_ir = [
            Binop(
                result_reg=Register("%0"),
                operator=BinopKind.CONCAT_LUA,
                left=Register("%1"),
                right=Register("%2"),
            )
        ]
        violations = lint_operators(fake_ir, "python")
        assert len(violations) == 1
        assert violations[0].operator == BinopKind.CONCAT_LUA
        assert violations[0].kind == "binop"

    def test_detects_violation_for_injected_invalid_unop(self):
        from interpreter.instructions import Unop
        from interpreter.register import Register

        # Go channel receive in Python is invalid
        fake_ir = [
            Unop(
                result_reg=Register("%0"),
                operator=UnopKind.CHAN_RECEIVE,
                operand=Register("%1"),
            )
        ]
        violations = lint_operators(fake_ir, "python")
        assert len(violations) == 1
        assert violations[0].operator == UnopKind.CHAN_RECEIVE
        assert violations[0].kind == "unop"

    def test_no_violations_for_all_languages(self):
        """Compile a basic program per language and verify zero violations."""
        from interpreter.constants import Language
        from interpreter.frontend import get_frontend

        programs = {
            "python": "x = 1 + 2",
            "java": "class M { static int x = 1 + 2; }",
            "javascript": "let x = 1 + 2;",
            "typescript": "let x = 1 + 2;",
            "kotlin": "val x = 1 + 2",
            "ruby": "x = 1 + 2",
            "lua": "local x = 1 + 2",
            "go": "package main\nfunc main() { x := 1 + 2; _ = x }",
            "rust": "let x = 1 + 2;",
            "c": "int x = 1 + 2;",
            "cpp": "int x = 1 + 2;",
            "csharp": "class M { static int x = 1 + 2; }",
            "php": "<?php $x = 1 + 2;",
            "pascal": "program t; var x: integer; begin x := 1 + 2; end.",
            "scala": "val x = 1 + 2",
        }
        for lang_name, source in programs.items():
            frontend = get_frontend(Language(lang_name))
            instructions = frontend.lower(source.encode("utf-8"))
            violations = lint_operators(instructions, lang_name)
            assert (
                violations == []
            ), f"[{lang_name}] unexpected violations: {violations}"
