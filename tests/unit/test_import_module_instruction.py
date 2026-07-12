"""Tests for ImportModule instruction class."""

import pytest

from interpreter.instructions import ImportModule
from interpreter.ir import Opcode
from interpreter.path_name import NO_PATH_NAME, PathName
from interpreter.register import Register


class TestImportModuleInstruction:
    def test_opcode(self):
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="./utils",
            resolved_path=PathName("/project/utils.py"),
        )
        assert inst.opcode == Opcode.IMPORT_MODULE

    def test_operands(self):
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="os",
            resolved_path=NO_PATH_NAME,
        )
        assert inst.operands == ["os", str(NO_PATH_NAME)]

    def test_operands_with_resolved(self):
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="./utils",
            resolved_path=PathName("/project/utils.py"),
        )
        assert inst.operands == ["./utils", "/project/utils.py"]

    def test_frozen(self):
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="os",
            resolved_path=NO_PATH_NAME,
        )
        with pytest.raises(AttributeError):
            inst.module_path = "sys"  # type: ignore[misc]

    def test_map_registers(self):
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="os",
            resolved_path=NO_PATH_NAME,
        )
        mapped = inst.map_registers(lambda r: r.rebase(10))
        assert str(mapped.result_reg) == "%10"

    def test_str_representation(self):
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="./utils",
            resolved_path=PathName("/project/utils.py"),
        )
        s = str(inst)
        assert "import_module" in s
        assert "./utils" in s
