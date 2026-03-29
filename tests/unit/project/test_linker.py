"""Tests for the linker — namespace, rebase, rewrite, merge."""

from pathlib import Path

import pytest

from interpreter.project.types import ExportTable, ImportRef, ModuleUnit
from interpreter.project.linker import (
    module_prefix,
    namespace_label,
    rebase_register,
    max_register_number,
)
from interpreter.constants import Language
from interpreter.ir import IRInstruction, Opcode, CodeLabel
from interpreter.register import Register

# ── module_prefix ────────────────────────────────────────────────


class TestModulePrefix:
    def test_simple_file(self):
        assert module_prefix(Path("/project/main.py"), Path("/project")) == "main"

    def test_nested_file(self):
        assert (
            module_prefix(Path("/project/src/utils.py"), Path("/project"))
            == "src.utils"
        )

    def test_deeply_nested(self):
        assert (
            module_prefix(Path("/project/pkg/sub/helpers.py"), Path("/project"))
            == "pkg.sub.helpers"
        )

    def test_strips_extension(self):
        assert module_prefix(Path("/project/mod.rs"), Path("/project")) == "mod"

    def test_java_path(self):
        assert (
            module_prefix(Path("/project/com/example/Utils.java"), Path("/project"))
            == "com.example.Utils"
        )


# ── namespace_label ──────────────────────────────────────────────


class TestNamespaceLabel:
    def test_prefixes_label(self):
        assert (
            namespace_label("func_helper_0", "src.utils") == "src.utils.func_helper_0"
        )

    def test_branch_targets(self):
        assert namespace_label("if_true_3", "main") == "main.if_true_3"

    def test_entry_label(self):
        assert namespace_label("entry", "main") == "main.entry"


# ── rebase_register ──────────────────────────────────────────────


class TestRebaseRegister:
    def test_simple_rebase(self):
        assert rebase_register("%0", 100) == "%100"

    def test_higher_number(self):
        assert rebase_register("%47", 100) == "%147"

    def test_zero_offset(self):
        assert rebase_register("%5", 0) == "%5"

    def test_non_register_unchanged(self):
        """Non-register strings pass through unchanged."""
        assert rebase_register("helper", 100) == "helper"
        assert rebase_register("func_helper_0", 100) == "func_helper_0"

    def test_negative_numbers_safe(self):
        """Negative numbers in operands shouldn't match register pattern."""
        assert rebase_register("-1", 100) == "-1"


# ── max_register_number ─────────────────────────────────────────


class TestMaxRegisterNumber:
    def test_empty_ir(self):
        assert max_register_number(()) == -1

    def test_single_instruction(self):
        ir = (
            IRInstruction(
                opcode=Opcode.CONST, result_reg=Register("%0"), operands=["42"]
            ),
        )
        assert max_register_number(ir) == 0

    def test_multiple_instructions(self):
        ir = (
            IRInstruction(
                opcode=Opcode.CONST, result_reg=Register("%0"), operands=["42"]
            ),
            IRInstruction(
                opcode=Opcode.CONST, result_reg=Register("%5"), operands=["99"]
            ),
            IRInstruction(
                opcode=Opcode.BINOP,
                result_reg=Register("%3"),
                operands=["+", "%0", "%5"],
            ),
        )
        assert max_register_number(ir) == 5

    def test_registers_in_operands(self):
        ir = (IRInstruction(opcode=Opcode.STORE_VAR, operands=["x", "%12"]),)
        assert max_register_number(ir) == 12

    def test_no_registers(self):
        ir = (IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),)
        assert max_register_number(ir) == -1
