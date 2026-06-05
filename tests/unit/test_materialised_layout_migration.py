"""TDD tests for Task 5: replace (DataLayout, region_reg) with MaterialisedSectionedLayout.

These tests verify the NEW API. They are written BEFORE the implementation
and are expected to FAIL initially.
"""

from __future__ import annotations

from interpreter.cobol.asg_types import CobolASG, CobolField
from interpreter.cobol.cobol_statements import (
    DisplayStatement,
    MoveStatement,
    StopRunStatement,
)
from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.data_layout import DataLayout, FieldLayout, build_data_layout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_data_division import (
    lower_data_division,
    lower_sectioned_data_division,
)
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    SectionedLayout,
    build_sectioned_layout,
)
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.ir import Opcode
from interpreter.register import NO_REGISTER, Register
from tests.covers import covers, NotLanguageFeature


def _make_field(name: str, pic: str = "X(5)", offset: int = 0) -> CobolField:
    return CobolField(name=name, level=1, pic=pic, usage="DISPLAY", offset=offset)


def _make_materialised(
    ws_fields: list[CobolField] | None = None,
) -> MaterialisedSectionedLayout:
    """Helper: build a MaterialisedSectionedLayout from a simple ASG."""
    asg = CobolASG(data_fields=ws_fields or [_make_field("WS-X")])
    sl = build_sectioned_layout(asg)
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    return lower_sectioned_data_division(ctx, sl)


# ── EmitContext.has_field with MaterialisedSectionedLayout ─────────────────


class TestEmitContextHasField:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_has_field_returns_true_for_ws_field(self):
        asg = CobolASG(data_fields=[_make_field("WS-A")])
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        assert ctx.has_field("WS-A", materialised) is True

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_has_field_returns_false_for_unknown(self):
        asg = CobolASG(data_fields=[_make_field("WS-A")])
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        assert ctx.has_field("WS-NONEXISTENT", materialised) is False

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_has_field_finds_linkage_field(self):
        asg = CobolASG(
            data_fields=[_make_field("WS-A")],
            linkage_fields=[_make_field("LK-B")],
        )
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        assert ctx.has_field("LK-B", materialised) is True


# ── EmitContext.resolve_field_ref with MaterialisedSectionedLayout ─────────


class TestEmitContextResolveFieldRef:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_resolve_field_ref_returns_tuple_of_ref_and_register(self):
        from interpreter.cobol.field_resolution import ResolvedFieldRef

        asg = CobolASG(data_fields=[_make_field("WS-A")])
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        result = ctx.resolve_field_ref("WS-A", materialised)

        assert isinstance(result, tuple)
        assert len(result) == 2
        ref, rr = result
        assert isinstance(ref, ResolvedFieldRef)
        assert isinstance(rr, Register)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_resolve_field_ref_ws_returns_ws_region_register(self):
        asg = CobolASG(data_fields=[_make_field("WS-A")])
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        _, rr = ctx.resolve_field_ref("WS-A", materialised)
        ws_reg = materialised.working_storage[1]

        assert rr == ws_reg


# ── EmitContext.lower_statement with MaterialisedSectionedLayout ───────────


class TestEmitContextLowerStatement:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_lower_statement_with_materialised_dispatches_stop_run(self):
        asg = CobolASG(data_fields=[_make_field("WS-A")])
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        ctx.lower_statement(StopRunStatement(), materialised)

        opcodes = [i.opcode for i in ctx.instructions]
        assert Opcode.RETURN in opcodes

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_lower_statement_with_materialised_dispatches_display(self):
        from interpreter.cobol.cobol_statements import RefModOperand

        asg = CobolASG(data_fields=[_make_field("WS-A")])
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        stmt = DisplayStatement(operand=RefModOperand(name="HELLO"))
        ctx.lower_statement(stmt, materialised)

        opcodes = [i.opcode for i in ctx.instructions]
        assert Opcode.CALL_FUNCTION in opcodes


# ── EmitContext.lower_condition with MaterialisedSectionedLayout ───────────


