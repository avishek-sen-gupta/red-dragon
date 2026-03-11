"""Unit tests for P1 lowering gaps: PHP (3), Ruby (5)."""

from __future__ import annotations

from interpreter.frontends.php import PhpFrontend
from interpreter.frontends.ruby import RubyFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


# ── PHP: sequence_expression ─────────────────────────────────────


class TestPHPSequenceExpression:
    def test_sequence_no_symbolic(self):
        """$a = 1, $b = 2 in for should not produce SYMBOLIC."""
        frontend = PhpFrontend(TreeSitterParserFactory(), "php")
        ir = frontend.lower(
            b"<?php for ($i = 0, $j = 10; $i < 5; $i++, $j--) { $x = $i; } ?>"
        )
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "sequence_expression" in str(inst.operands) for inst in symbolics
        )


# ── PHP: include_once_expression ─────────────────────────────────


class TestPHPIncludeOnceExpression:
    def test_include_once_no_symbolic(self):
        """include_once should not produce SYMBOLIC fallthrough."""
        frontend = PhpFrontend(TreeSitterParserFactory(), "php")
        ir = frontend.lower(b"<?php include_once 'file.php'; ?>")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "include_once_expression" in str(inst.operands) for inst in symbolics
        )

    def test_include_once_produces_call(self):
        """include_once should emit a CALL_FUNCTION."""
        frontend = PhpFrontend(TreeSitterParserFactory(), "php")
        ir = frontend.lower(b"<?php include_once 'file.php'; ?>")
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("include_once" in inst.operands for inst in calls)


# ── PHP: require_expression ──────────────────────────────────────


class TestPHPRequireExpression:
    def test_require_no_symbolic(self):
        """require should not produce SYMBOLIC fallthrough."""
        frontend = PhpFrontend(TreeSitterParserFactory(), "php")
        ir = frontend.lower(b"<?php require 'file.php'; ?>")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("require_expression" in str(inst.operands) for inst in symbolics)

    def test_require_produces_call(self):
        """require should emit a CALL_FUNCTION."""
        frontend = PhpFrontend(TreeSitterParserFactory(), "php")
        ir = frontend.lower(b"<?php require 'file.php'; ?>")
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("require" in inst.operands for inst in calls)


# ── Ruby: splat_argument ─────────────────────────────────────────


class TestRubySplatArgument:
    def test_splat_argument_no_symbolic(self):
        """*args in method call should not produce SYMBOLIC."""
        frontend = RubyFrontend(TreeSitterParserFactory(), "ruby")
        ir = frontend.lower(b"arr = [1, 2, 3]\nfoo(*arr)")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("splat_argument" in str(inst.operands) for inst in symbolics)


# ── Ruby: hash_splat_argument ────────────────────────────────────


class TestRubyHashSplatArgument:
    def test_hash_splat_no_symbolic(self):
        """**opts in method call should not produce SYMBOLIC."""
        frontend = RubyFrontend(TreeSitterParserFactory(), "ruby")
        ir = frontend.lower(b"opts = {}\nfoo(**opts)")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "hash_splat_argument" in str(inst.operands) for inst in symbolics
        )


# ── Ruby: block_argument ─────────────────────────────────────────


class TestRubyBlockArgument:
    def test_block_argument_no_symbolic(self):
        """&block in method call should not produce SYMBOLIC."""
        frontend = RubyFrontend(TreeSitterParserFactory(), "ruby")
        ir = frontend.lower(b"blk = lambda { 1 }\nfoo(&blk)")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("block_argument" in str(inst.operands) for inst in symbolics)


# ── Ruby: begin_block / end_block ────────────────────────────────


class TestRubyBeginEndBlock:
    def test_begin_block_no_symbolic(self):
        """BEGIN { ... } should not produce SYMBOLIC."""
        frontend = RubyFrontend(TreeSitterParserFactory(), "ruby")
        ir = frontend.lower(b"BEGIN { x = 1 }\ny = 42")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("begin_block" in str(inst.operands) for inst in symbolics)

    def test_end_block_no_symbolic(self):
        """END { ... } should not produce SYMBOLIC."""
        frontend = RubyFrontend(TreeSitterParserFactory(), "ruby")
        ir = frontend.lower(b"END { x = 1 }\ny = 42")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("end_block" in str(inst.operands) for inst in symbolics)

    def test_begin_block_does_not_block(self):
        """Code after BEGIN block should still be lowered."""
        frontend = RubyFrontend(TreeSitterParserFactory(), "ruby")
        ir = frontend.lower(b"BEGIN { x = 1 }\ny = 42")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)

    def test_end_block_does_not_block(self):
        """Code after END block should still be lowered."""
        frontend = RubyFrontend(TreeSitterParserFactory(), "ruby")
        ir = frontend.lower(b"END { x = 1 }\ny = 42")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)
