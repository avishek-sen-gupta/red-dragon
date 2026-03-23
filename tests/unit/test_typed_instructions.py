"""Round-trip tests for typed instruction classes.

Every instruction that the frontends and COBOL emitter produce must survive
``to_typed(inst).to_flat()`` losslessly.  These tests define the contract
before the implementation exists.
"""

from __future__ import annotations

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
from interpreter.register import NO_REGISTER, Register


def _loc() -> SourceLocation:
    return SourceLocation(start_line=1, start_col=0, end_line=1, end_col=10)


# ── Helper: round-trip assertion ─────────────────────────────────


def _assert_round_trip(inst: IRInstruction) -> None:
    """Assert flat → typed → flat produces an equivalent instruction."""
    from interpreter.instructions import to_flat, to_typed

    typed = to_typed(inst)
    # Typed instruction must expose the correct opcode
    assert typed.opcode == inst.opcode
    # Round-trip back to flat
    flat = to_flat(typed)
    assert flat.opcode == inst.opcode
    assert flat.result_reg == inst.result_reg
    assert flat.label == inst.label
    assert flat.source_location == inst.source_location
    # Operands: compare stringified to handle type coercion
    assert len(flat.operands) == len(inst.operands), (
        f"Operand count mismatch for {inst.opcode}: "
        f"expected {len(inst.operands)}, got {len(flat.operands)}"
    )
    for i, (a, b) in enumerate(zip(flat.operands, inst.operands)):
        if isinstance(b, list):
            # TRY_PUSH catch_labels: list[CodeLabel]
            assert isinstance(a, list)
            assert len(a) == len(b)
            for x, y in zip(a, b):
                assert str(x) == str(y), f"operands[{i}] list element mismatch"
        else:
            assert str(a) == str(b), (
                f"operands[{i}] mismatch for {inst.opcode}: "
                f"expected {b!r}, got {a!r}"
            )
    assert len(flat.branch_targets) == len(inst.branch_targets)
    for a, b in zip(flat.branch_targets, inst.branch_targets):
        assert str(a) == str(b)


# ── Variables & Constants ────────────────────────────────────────


class TestConstRoundTrip:
    def test_string_literal(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.CONST,
                result_reg="%0",
                operands=['"hello"'],
                source_location=_loc(),
            )
        )

    def test_numeric_literal(self):
        _assert_round_trip(
            IRInstruction(opcode=Opcode.CONST, result_reg="%1", operands=["42"])
        )

    def test_boolean_literal(self):
        _assert_round_trip(
            IRInstruction(opcode=Opcode.CONST, result_reg="%2", operands=["True"])
        )

    def test_none_literal(self):
        _assert_round_trip(
            IRInstruction(opcode=Opcode.CONST, result_reg="%3", operands=["None"])
        )

    def test_no_operands(self):
        _assert_round_trip(
            IRInstruction(opcode=Opcode.CONST, result_reg="%4", operands=[])
        )


class TestLoadVarRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(opcode=Opcode.LOAD_VAR, result_reg="%0", operands=["x"])
        )

    def test_this(self):
        _assert_round_trip(
            IRInstruction(opcode=Opcode.LOAD_VAR, result_reg="%1", operands=["this"])
        )


class TestDeclVarRoundTrip:
    def test_basic(self):
        _assert_round_trip(IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%0"]))


class TestStoreVarRoundTrip:
    def test_basic(self):
        _assert_round_trip(IRInstruction(opcode=Opcode.STORE_VAR, operands=["y", "%1"]))


class TestSymbolicRoundTrip:
    def test_param(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.SYMBOLIC,
                result_reg="%0",
                operands=["__param__x"],
            )
        )

    def test_empty_hint(self):
        _assert_round_trip(
            IRInstruction(opcode=Opcode.SYMBOLIC, result_reg="%1", operands=[])
        )


# ── Arithmetic ───────────────────────────────────────────────────


