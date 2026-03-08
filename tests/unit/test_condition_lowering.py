"""Tests for condition lowering with level-88 condition name expansion."""

from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.condition_lowering import lower_condition
from interpreter.cobol.condition_name import ConditionName, ConditionValue
from interpreter.cobol.condition_name_index import (
    ConditionEntry,
    ConditionNameIndex,
    build_condition_index,
)
from interpreter.cobol.data_layout import build_data_layout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_data_division import lower_data_division
from interpreter.ir import Opcode


def _noop_dispatch(ctx, stmt, layout, region_reg):
    pass


def _setup_with_fields(cobol_fields: list[CobolField]):
    """Build layout, emit context, and allocate region for test fields."""
    layout = build_data_layout(cobol_fields)
    condition_index = build_condition_index(layout.fields)
    ctx = EmitContext(
        dispatch_fn=_noop_dispatch,
        condition_index=condition_index,
    )
    region_reg = lower_data_division(ctx, layout)
    return ctx, layout, region_reg, condition_index


class TestConditionLoweringBasic:
    """Existing behavior: field OP value conditions."""

    def test_simple_comparison(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(4)", usage="DISPLAY", offset=0),
        ]
        ctx, layout, region_reg, idx = _setup_with_fields(fields)
        result_reg = lower_condition(ctx, "WS-A > 10", layout, region_reg, idx)
        assert result_reg.startswith("%r")
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        assert any(i.operands[0] == ">" for i in binop_insts)

    def test_unknown_condition_defaults_to_true(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(4)", usage="DISPLAY", offset=0),
        ]
        ctx, layout, region_reg, idx = _setup_with_fields(fields)
        result_reg = lower_condition(ctx, "UNKNOWN-TOKEN", layout, region_reg, idx)
        const_insts = [i for i in ctx.instructions if i.opcode == Opcode.CONST]
        last_const = const_insts[-1]
        assert last_const.operands == [True]


