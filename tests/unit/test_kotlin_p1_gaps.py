"""Unit tests for Kotlin P1 lowering gap handlers: unsigned_literal, wildcard_import, callable_reference, spread_expression."""

from __future__ import annotations

from interpreter.frontends.kotlin import KotlinFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_kotlin(source: str) -> list[IRInstruction]:
    frontend = KotlinFrontend(TreeSitterParserFactory(), "kotlin")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestKotlinUnsignedLiteral:
    def test_unsigned_literal_no_symbolic(self):
        """42u should not produce SYMBOLIC fallthrough."""
        ir = _parse_kotlin("val x = 42u")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsigned_literal" in str(inst.operands) for inst in symbolics)

    def test_unsigned_literal_emits_const(self):
        """Unsigned literal should emit a CONST instruction."""
        ir = _parse_kotlin("val x = 42u")
        consts = _find_all(ir, Opcode.CONST)
        assert len(consts) >= 1

    def test_unsigned_literal_stored(self):
        """Unsigned literal should be stored in a variable."""
        ir = _parse_kotlin("val x = 42u")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestKotlinWildcardImport:
    def test_wildcard_import_no_symbolic(self):
        """import foo.* should not produce SYMBOLIC fallthrough."""
        ir = _parse_kotlin("import kotlin.math.*\nval x = 1")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("wildcard_import" in str(inst.operands) for inst in symbolics)


class TestKotlinCallableReference:
    def test_callable_reference_no_symbolic(self):
        """::println should not produce SYMBOLIC fallthrough."""
        ir = _parse_kotlin("val f = ::println")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("callable_reference" in str(inst.operands) for inst in symbolics)

    def test_callable_reference_emits_load(self):
        """::functionName should emit a LOAD_VAR for the referenced function."""
        ir = _parse_kotlin("val f = ::println")
        loads = _find_all(ir, Opcode.LOAD_VAR)
        assert any("println" in str(inst.operands) for inst in loads)


class TestKotlinSpreadExpression:
    def test_spread_no_symbolic(self):
        """*array should not produce SYMBOLIC fallthrough."""
        ir = _parse_kotlin("""\
val arr = listOf(1, 2, 3)
val x = listOf(*arr)
""")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("spread_expression" in str(inst.operands) for inst in symbolics)