class TestBinopRoundTrip:
    def test_add(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.BINOP,
                result_reg="%2",
                operands=["+", "%0", "%1"],
            )
        )

    def test_comparison(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.BINOP,
                result_reg="%3",
                operands=[">=", "%0", "%1"],
            )
        )


class TestUnopRoundTrip:
    def test_negate(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.UNOP,
                result_reg="%1",
                operands=["!", "%0"],
            )
        )


# ── Calls ────────────────────────────────────────────────────────


class TestCallFunctionRoundTrip:
    def test_no_args(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg="%0",
                operands=["print"],
            )
        )

    def test_with_args(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg="%2",
                operands=["add", "%0", "%1"],
            )
        )

    def test_with_spread(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg="%3",
                operands=["f", "%0", SpreadArguments(register="%1")],
            )
        )


class TestCallMethodRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.CALL_METHOD,
                result_reg="%2",
                operands=["%0", "length"],
            )
        )

    def test_with_args(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.CALL_METHOD,
                result_reg="%3",
                operands=["%0", "push", "%1", "%2"],
            )
        )


class TestCallUnknownRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.CALL_UNKNOWN,
                result_reg="%1",
                operands=["%0"],
            )
        )

    def test_with_args(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.CALL_UNKNOWN,
                result_reg="%3",
                operands=["%0", "%1", "%2"],
            )
        )


# ── Memory — Fields ──────────────────────────────────────────────


class TestLoadFieldRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.LOAD_FIELD,
                result_reg="%1",
                operands=["%0", "name"],
            )
        )


class TestStoreFieldRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.STORE_FIELD,
                operands=["%0", "count", "%1"],
            )
        )


class TestLoadFieldIndirectRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.LOAD_FIELD_INDIRECT,
                result_reg="%2",
                operands=["%0", "%1"],
            )
        )


# ── Memory — Indexing ────────────────────────────────────────────


class TestLoadIndexRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.LOAD_INDEX,
                result_reg="%2",
                operands=["%0", "%1"],
            )
        )


class TestStoreIndexRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.STORE_INDEX,
                operands=["%0", "%1", "%2"],
            )
        )


# ── Memory — Pointers ────────────────────────────────────────────


class TestLoadIndirectRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.LOAD_INDIRECT,
                result_reg="%1",
                operands=["%0"],
            )
        )


class TestStoreIndirectRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.STORE_INDIRECT,
                operands=["%0", "%1"],
            )
        )


class TestAddressOfRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.ADDRESS_OF,
                result_reg="%1",
                operands=["x"],
            )
        )


# ── Objects ──────────────────────────────────────────────────────


class TestNewObjectRoundTrip:
    def test_with_type(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.NEW_OBJECT,
                result_reg="%0",
                operands=["Foo"],
            )
        )

    def test_empty_type(self):
        _assert_round_trip(
            IRInstruction(opcode=Opcode.NEW_OBJECT, result_reg="%0", operands=[])
        )


class TestNewArrayRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.NEW_ARRAY,
                result_reg="%1",
                operands=["list", "%0"],
            )
        )


# ── Control Flow ─────────────────────────────────────────────────


class TestLabelRoundTrip:
    def test_basic(self):
        _assert_round_trip(IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")))


class TestBranchRoundTrip:
    def test_basic(self):
        _assert_round_trip(IRInstruction(opcode=Opcode.BRANCH, label=CodeLabel("L_1")))


class TestBranchIfRoundTrip:
    def test_two_targets(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.BRANCH_IF,
                operands=["%0"],
                branch_targets=[CodeLabel("L_true"), CodeLabel("L_false")],
            )
        )


class TestReturnRoundTrip:
    def test_with_value(self):
        _assert_round_trip(IRInstruction(opcode=Opcode.RETURN, operands=["%0"]))

    def test_void(self):
        _assert_round_trip(IRInstruction(opcode=Opcode.RETURN, operands=[]))


