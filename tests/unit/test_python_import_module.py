"""Tests for Python frontend emitting IMPORT_MODULE instructions."""

from __future__ import annotations

from interpreter.frontends.python import PythonFrontend
from interpreter.frontends.python.features import PythonFeature
from interpreter.instructions import ImportModule, InstructionBase
from interpreter.ir import Opcode
from interpreter.parser import TreeSitterParserFactory
from tests.covers import covers


def _lower(source: str) -> list[InstructionBase]:
    frontend = PythonFrontend(TreeSitterParserFactory(), "python")
    return frontend.lower(source.encode())


class TestPythonImportEmitsImportModule:
    @covers(PythonFeature.IMPORT)
    def test_import_os(self):
        ir = _lower("import os\n")
        import_insts = [i for i in ir if isinstance(i, ImportModule)]
        assert len(import_insts) == 1
        assert import_insts[0].module_path == "os"

    @covers(PythonFeature.IMPORT)
    def test_import_dotted(self):
        ir = _lower("import os.path\n")
        import_insts = [i for i in ir if isinstance(i, ImportModule)]
        assert len(import_insts) == 1
        assert import_insts[0].module_path == "os.path"

    @covers(PythonFeature.IMPORT)
    def test_import_stores_variable(self):
        """import os should also emit DECL_VAR for 'os'."""
        ir = _lower("import os\n")
        decl_vars = [i for i in ir if i.opcode == Opcode.DECL_VAR]
        names = [str(i.name) for i in decl_vars]
        assert "os" in names

    @covers(PythonFeature.IMPORT)
    def test_from_import(self):
        ir = _lower("from os import path\n")
        import_insts = [i for i in ir if isinstance(i, ImportModule)]
        assert len(import_insts) == 1
        assert import_insts[0].module_path == "os"

    @covers(PythonFeature.IMPORT)
    def test_from_import_load_field(self):
        """from os import path should emit IMPORT_MODULE + LOAD_FIELD + DECL_VAR."""
        ir = _lower("from os import path\n")
        opcodes = [i.opcode for i in ir]
        assert Opcode.IMPORT_MODULE in opcodes
        assert Opcode.LOAD_FIELD in opcodes

    @covers(PythonFeature.IMPORT)
    def test_from_import_multiple_names(self):
        ir = _lower("from os import path, getcwd\n")
        import_insts = [i for i in ir if isinstance(i, ImportModule)]
        # One IMPORT_MODULE for the module, then LOAD_FIELD per name
        assert len(import_insts) == 1
        load_fields = [i for i in ir if i.opcode == Opcode.LOAD_FIELD]
        assert len(load_fields) == 2
