"""Unit tests for miscellaneous P1 lowering gaps: C linkage_specification, Python future_import_statement, Scala export_declaration."""

from __future__ import annotations

from interpreter.frontends.c import CFrontend
from interpreter.frontends.python import PythonFrontend
from interpreter.frontends.scala import ScalaFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestCLinkageSpecification:
    def test_linkage_spec_no_symbolic(self):
        """extern 'C' { ... } should not produce SYMBOLIC fallthrough."""
        frontend = CFrontend(TreeSitterParserFactory(), "c")
        ir = frontend.lower(b'extern "C" { int foo(); }')
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "linkage_specification" in str(inst.operands) for inst in symbolics
        )

    def test_linkage_spec_body_lowered(self):
        """Declarations inside extern 'C' should still be lowered."""
        frontend = CFrontend(TreeSitterParserFactory(), "c")
        ir = frontend.lower(b'extern "C" { int x = 42; }')
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestPythonFutureImportStatement:
    def test_future_import_no_symbolic(self):
        """from __future__ import annotations should not produce SYMBOLIC."""
        frontend = PythonFrontend(TreeSitterParserFactory(), "python")
        ir = frontend.lower(b"from __future__ import annotations\nx = 42")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "future_import_statement" in str(inst.operands) for inst in symbolics
        )

    def test_future_import_does_not_block(self):
        """Code after future import should still execute."""
        frontend = PythonFrontend(TreeSitterParserFactory(), "python")
        ir = frontend.lower(b"from __future__ import annotations\nx = 42")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestScalaExportDeclaration:
    def test_export_no_symbolic(self):
        """export foo._ should not produce SYMBOLIC fallthrough."""
        frontend = ScalaFrontend(TreeSitterParserFactory(), "scala")
        ir = frontend.lower(b"export foo._\nval x = 42")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("export_declaration" in str(inst.operands) for inst in symbolics)

    def test_export_does_not_block(self):
        """Code after export should still be lowered."""
        frontend = ScalaFrontend(TreeSitterParserFactory(), "scala")
        ir = frontend.lower(b"export foo._\nval x = 42")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