class TestThrowRoundTrip:
    def test_with_value(self):
        _assert_round_trip(IRInstruction(opcode=Opcode.THROW, operands=["%0"]))

    def test_bare(self):
        _assert_round_trip(IRInstruction(opcode=Opcode.THROW, operands=[]))


# ── Exceptions ───────────────────────────────────────────────────


class TestTryPushRoundTrip:
    def test_basic(self):
        _assert_round_trip(
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
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.TRY_PUSH,
                operands=[
                    [CodeLabel("catch_0"), CodeLabel("catch_1")],
                    NO_LABEL,
                    CodeLabel("end_try"),
                ],
            )
        )


class TestTryPopRoundTrip:
    def test_basic(self):
        _assert_round_trip(IRInstruction(opcode=Opcode.TRY_POP))


# ── Regions ──────────────────────────────────────────────────────


class TestAllocRegionRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg="%1",
                operands=["%0"],
            )
        )


class TestLoadRegionRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%2",
                operands=["%0", "%1", 8],
            )
        )


class TestWriteRegionRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.WRITE_REGION,
                operands=["%0", "%1", 8, "%2"],
            )
        )


# ── Continuations ────────────────────────────────────────────────


class TestSetContinuationRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.SET_CONTINUATION,
                operands=["__cont", CodeLabel("L_resume")],
            )
        )


class TestResumeContinuationRoundTrip:
    def test_basic(self):
        _assert_round_trip(
            IRInstruction(
                opcode=Opcode.RESUME_CONTINUATION,
                operands=["__cont"],
            )
        )


# ── Typed field access ───────────────────────────────────────────


class TestTypedFieldAccess:
    """Verify that typed instructions expose named fields, not positional operands."""

    def test_binop_fields(self):
        from interpreter.instructions import to_typed

        inst = IRInstruction(
            opcode=Opcode.BINOP,
            result_reg="%2",
            operands=["+", "%0", "%1"],
        )
        typed = to_typed(inst)
        assert typed.operator == "+"
        assert typed.left == "%0"
        assert typed.right == "%1"
        assert typed.result_reg == Register("%2")

    def test_call_function_fields(self):
        from interpreter.instructions import to_typed

        inst = IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg="%3",
            operands=["add", "%0", "%1"],
        )
        typed = to_typed(inst)
        assert typed.func_name == "add"
        assert typed.args == ("%0", "%1")

    def test_store_field_fields(self):
        from interpreter.instructions import to_typed

        inst = IRInstruction(
            opcode=Opcode.STORE_FIELD,
            operands=["%0", "count", "%1"],
        )
        typed = to_typed(inst)
        assert typed.obj_reg == "%0"
        assert typed.field_name == "count"
        assert typed.value_reg == "%1"

    def test_branch_if_fields(self):
        from interpreter.instructions import to_typed

        inst = IRInstruction(
            opcode=Opcode.BRANCH_IF,
            operands=["%0"],
            branch_targets=[CodeLabel("L_true"), CodeLabel("L_false")],
        )
        typed = to_typed(inst)
        assert typed.cond_reg == "%0"
        assert typed.branch_targets == (CodeLabel("L_true"), CodeLabel("L_false"))

    def test_write_region_length_is_int(self):
        from interpreter.instructions import to_typed

        inst = IRInstruction(
            opcode=Opcode.WRITE_REGION,
            operands=["%0", "%1", 8, "%2"],
        )
        typed = to_typed(inst)
        assert typed.length == 8
        assert isinstance(typed.length, int)

    def test_return_void_has_none_value_reg(self):
        from interpreter.instructions import to_typed

        inst = IRInstruction(opcode=Opcode.RETURN, operands=[])
        typed = to_typed(inst)
        assert typed.value_reg is None

    def test_return_with_value(self):
        from interpreter.instructions import to_typed

        inst = IRInstruction(opcode=Opcode.RETURN, operands=["%0"])
        typed = to_typed(inst)
        assert typed.value_reg == "%0"
