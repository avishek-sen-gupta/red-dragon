"""Unit tests for PHP P1 lowering gaps: error_suppression_expression, exit_statement, declare_statement, unset_statement."""

from __future__ import annotations

from interpreter.frontends.php import PhpFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_php(source: str) -> list[IRInstruction]:
    frontend = PhpFrontend(TreeSitterParserFactory(), "php")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestPhpErrorSuppression:
    def test_error_suppression_no_symbolic(self):
        """@expr should not produce SYMBOLIC fallthrough."""
        ir = _parse_php("<?php $x = @strlen('hello'); ?>")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "error_suppression_expression" in str(inst.operands) for inst in symbolics
        )

    def test_error_suppression_lowers_inner_call(self):
        """@strlen('hello') should still emit a CALL_FUNCTION for strlen."""
        ir = _parse_php("<?php $x = @strlen('hello'); ?>")
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("strlen" in str(inst.operands) for inst in calls)


class TestPhpExitStatement:
    def test_exit_no_symbolic(self):
        """exit(0) should not produce SYMBOLIC fallthrough."""
        ir = _parse_php("<?php exit(0); ?>")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("exit_statement" in str(inst.operands) for inst in symbolics)


class TestPhpDeclareStatement:
    def test_declare_no_symbolic(self):
        """declare(strict_types=1) should not produce SYMBOLIC fallthrough."""
        ir = _parse_php("<?php declare(strict_types=1); ?>")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("declare_statement" in str(inst.operands) for inst in symbolics)


class TestPhpUnsetStatement:
    def test_unset_no_symbolic(self):
        """unset($x) should not produce SYMBOLIC fallthrough."""
        ir = _parse_php("<?php $x = 1; unset($x); ?>")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unset_statement" in str(inst.operands) for inst in symbolics)
