"""Tests for export table construction from IR + symbol tables."""

from pathlib import Path

import pytest

from interpreter.project.types import ExportTable
from interpreter.project.compiler import build_export_table
from interpreter.ir import IRInstruction, Opcode, CodeLabel
from interpreter.refs.func_ref import FuncRef
from interpreter.refs.class_ref import ClassRef
from interpreter.func_name import FuncName
from interpreter.class_name import ClassName


class TestBuildExportTable:
    def test_empty_ir(self):
        et = build_export_table([], {}, {})
        assert et.functions == {}
        assert et.classes == {}
        assert et.variables == {}

    def test_exports_functions(self):
        func_table = {
            "func_helper_0": FuncRef(
                name=FuncName("helper"), label=CodeLabel("func_helper_0")
            ),
            "func_main_2": FuncRef(
                name=FuncName("main"), label=CodeLabel("func_main_2")
            ),
        }
        et = build_export_table([], func_table, {})
        assert et.functions == {"helper": "func_helper_0", "main": "func_main_2"}

    def test_exports_classes(self):
        class_table = {
            "class_User_0": ClassRef(
                name=ClassName("User"), label=CodeLabel("class_User_0"), parents=()
            ),
        }
        et = build_export_table([], {}, class_table)
        assert et.classes == {"User": "class_User_0"}

    def test_exports_top_level_variables(self):
        """DECL_VAR or STORE_VAR at module level (before any func/class label) is exported."""
        ir = [
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
            IRInstruction(opcode=Opcode.CONST, result_reg="%0", operands=["3.14"]),
            IRInstruction(opcode=Opcode.STORE_VAR, operands=["PI", "%0"]),
        ]
        et = build_export_table(ir, {}, {})
        assert et.variables == {"PI": "%0"}

    def test_exports_top_level_decl_var(self):
        """DECL_VAR at module level is also exported."""
        ir = [
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
            IRInstruction(opcode=Opcode.CONST, result_reg="%0", operands=["3.14"]),
            IRInstruction(opcode=Opcode.DECL_VAR, operands=["PI", "%0"]),
        ]
        et = build_export_table(ir, {}, {})
        assert et.variables == {"PI": "%0"}

    def test_skips_variables_inside_functions(self):
        """STORE_VAR inside a function body is NOT exported."""
        ir = [
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("func_helper_0")),
            IRInstruction(opcode=Opcode.STORE_VAR, operands=["local_var", "%0"]),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("end_helper_1")),
        ]
        et = build_export_table(ir, {}, {})
        assert et.variables == {}

    def test_skips_variables_inside_classes(self):
        """STORE_VAR inside a class body is NOT exported."""
        ir = [
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("class_User_0")),
            IRInstruction(opcode=Opcode.STORE_VAR, operands=["field", "%0"]),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("end_class_User_1")),
        ]
        et = build_export_table(ir, {}, {})
        assert et.variables == {}

    def test_variable_after_function_is_exported(self):
        """STORE_VAR after end_func returns to module scope → exported."""
        ir = [
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("func_helper_0")),
            IRInstruction(opcode=Opcode.STORE_VAR, operands=["local", "%0"]),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("end_helper_1")),
            IRInstruction(opcode=Opcode.CONST, result_reg="%1", operands=["42"]),
            IRInstruction(opcode=Opcode.STORE_VAR, operands=["ANSWER", "%1"]),
        ]
        et = build_export_table(ir, {}, {})
        assert "ANSWER" in et.variables
        assert "local" not in et.variables

    def test_function_names_not_duplicated_as_variables(self):
        """If a function is in func_symbol_table, its DECL_VAR is not also in variables."""
        func_table = {
            "func_helper_0": FuncRef(
                name=FuncName("helper"), label=CodeLabel("func_helper_0")
            ),
        }
        ir = [
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("end_helper_1")),
            IRInstruction(opcode=Opcode.DECL_VAR, operands=["helper", "%0"]),
        ]
        et = build_export_table(ir, func_table, {})
        assert "helper" in et.functions
        assert "helper" not in et.variables

    def test_class_names_not_duplicated_as_variables(self):
        """If a class is in class_symbol_table, its DECL_VAR is not also in variables."""
        class_table = {
            "class_User_0": ClassRef(
                name=ClassName("User"), label=CodeLabel("class_User_0"), parents=()
            ),
        }
        ir = [
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("end_class_User_1")),
            IRInstruction(opcode=Opcode.DECL_VAR, operands=["User", "%0"]),
        ]
        et = build_export_table(ir, {}, class_table)
        assert "User" in et.classes
        assert "User" not in et.variables
