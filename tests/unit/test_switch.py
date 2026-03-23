"""Tests for switch/case lowering as if/else chains."""

from __future__ import annotations

from interpreter.frontends.c import CFrontend
from interpreter.frontends.cpp import CppFrontend
from interpreter.frontends.java import JavaFrontend
from interpreter.ir import IRInstruction, Opcode
from interpreter.parser import TreeSitterParserFactory


def _parse_and_lower(source: str, language: str, frontend) -> list[IRInstruction]:
    source_bytes = source.encode("utf-8")
    return frontend.lower(source_bytes)


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


def _labels(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label.value for inst in instructions if inst.opcode == Opcode.LABEL]


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
            CFrontend(TreeSitterParserFactory(), "c"),
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
            CFrontend(TreeSitterParserFactory(), "c"),
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
            CFrontend(TreeSitterParserFactory(), "c"),
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
            CFrontend(TreeSitterParserFactory(), "c"),
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
            CFrontend(TreeSitterParserFactory(), "c"),
        )
        # Should have BINOP == for case 1, unconditional BRANCH for default
        binops = _find_all(ir, Opcode.BINOP)
        eq_ops = [b for b in binops if "==" in b.operands]
        assert len(eq_ops) == 1
        # Default arm should store 99 into x
        decls = [s for s in _find_all(ir, Opcode.DECL_VAR) if "x" in s.operands]
        stores = [s for s in _find_all(ir, Opcode.STORE_VAR) if "x" in s.operands]
        consts = [c for c in _find_all(ir, Opcode.CONST) if "99" in c.operands]
        assert len(consts) == 1, "default arm should produce CONST 99"
        assert len(decls) == 1, "should have DECL_VAR for parameter x"
        assert (
            len(stores) == 2
        ), "should have STORE_VAR for case 1 (10) and default (99)"

    def test_empty_switch(self):
        ir = _parse_and_lower(
            """
            void f(int x) {
                switch (x) {
                }
            }
            """,
            "c",
            CFrontend(TreeSitterParserFactory(), "c"),
        )
        labels = _labels(ir)
        assert any("switch_end" in l for l in labels)
        # Empty switch should produce no case comparisons
        binops = _find_all(ir, Opcode.BINOP)
        eq_ops = [b for b in binops if "==" in b.operands]
        assert len(eq_ops) == 0, "empty switch should produce no case comparisons"


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
            CppFrontend(TreeSitterParserFactory(), "cpp"),
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
            JavaFrontend(TreeSitterParserFactory(), "java"),
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
            JavaFrontend(TreeSitterParserFactory(), "java"),
        )
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        switch_symbolics = [
            s for s in symbolics if any("switch" in str(o) for o in s.operands)
        ]
        assert len(switch_symbolics) == 0