class TestConditionNameExpansion:
    """Level-88 condition name expansion tests."""

    def test_single_value_condition(self):
        """IF STATUS-ACTIVE expands to WS-STATUS == 'A'."""
        fields = [
            CobolField(
                name="WS-STATUS",
                level=5,
                pic="X(1)",
                usage="DISPLAY",
                offset=0,
                conditions=[
                    ConditionName(
                        name="STATUS-ACTIVE",
                        values=[ConditionValue(from_val="A")],
                    ),
                ],
            ),
        ]
        ctx, layout, region_reg, idx = _setup_with_fields(fields)
        result_reg = lower_condition(ctx, "STATUS-ACTIVE", layout, region_reg, idx)
        assert result_reg.startswith("%r")
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        eq_ops = [i for i in binop_insts if i.operands[0] == "=="]
        assert len(eq_ops) == 1

    def test_multi_value_or_expansion(self):
        """IF STATUS-VALID expands to WS-STATUS == 'A' OR WS-STATUS == 'B' OR WS-STATUS == 'C'."""
        fields = [
            CobolField(
                name="WS-STATUS",
                level=5,
                pic="X(1)",
                usage="DISPLAY",
                offset=0,
                conditions=[
                    ConditionName(
                        name="STATUS-VALID",
                        values=[
                            ConditionValue(from_val="A"),
                            ConditionValue(from_val="B"),
                            ConditionValue(from_val="C"),
                        ],
                    ),
                ],
            ),
        ]
        ctx, layout, region_reg, idx = _setup_with_fields(fields)
        result_reg = lower_condition(ctx, "STATUS-VALID", layout, region_reg, idx)
        assert result_reg.startswith("%r")
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        eq_ops = [i for i in binop_insts if i.operands[0] == "=="]
        or_ops = [i for i in binop_insts if i.operands[0] == "or"]
        assert len(eq_ops) == 3
        assert len(or_ops) == 2

    def test_thru_range_expansion(self):
        """IF STATUS-ALPHA expands to WS-STATUS >= 'A' AND WS-STATUS <= 'Z'."""
        fields = [
            CobolField(
                name="WS-STATUS",
                level=5,
                pic="X(1)",
                usage="DISPLAY",
                offset=0,
                conditions=[
                    ConditionName(
                        name="STATUS-ALPHA",
                        values=[ConditionValue(from_val="A", to_val="Z")],
                    ),
                ],
            ),
        ]
        ctx, layout, region_reg, idx = _setup_with_fields(fields)
        result_reg = lower_condition(ctx, "STATUS-ALPHA", layout, region_reg, idx)
        assert result_reg.startswith("%r")
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        ge_ops = [i for i in binop_insts if i.operands[0] == ">="]
        le_ops = [i for i in binop_insts if i.operands[0] == "<="]
        and_ops = [i for i in binop_insts if i.operands[0] == "and"]
        assert len(ge_ops) == 1
        assert len(le_ops) == 1
        assert len(and_ops) == 1

    def test_mixed_discrete_and_range(self):
        """Mixed: VALUE 'A' 'X' THRU 'Z' — produces 1 eq + 1 range, combined with OR."""
        fields = [
            CobolField(
                name="WS-CODE",
                level=5,
                pic="X(1)",
                usage="DISPLAY",
                offset=0,
                conditions=[
                    ConditionName(
                        name="VALID-CODE",
                        values=[
                            ConditionValue(from_val="A"),
                            ConditionValue(from_val="X", to_val="Z"),
                        ],
                    ),
                ],
            ),
        ]
        ctx, layout, region_reg, idx = _setup_with_fields(fields)
        result_reg = lower_condition(ctx, "VALID-CODE", layout, region_reg, idx)
        assert result_reg.startswith("%r")
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        eq_ops = [i for i in binop_insts if i.operands[0] == "=="]
        ge_ops = [i for i in binop_insts if i.operands[0] == ">="]
        le_ops = [i for i in binop_insts if i.operands[0] == "<="]
        or_ops = [i for i in binop_insts if i.operands[0] == "or"]
        and_ops = [i for i in binop_insts if i.operands[0] == "and"]
        assert len(eq_ops) == 1
        assert len(ge_ops) == 1
        assert len(le_ops) == 1
        assert len(and_ops) == 1
        assert len(or_ops) == 1

    def test_unknown_condition_passes_through(self):
        """A single token that is NOT a known condition name defaults to true
        without any condition-name expansion (no or/and/== from expansion)."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(4)", usage="DISPLAY", offset=0),
        ]
        ctx, layout, region_reg, idx = _setup_with_fields(fields)
        result_reg = lower_condition(ctx, "NONEXISTENT-COND", layout, region_reg, idx)
        const_insts = [i for i in ctx.instructions if i.opcode == Opcode.CONST]
        last_const = const_insts[-1]
        assert last_const.operands == [True]
        # No expansion: no or/and BINOPs that condition-name expansion would produce
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        expansion_ops = [i for i in binop_insts if i.operands[0] in ("or", "and", "==")]
        assert len(expansion_ops) == 0, "Unknown condition should not expand"

    def test_regular_comparison_still_works_with_index(self):
        """Normal 'field OP value' conditions still work when index is present."""
        fields = [
            CobolField(
                name="WS-STATUS",
                level=5,
                pic="X(1)",
                usage="DISPLAY",
                offset=0,
                conditions=[
                    ConditionName(
                        name="STATUS-ACTIVE",
                        values=[ConditionValue(from_val="A")],
                    ),
                ],
            ),
        ]
        ctx, layout, region_reg, idx = _setup_with_fields(fields)
        result_reg = lower_condition(ctx, "WS-STATUS = A", layout, region_reg, idx)
        assert result_reg.startswith("%r")
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        eq_ops = [i for i in binop_insts if i.operands[0] == "=="]
        assert len(eq_ops) == 1
