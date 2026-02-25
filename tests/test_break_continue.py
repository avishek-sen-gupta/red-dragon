"""Tests for break/continue lowering across language frontends."""

from __future__ import annotations

import pytest
import tree_sitter_language_pack

from interpreter.frontends.c import CFrontend
from interpreter.frontends.cpp import CppFrontend
from interpreter.frontends.javascript import JavaScriptFrontend
from interpreter.frontends.java import JavaFrontend
from interpreter.frontends.go import GoFrontend
from interpreter.frontends.rust import RustFrontend
from interpreter.frontends.ruby import RubyFrontend
from interpreter.frontends.lua import LuaFrontend
from interpreter.frontends.php import PhpFrontend
from interpreter.frontends.kotlin import KotlinFrontend
from interpreter.frontends.csharp import CSharpFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_and_lower(source: str, language: str, frontend) -> list[IRInstruction]:
    parser = tree_sitter_language_pack.get_parser(language)
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    return frontend.lower(tree, source_bytes)


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


def _labels(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


def _branches(instructions: list[IRInstruction]) -> list[str]:
    return [
        inst.label
        for inst in instructions
        if inst.opcode == Opcode.BRANCH and inst.label
    ]


class TestBreakInWhileLoop:
    def test_c_break_in_while(self):
        ir = _parse_and_lower(
            "void f() { while (x) { break; } }",
            "c",
            CFrontend(),
        )
        branches = _branches(ir)
        labels = _labels(ir)
        # break should produce a BRANCH to the while_end label
        end_labels = [l for l in labels if "while_end" in l]
        assert len(end_labels) == 1
        assert end_labels[0] in branches

    def test_c_continue_in_while(self):
        ir = _parse_and_lower(
            "void f() { while (x) { continue; } }",
            "c",
            CFrontend(),
        )
        branches = _branches(ir)
        labels = _labels(ir)
        # continue should produce a BRANCH to the while_cond label
        cond_labels = [l for l in labels if "while_cond" in l]
        assert len(cond_labels) == 1
        assert cond_labels[0] in branches

    def test_no_symbolic_for_break(self):
        ir = _parse_and_lower(
            "void f() { while (x) { break; } }",
            "c",
            CFrontend(),
        )
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        break_symbolics = [
            s for s in symbolics if any("break" in str(o) for o in s.operands)
        ]
        assert len(break_symbolics) == 0

    def test_no_symbolic_for_continue(self):
        ir = _parse_and_lower(
            "void f() { while (x) { continue; } }",
            "c",
            CFrontend(),
        )
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        continue_symbolics = [
            s for s in symbolics if any("continue" in str(o) for o in s.operands)
        ]
        assert len(continue_symbolics) == 0


class TestBreakInForLoop:
    def test_c_break_in_for(self):
        ir = _parse_and_lower(
            "void f() { for (int i = 0; i < 10; i++) { break; } }",
            "c",
            CFrontend(),
        )
        branches = _branches(ir)
        labels = _labels(ir)
        end_labels = [l for l in labels if "for_end" in l]
        assert len(end_labels) == 1
        assert end_labels[0] in branches

    def test_c_continue_in_for_jumps_to_update(self):
        ir = _parse_and_lower(
            "void f() { for (int i = 0; i < 10; i++) { continue; } }",
            "c",
            CFrontend(),
        )
        branches = _branches(ir)
        labels = _labels(ir)
        # continue should jump to the update label, not the condition
        update_labels = [l for l in labels if "for_update" in l]
        assert len(update_labels) == 1
        assert update_labels[0] in branches


class TestBreakInDoWhile:
    def test_c_break_in_do_while(self):
        ir = _parse_and_lower(
            "void f() { do { break; } while (x); }",
            "c",
            CFrontend(),
        )
        branches = _branches(ir)
        labels = _labels(ir)
        end_labels = [l for l in labels if "do_end" in l]
        assert len(end_labels) == 1
        assert end_labels[0] in branches

    def test_c_continue_in_do_while(self):
        ir = _parse_and_lower(
            "void f() { do { continue; } while (x); }",
            "c",
            CFrontend(),
        )
        branches = _branches(ir)
        labels = _labels(ir)
        # continue in do-while jumps to the condition
        cond_labels = [l for l in labels if "do_cond" in l]
        assert len(cond_labels) == 1
        assert cond_labels[0] in branches


class TestNestedLoops:
    def test_inner_break_targets_inner_loop(self):
        ir = _parse_and_lower(
            "void f() { while (a) { while (b) { break; } } }",
            "c",
            CFrontend(),
        )
        labels = _labels(ir)
        branches = _branches(ir)
        # There should be two while_end labels
        end_labels = [l for l in labels if "while_end" in l]
        assert len(end_labels) == 2
        # The break emits a BRANCH to the inner while_end (while_end_7)
        # The inner loop's end label appears first in instructions
        inner_end = end_labels[0]
        assert inner_end in branches

    def test_inner_continue_targets_inner_loop(self):
        ir = _parse_and_lower(
            "void f() { while (a) { while (b) { continue; } } }",
            "c",
            CFrontend(),
        )
        labels = _labels(ir)
        branches = _branches(ir)
        cond_labels = [l for l in labels if "while_cond" in l]
        assert len(cond_labels) == 2
        # The continue should target the inner (second) while_cond
        assert cond_labels[1] in branches


class TestBreakOutsideLoop:
    def test_break_outside_loop_emits_symbolic(self):
        ir = _parse_and_lower(
            "void f() { break; }",
            "c",
            CFrontend(),
        )
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert any("break_outside_loop_or_switch" in str(s.operands) for s in symbolics)

    def test_continue_outside_loop_emits_symbolic(self):
        ir = _parse_and_lower(
            "void f() { continue; }",
            "c",
            CFrontend(),
        )
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert any("continue_outside_loop" in str(s.operands) for s in symbolics)


class TestBreakContinueMultipleLanguages:
    """Parametrized tests across languages that support break/continue in while loops."""

    @pytest.mark.parametrize(
        "lang,frontend,source",
        [
            ("c", CFrontend(), "void f() { while (x) { break; } }"),
            ("cpp", CppFrontend(), "void f() { while (x) { break; } }"),
            (
                "javascript",
                JavaScriptFrontend(),
                "function f() { while (x) { break; } }",
            ),
            (
                "java",
                JavaFrontend(),
                "class T { void f() { while (x) { break; } } }",
            ),
            ("go", GoFrontend(), "package main\nfunc f() { for x { break } }"),
            (
                "php",
                PhpFrontend(),
                "<?php while ($x) { break; } ?>",
            ),
        ],
    )
    def test_break_emits_branch_not_symbolic(self, lang, frontend, source):
        ir = _parse_and_lower(source, lang, frontend)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        break_symbolics = [
            s for s in symbolics if any("break" in str(o) for o in s.operands)
        ]
        assert (
            len(break_symbolics) == 0
        ), f"{lang}: break should not produce SYMBOLIC, got {break_symbolics}"
        branches = _branches(ir)
        assert len(branches) > 0, f"{lang}: break should produce BRANCH instructions"

    @pytest.mark.parametrize(
        "lang,frontend,source",
        [
            ("c", CFrontend(), "void f() { while (x) { continue; } }"),
            ("cpp", CppFrontend(), "void f() { while (x) { continue; } }"),
            (
                "javascript",
                JavaScriptFrontend(),
                "function f() { while (x) { continue; } }",
            ),
            (
                "java",
                JavaFrontend(),
                "class T { void f() { while (x) { continue; } } }",
            ),
            ("go", GoFrontend(), "package main\nfunc f() { for x { continue } }"),
            (
                "php",
                PhpFrontend(),
                "<?php while ($x) { continue; } ?>",
            ),
        ],
    )
    def test_continue_emits_branch_not_symbolic(self, lang, frontend, source):
        ir = _parse_and_lower(source, lang, frontend)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        continue_symbolics = [
            s for s in symbolics if any("continue" in str(o) for o in s.operands)
        ]
        assert (
            len(continue_symbolics) == 0
        ), f"{lang}: continue should not produce SYMBOLIC, got {continue_symbolics}"


class TestRubyBreakNext:
    def test_ruby_break_in_while(self):
        ir = _parse_and_lower(
            "while x\n  break\nend",
            "ruby",
            RubyFrontend(),
        )
        branches = _branches(ir)
        labels = _labels(ir)
        end_labels = [l for l in labels if "while_end" in l]
        assert len(end_labels) == 1
        assert end_labels[0] in branches

    def test_ruby_next_in_while(self):
        ir = _parse_and_lower(
            "while x\n  next\nend",
            "ruby",
            RubyFrontend(),
        )
        branches = _branches(ir)
        labels = _labels(ir)
        cond_labels = [l for l in labels if "while_cond" in l]
        assert len(cond_labels) == 1
        assert cond_labels[0] in branches


class TestLuaBreak:
    def test_lua_break_in_while(self):
        ir = _parse_and_lower(
            "while x do\n  break\nend",
            "lua",
            LuaFrontend(),
        )
        branches = _branches(ir)
        labels = _labels(ir)
        end_labels = [l for l in labels if "while_end" in l]
        assert len(end_labels) == 1
        assert end_labels[0] in branches


class TestRustBreakContinue:
    def test_rust_break_in_loop(self):
        ir = _parse_and_lower(
            "fn f() { loop { break; } }",
            "rust",
            RustFrontend(),
        )
        branches = _branches(ir)
        labels = _labels(ir)
        end_labels = [l for l in labels if "loop_end" in l]
        assert len(end_labels) == 1
        assert end_labels[0] in branches

    def test_rust_continue_in_loop(self):
        ir = _parse_and_lower(
            "fn f() { loop { continue; } }",
            "rust",
            RustFrontend(),
        )
        branches = _branches(ir)
        labels = _labels(ir)
        top_labels = [l for l in labels if "loop_top" in l]
        assert len(top_labels) == 1
        assert top_labels[0] in branches


class TestKotlinBreakContinue:
    def test_kotlin_break_in_while(self):
        ir = _parse_and_lower(
            "fun f() { while (x) { break } }",
            "kotlin",
            KotlinFrontend(),
        )
        branches = _branches(ir)
        labels = _labels(ir)
        end_labels = [l for l in labels if "while_end" in l]
        assert len(end_labels) == 1
        assert end_labels[0] in branches

    def test_kotlin_continue_in_while(self):
        ir = _parse_and_lower(
            "fun f() { while (x) { continue } }",
            "kotlin",
            KotlinFrontend(),
        )
        branches = _branches(ir)
        labels = _labels(ir)
        cond_labels = [l for l in labels if "while_cond" in l]
        assert len(cond_labels) == 1
        assert cond_labels[0] in branches
