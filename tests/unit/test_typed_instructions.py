"""Tests for typed instruction classes.

Verifies that ``inst`` produces correct typed instructions
from flat IRInstruction objects, and that ``str(typed)`` matches the
original ``str(inst)`` output.
"""

from __future__ import annotations

from interpreter.register import Register

import pytest

from interpreter.ir import (
    CodeLabel,
    IRInstruction,
    NO_LABEL,
    NO_SOURCE_LOCATION,
    Opcode,
    SourceLocation,
    SpreadArguments,
)
from interpreter.instructions import InstructionBase
from interpreter.field_name import FieldName
from interpreter.register import NO_REGISTER, Register


def _loc() -> SourceLocation:
    return SourceLocation(start_line=1, start_col=0, end_line=1, end_col=10)


# ── Helper: to_typed assertion ─────────────────────────────────


def _assert_to_typed(inst: InstructionBase) -> None:
    """Assert flat → typed produces a correct instruction with matching str."""

    typed = inst
    # Typed instruction must expose the correct opcode
    assert typed.opcode == inst.opcode
    # str() output must match
    assert str(typed) == str(inst)


# ── Variables & Constants ────────────────────────────────────────


class TestConstToTyped:
    def test_string_literal(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.CONST,
                result_reg="%0",
                operands=['"hello"'],
                source_location=_loc(),
            )
        )

    def test_numeric_literal(self):
        _assert_to_typed(
            IRInstruction(opcode=Opcode.CONST, result_reg="%1", operands=["42"])
        )

    def test_boolean_literal(self):
        _assert_to_typed(
            IRInstruction(opcode=Opcode.CONST, result_reg="%2", operands=["True"])
        )

    def test_none_literal(self):
        _assert_to_typed(
            IRInstruction(opcode=Opcode.CONST, result_reg="%3", operands=["None"])
        )

    def test_no_operands(self):
        _assert_to_typed(
            IRInstruction(opcode=Opcode.CONST, result_reg="%4", operands=[])
        )


class TestLoadVarToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(opcode=Opcode.LOAD_VAR, result_reg="%0", operands=["x"])
        )

    def test_this(self):
        _assert_to_typed(
            IRInstruction(opcode=Opcode.LOAD_VAR, result_reg="%1", operands=["this"])
        )


class TestDeclVarToTyped:
    def test_basic(self):
        _assert_to_typed(IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%0"]))


class TestStoreVarToTyped:
    def test_basic(self):
        _assert_to_typed(IRInstruction(opcode=Opcode.STORE_VAR, operands=["y", "%1"]))


class TestSymbolicToTyped:
    def test_param(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.SYMBOLIC,
                result_reg="%0",
                operands=["__param__x"],
            )
        )

    def test_empty_hint(self):
        _assert_to_typed(
            IRInstruction(opcode=Opcode.SYMBOLIC, result_reg="%1", operands=[])
        )


# ── Arithmetic ───────────────────────────────────────────────────


class TestBinopToTyped:
    def test_add(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.BINOP,
                result_reg="%2",
                operands=["+", "%0", "%1"],
            )
        )

    def test_comparison(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.BINOP,
                result_reg="%3",
                operands=[">=", "%0", "%1"],
            )
        )


class TestUnopToTyped:
    def test_negate(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.UNOP,
                result_reg="%1",
                operands=["!", "%0"],
            )
        )


# ── Calls ────────────────────────────────────────────────────────


class TestCallFunctionToTyped:
    def test_no_args(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg="%0",
                operands=["print"],
            )
        )

    def test_with_args(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg="%2",
                operands=["add", "%0", "%1"],
            )
        )

    def test_with_spread(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg="%3",
                operands=["f", "%0", SpreadArguments(register="%1")],
            )
        )


class TestCallMethodToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.CALL_METHOD,
                result_reg="%2",
                operands=["%0", "length"],
            )
        )

    def test_with_args(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.CALL_METHOD,
                result_reg="%3",
                operands=["%0", "push", "%1", "%2"],
            )
        )


class TestCallUnknownToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.CALL_UNKNOWN,
                result_reg="%1",
                operands=["%0"],
            )
        )

    def test_with_args(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.CALL_UNKNOWN,
                result_reg="%3",
                operands=["%0", "%1", "%2"],
            )
        )


# ── Memory — Fields ──────────────────────────────────────────────


class TestLoadFieldToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.LOAD_FIELD,
                result_reg="%1",
                operands=["%0", "name"],
            )
        )


class TestStoreFieldToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.STORE_FIELD,
                operands=["%0", "count", "%1"],
            )
        )


class TestLoadFieldIndirectToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.LOAD_FIELD_INDIRECT,
                result_reg="%2",
                operands=["%0", "%1"],
            )
        )


# ── Memory — Indexing ────────────────────────────────────────────


class TestLoadIndexToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.LOAD_INDEX,
                result_reg="%2",
                operands=["%0", "%1"],
            )
        )


class TestStoreIndexToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.STORE_INDEX,
                operands=["%0", "%1", "%2"],
            )
        )


# ── Memory — Pointers ────────────────────────────────────────────


class TestLoadIndirectToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.LOAD_INDIRECT,
                result_reg="%1",
                operands=["%0"],
            )
        )


class TestStoreIndirectToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.STORE_INDIRECT,
                operands=["%0", "%1"],
            )
        )


class TestAddressOfToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.ADDRESS_OF,
                result_reg="%1",
                operands=["x"],
            )
        )


# ── Objects ──────────────────────────────────────────────────────


class TestNewObjectToTyped:
    def test_with_type(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.NEW_OBJECT,
                result_reg="%0",
                operands=["Foo"],
            )
        )

    def test_empty_type(self):
        _assert_to_typed(
            IRInstruction(opcode=Opcode.NEW_OBJECT, result_reg="%0", operands=[])
        )


class TestNewArrayToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.NEW_ARRAY,
                result_reg="%1",
                operands=["list", "%0"],
            )
        )


# ── Control Flow ─────────────────────────────────────────────────


class TestLabelToTyped:
    def test_basic(self):
        _assert_to_typed(IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")))


class TestBranchToTyped:
    def test_basic(self):
        _assert_to_typed(IRInstruction(opcode=Opcode.BRANCH, label=CodeLabel("L_1")))


class TestBranchIfToTyped:
    def test_two_targets(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.BRANCH_IF,
                operands=["%0"],
                branch_targets=[CodeLabel("L_true"), CodeLabel("L_false")],
            )
        )


class TestReturnToTyped:
    def test_with_value(self):
        _assert_to_typed(IRInstruction(opcode=Opcode.RETURN, operands=["%0"]))

    def test_void(self):
        _assert_to_typed(IRInstruction(opcode=Opcode.RETURN, operands=[]))


class TestThrowToTyped:
    def test_with_value(self):
        _assert_to_typed(IRInstruction(opcode=Opcode.THROW, operands=["%0"]))

    def test_bare(self):
        _assert_to_typed(IRInstruction(opcode=Opcode.THROW, operands=[]))


# ── Exceptions ───────────────────────────────────────────────────


class TestTryPushToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.TRY_PUSH,
                operands=[
                    [CodeLabel("catch_0")],
                    CodeLabel("finally_0"),
                    CodeLabel("end_try"),
                ],
            )
        )

    def test_multiple_catch(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.TRY_PUSH,
                operands=[
                    [CodeLabel("catch_0"), CodeLabel("catch_1")],
                    NO_LABEL,
                    CodeLabel("end_try"),
                ],
            )
        )


class TestTryPopToTyped:
    def test_basic(self):
        _assert_to_typed(IRInstruction(opcode=Opcode.TRY_POP))


# ── Regions ──────────────────────────────────────────────────────


class TestAllocRegionToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg="%1",
                operands=["%0"],
            )
        )


class TestLoadRegionToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%2",
                operands=["%0", "%1", 8],
            )
        )


class TestWriteRegionToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%0", "%1", 8, "%2"],
            )
        )


# ── Continuations ────────────────────────────────────────────────


class TestSetContinuationToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.SET_CONTINUATION,
                operands=["__cont", CodeLabel("L_resume")],
            )
        )


class TestResumeContinuationToTyped:
    def test_basic(self):
        _assert_to_typed(
            IRInstruction(
                opcode=Opcode.RESUME_CONTINUATION,
                operands=["__cont"],
            )
        )


# ── Typed field access ───────────────────────────────────────────


class TestTypedFieldAccess:
    """Verify that typed instructions expose named fields, not positional operands."""

    def test_binop_fields(self):

        inst = IRInstruction(
            opcode=Opcode.BINOP,
            result_reg="%2",
            operands=["+", "%0", "%1"],
        )
        typed = inst
        assert typed.operator == "+"
        assert typed.left == Register("%0")
        assert typed.right == Register("%1")
        assert typed.result_reg == Register("%2")

    def test_call_function_fields(self):

        inst = IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg="%3",
            operands=["add", "%0", "%1"],
        )
        typed = inst
        assert typed.func_name == "add"
        assert typed.args == (Register("%0"), Register("%1"))

    def test_store_field_fields(self):

        inst = IRInstruction(
            opcode=Opcode.STORE_FIELD,
            operands=["%0", "count", "%1"],
        )
        typed = inst
        assert typed.obj_reg == Register("%0")
        assert typed.field_name == FieldName("count")
        assert typed.value_reg == Register("%1")

    def test_branch_if_fields(self):

        inst = IRInstruction(
            opcode=Opcode.BRANCH_IF,
            operands=["%0"],
            branch_targets=[CodeLabel("L_true"), CodeLabel("L_false")],
        )
        typed = inst
        assert typed.cond_reg == Register("%0")
        assert typed.branch_targets == (CodeLabel("L_true"), CodeLabel("L_false"))

    def test_write_region_length_is_int(self):

        inst = IRInstruction(
            opcode=Opcode.WRITE_REGION,
            operands=["%0", "%1", 8, "%2"],
        )
        typed = inst
        assert typed.length == 8
        assert isinstance(typed.length, int)

    def test_return_void_has_none_value_reg(self):

        inst = IRInstruction(opcode=Opcode.RETURN, operands=[])
        typed = inst
        assert typed.value_reg is None

    def test_return_with_value(self):

        inst = IRInstruction(opcode=Opcode.RETURN, operands=["%0"])
        typed = inst
        assert typed.value_reg == Register("%0")