class TestEmitContextLowerCondition:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_lower_condition_with_materialised_emits_binop(self):
        asg = CobolASG(data_fields=[_make_field("WS-A", pic="9(4)")])
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        condition = {
            "not": False,
            "relation": {
                "left": {"kind": "ref", "name": "WS-A"},
                "op": ">",
                "right": {"kind": "lit", "value": "10"},
            },
        }
        result_reg = ctx.lower_condition(condition, materialised)

        assert str(result_reg).startswith("%")
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        assert any(i.operands[0] == ">" for i in binop_insts)


# ── dispatch_statement with MaterialisedSectionedLayout ───────────────────


class TestDispatchStatementWithMaterialised:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_dispatch_stop_run_with_materialised(self):
        asg = CobolASG(data_fields=[_make_field("WS-A")])
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        dispatch_statement(ctx, StopRunStatement(), materialised)

        opcodes = [i.opcode for i in ctx.instructions]
        assert Opcode.RETURN in opcodes


# ── lower_move with MaterialisedSectionedLayout ────────────────────────────


class TestLowerMoveWithMaterialised:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_lower_move_literal_to_field_emits_write_region(self):
        from interpreter.cobol.lower_arithmetic import lower_move
        from interpreter.cobol.cobol_statements import MoveStatement, RefModOperand

        asg = CobolASG(data_fields=[_make_field("WS-A")])
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        stmt = MoveStatement(
            source=RefModOperand(name="HELLO"),
            target=RefModOperand(name="WS-A"),
        )
        lower_move(ctx, stmt, materialised)

        opcodes = [i.opcode for i in ctx.instructions]
        assert Opcode.WRITE_REGION in opcodes


# ── lower_arithmetic with MaterialisedSectionedLayout ─────────────────────


class TestLowerArithmeticWithMaterialised:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_lower_arithmetic_add_emits_binop_and_write(self):
        from interpreter.cobol.lower_arithmetic import lower_arithmetic
        from interpreter.cobol.cobol_statements import (
            ArithmeticStatement,
            RefModOperand,
        )

        asg = CobolASG(data_fields=[_make_field("WS-A", pic="9(5)")])
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        stmt = ArithmeticStatement(
            op="ADD",
            source=RefModOperand(name="1"),
            target="WS-A",
            giving=[],
            on_size_error=[],
            not_on_size_error=[],
        )
        lower_arithmetic(ctx, stmt, materialised)

        opcodes = [i.opcode for i in ctx.instructions]
        assert Opcode.BINOP in opcodes
        assert Opcode.WRITE_REGION in opcodes


# ── lower_io with MaterialisedSectionedLayout ──────────────────────────────


class TestLowerIoWithMaterialised:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_lower_accept_emits_call_function(self):
        from interpreter.cobol.lower_io import lower_accept
        from interpreter.cobol.cobol_statements import AcceptStatement

        asg = CobolASG(data_fields=[_make_field("WS-A")])
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        stmt = AcceptStatement(target="WS-A", from_device="SYSIN")
        lower_accept(ctx, stmt, materialised)

        opcodes = [i.opcode for i in ctx.instructions]
        assert Opcode.CALL_FUNCTION in opcodes


# ── lower_perform with MaterialisedSectionedLayout ────────────────────────


class TestLowerPerformWithMaterialised:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_lower_perform_inline_body_dispatches_children(self):
        from interpreter.cobol.lower_perform import lower_perform
        from interpreter.cobol.cobol_statements import PerformStatement

        asg = CobolASG(data_fields=[_make_field("WS-A")])
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        stmt = PerformStatement(
            target="",
            thru="",
            spec=None,
            children=[StopRunStatement()],
        )
        lower_perform(ctx, stmt, materialised)

        opcodes = [i.opcode for i in ctx.instructions]
        assert Opcode.RETURN in opcodes


# ── lower_call with MaterialisedSectionedLayout ────────────────────────────


class TestLowerCallWithMaterialised:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_lower_call_emits_call_with_memory(self):
        from interpreter.cobol.lower_call import lower_call
        from interpreter.cobol.cobol_statements import CallStatement

        asg = CobolASG(data_fields=[_make_field("WS-A")])
        sl = build_sectioned_layout(asg)
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        materialised = lower_sectioned_data_division(ctx, sl)

        stmt = CallStatement(program="MY-PROG", using=[], giving="")
        lower_call(ctx, stmt, materialised)

        opcodes = [i.opcode for i in ctx.instructions]
        assert Opcode.CALL_WITH_MEMORY in opcodes
