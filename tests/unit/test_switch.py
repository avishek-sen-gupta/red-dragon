"""Tests for switch/case lowering as if/else chains."""

from __future__ import annotations

import tree_sitter_language_pack

from interpreter.frontends.c import CFrontend
from interpreter.frontends.cpp import CppFrontend
from interpreter.frontends.java import JavaFrontend
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


class TestCSwitchLowering:
    def test_switch_with_cases_produces_binop_eq(self):
        ir = _parse_and_lower(
            """
            void f(int x) {
                switch (x) {
                    case 1: return;
                    case 2: return;
                }
            }
            """,
            "c",
            CFrontend(),
        )
        binops = _find_all(ir, Opcode.BINOP)
        eq_ops = [b for b in binops if "==" in b.operands]
        assert len(eq_ops) == 2, "Each case should produce a BINOP =="

    def test_switch_produces_no_symbolic(self):
        ir = _parse_and_lower(
            """
            void f(int x) {
                switch (x) {
                    case 1: return;
                    default: return;
                }
            }
            """,
            "c",
            CFrontend(),
        )
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        switch_symbolics = [
            s for s in symbolics if any("switch" in str(o) for o in s.operands)
        ]
        assert len(switch_symbolics) == 0

    def test_switch_has_end_label(self):
        ir = _parse_and_lower(
            """
            void f(int x) {
                switch (x) {
                    case 1: return;
                }
            }
            """,
            "c",
            CFrontend(),
        )
        labels = _labels(ir)
        assert any("switch_end" in l for l in labels)

    def test_switch_break_branches_to_end(self):
        ir = _parse_and_lower(
            """
            void f(int x) {
                switch (x) {
                    case 1:
                        x = 10;
                        break;
                    case 2:
                        x = 20;
                        break;
                }
            }
            """,
            "c",
            CFrontend(),
        )
        labels = _labels(ir)
        branches = _branches(ir)
        end_labels = [l for l in labels if "switch_end" in l]
        assert len(end_labels) == 1
        # break inside switch should branch to switch_end
        assert end_labels[0] in branches

    def test_switch_with_default(self):
        ir = _parse_and_lower(
            """
            void f(int x) {
                switch (x) {
                    case 1:
                        x = 10;
                        break;
                    default:
                        x = 99;
                        break;
                }
            }
            """,
            "c",
            CFrontend(),
        )
        # Should have BINOP == for case 1, unconditional BRANCH for default
        binops = _find_all(ir, Opcode.BINOP)
        eq_ops = [b for b in binops if "==" in b.operands]
        assert len(eq_ops) == 1

    def test_empty_switch(self):
        ir = _parse_and_lower(
            """
            void f(int x) {
                switch (x) {
                }
            }
            """,
            "c",
            CFrontend(),
        )
        labels = _labels(ir)
        assert any("switch_end" in l for l in labels)


class TestCppSwitchInheritsC:
    def test_cpp_switch_produces_binop_eq(self):
        ir = _parse_and_lower(
            """
            void f(int x) {
                switch (x) {
                    case 1: return;
                    case 2: return;
                }
            }
            """,
            "cpp",
            CppFrontend(),
        )
        binops = _find_all(ir, Opcode.BINOP)
        eq_ops = [b for b in binops if "==" in b.operands]
        assert len(eq_ops) == 2


class TestJavaSwitchLowering:
    def test_java_switch_produces_binop_eq(self):
        ir = _parse_and_lower(
            """
            class T {
                void f(int x) {
                    switch (x) {
                        case 1:
                            System.out.println("one");
                            break;
                        case 2:
                            System.out.println("two");
                            break;
                    }
                }
            }
            """,
            "java",
            JavaFrontend(),
        )
        binops = _find_all(ir, Opcode.BINOP)
        eq_ops = [b for b in binops if "==" in b.operands]
        assert len(eq_ops) == 2

    def test_java_switch_no_symbolic(self):
        ir = _parse_and_lower(
            """
            class T {
                void f(int x) {
                    switch (x) {
                        case 1:
                            break;
                        default:
                            break;
                    }
                }
            }
            """,
            "java",
            JavaFrontend(),
        )
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        switch_symbolics = [
            s for s in symbolics if any("switch" in str(o) for o in s.operands)
        ]
        assert len(switch_symbolics) == 0
