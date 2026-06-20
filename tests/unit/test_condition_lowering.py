"""Tests for condition lowering with level-88 condition name expansion."""

from interpreter.cobol.asg_types import CobolField, CobolASG
from interpreter.cobol.condition_lowering import lower_condition
from interpreter.cobol.condition_name import ConditionName, ConditionValue
from interpreter.cobol.condition_name_index import (
    ConditionEntry,
    ConditionNameIndex,
    build_condition_index,
)
from interpreter.cobol.data_layout import build_data_layout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    SectionedLayout,
    build_sectioned_layout,
)
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.ir import Opcode
from tests.covers import covers


def _noop_dispatch(ctx, stmt, materialised):
    pass


def _setup_with_fields(cobol_fields: list[CobolField]):
    """Build layout, emit context, and allocate region for test fields."""
    layout = build_data_layout(cobol_fields)
    condition_index = build_condition_index(layout)
    ctx = EmitContext(
        dispatch_fn=_noop_dispatch,
        condition_index=condition_index,
    )
    asg = CobolASG(data_fields=cobol_fields)
    sl = build_sectioned_layout(asg)
    materialised = lower_sectioned_data_division(ctx, sl, "TESTPGM")
    return ctx, materialised, condition_index


class TestFigurativeConditions:
    """Figurative-constant operands sized to the sibling field."""

    @covers(CobolFeature.FIGURATIVE_SPACES)
    def test_spaces_compares_against_field_length_string(self):
        """WS-X = SPACES builds an N-space string literal sized to WS-X."""
        fields = [
            CobolField(name="WS-X", level=77, pic="X(8)", usage="DISPLAY", offset=0),
        ]
        ctx, materialised, idx = _setup_with_fields(fields)
        lower_condition(
            ctx,
            {
                "not": False,
                "relation": {
                    "left": {"kind": "ref", "name": "WS-X"},
                    "op": "==",
                    "right": {"kind": "figurative", "value": "SPACES"},
                },
            },
            materialised,
            idx,
        )
        const_vals = [
            i.operands[0] for i in ctx.instructions if i.opcode == Opcode.CONST
        ]
        # The figurative SPACES const must be exactly 8 spaces.
        assert " " * 8 in const_vals
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        assert any(i.operands[0] == "==" for i in binop_insts)

    @covers(CobolFeature.FIGURATIVE_SPACES)
    def test_figurative_on_left_uses_right_field_length(self):
        """SPACES = WS-X resolves the figurative length from the right operand."""
        fields = [
            CobolField(name="WS-X", level=77, pic="X(5)", usage="DISPLAY", offset=0),
        ]
        ctx, materialised, idx = _setup_with_fields(fields)
        lower_condition(
            ctx,
            {
                "not": False,
                "relation": {
                    "left": {"kind": "figurative", "value": "SPACES"},
                    "op": "==",
                    "right": {"kind": "ref", "name": "WS-X"},
                },
            },
            materialised,
            idx,
        )
        const_vals = [
            i.operands[0] for i in ctx.instructions if i.opcode == Opcode.CONST
        ]
        assert " " * 5 in const_vals

    @covers(CobolFeature.FIGURATIVE_ZEROS)
    def test_zeros_on_alphanumeric_field(self):
        """WS-X = ZEROS builds an N-zero string literal sized to WS-X."""
        fields = [
            CobolField(name="WS-X", level=77, pic="X(4)", usage="DISPLAY", offset=0),
        ]
        ctx, materialised, idx = _setup_with_fields(fields)
        lower_condition(
            ctx,
            {
                "not": False,
                "relation": {
                    "left": {"kind": "ref", "name": "WS-X"},
                    "op": "==",
                    "right": {"kind": "figurative", "value": "ZEROS"},
                },
            },
            materialised,
            idx,
        )
        const_vals = [
            i.operands[0] for i in ctx.instructions if i.opcode == Opcode.CONST
        ]
        assert "0" * 4 in const_vals


class TestAbbreviatedConditions:
    """Abbreviated/combined relations expand to AND/OR trees."""

    @covers(CobolFeature.FIGURATIVE_SPACES)
    def test_combined_or_expands_to_disjunction(self):
        """A = SPACES OR LOW-VALUES lowers to two relations joined by OR."""
        fields = [
            CobolField(name="WS-X", level=77, pic="X(3)", usage="DISPLAY", offset=0),
        ]
        ctx, materialised, idx = _setup_with_fields(fields)
        node = {
            "op": "OR",
            "left": {
                "not": False,
                "relation": {
                    "left": {"kind": "ref", "name": "WS-X"},
                    "op": "==",
                    "right": {"kind": "figurative", "value": "SPACES"},
                },
            },
            "right": {
                "not": False,
                "relation": {
                    "left": {"kind": "ref", "name": "WS-X"},
                    "op": "==",
                    "right": {"kind": "figurative", "value": "LOW-VALUES"},
                },
            },
        }
        lower_condition(ctx, node, materialised, idx)
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        or_ops = [i for i in binop_insts if i.operands[0] == "or"]
        eq_ops = [i for i in binop_insts if i.operands[0] == "=="]
        assert len(or_ops) == 1
        assert len(eq_ops) == 2


class TestConditionLoweringBasic:
    """Existing behavior: field OP value conditions."""

    @covers(CobolFeature.IF_ELSE)
    def test_simple_comparison(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(4)", usage="DISPLAY", offset=0),
        ]
        ctx, materialised, idx = _setup_with_fields(fields)
        result_reg = lower_condition(
            ctx,
            {
                "not": False,
                "relation": {
                    "left": {"kind": "ref", "name": "WS-A"},
                    "op": ">",
                    "right": {"kind": "lit", "value": "10"},
                },
            },
            materialised,
            idx,
        )
        assert str(result_reg).startswith("%")
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        assert any(i.operands[0] == ">" for i in binop_insts)
        # Verify the comparison value 10 appears as a CONST
        const_vals = [
            i.operands[0] for i in ctx.instructions if i.opcode == Opcode.CONST
        ]
        assert 10 in const_vals

    @covers(CobolFeature.IF_ELSE)
    def test_unknown_condition_never_matches(self):
        """An unparseable text condition must NOT silently evaluate TRUE."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(4)", usage="DISPLAY", offset=0),
        ]
        ctx, materialised, idx = _setup_with_fields(fields)
        result_reg = lower_condition(
            ctx, {"not": False, "text": "UNKNOWN-TOKEN"}, materialised, idx
        )
        const_insts = [i for i in ctx.instructions if i.opcode == Opcode.CONST]
        last_const = const_insts[-1]
        assert last_const.operands == [False]


class TestConditionNameExpansion:
    """Level-88 condition name expansion tests."""

    @covers(CobolFeature.LEVEL_88_CONDITION)
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
        ctx, materialised, idx = _setup_with_fields(fields)
        result_reg = lower_condition(
            ctx,
            {"not": False, "condition_name": "STATUS-ACTIVE"},
            materialised,
            idx,
        )
        assert str(result_reg).startswith("%")
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        eq_ops = [i for i in binop_insts if i.operands[0] == "=="]
        assert len(eq_ops) == 1
        # Verify the comparison value 'A' appears as a CONST. The parent field is
        # PIC X(1) (ALPHANUMERIC), so the 88 VALUE is emitted as a QUOTED string
        # literal ('"A"') — it must compare as the character "A" against the
        # parent's decoded character form, not be numerically coerced (the
        # read-side counterpart of the SET <88> character write, red-dragon-xcm9).
        const_vals = [
            i.operands[0] for i in ctx.instructions if i.opcode == Opcode.CONST
        ]
        assert "A" in const_vals

    @covers(CobolFeature.LEVEL_88_CONDITION)
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
        ctx, materialised, idx = _setup_with_fields(fields)
        result_reg = lower_condition(
            ctx,
            {"not": False, "condition_name": "STATUS-VALID"},
            materialised,
            idx,
        )
        assert str(result_reg).startswith("%")
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        eq_ops = [i for i in binop_insts if i.operands[0] == "=="]
        or_ops = [i for i in binop_insts if i.operands[0] == "or"]
        assert len(eq_ops) == 3
        assert len(or_ops) == 2

    @covers(CobolFeature.CONDITION_VALUES_THRU)
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
        ctx, materialised, idx = _setup_with_fields(fields)
        result_reg = lower_condition(
            ctx,
            {"not": False, "condition_name": "STATUS-ALPHA"},
            materialised,
            idx,
        )
        assert str(result_reg).startswith("%")
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        ge_ops = [i for i in binop_insts if i.operands[0] == ">="]
        le_ops = [i for i in binop_insts if i.operands[0] == "<="]
        and_ops = [i for i in binop_insts if i.operands[0] == "and"]
        assert len(ge_ops) == 1
        assert len(le_ops) == 1
        assert len(and_ops) == 1
        # Verify the range boundary values 'A' and 'Z' appear as CONSTs. The
        # parent is PIC X(1) (ALPHANUMERIC), so each boundary is emitted as a
        # QUOTED string literal so it compares against the field's decoded
        # character form (red-dragon-xcm9).
        const_vals = [
            i.operands[0] for i in ctx.instructions if i.opcode == Opcode.CONST
        ]
        assert "A" in const_vals
        assert "Z" in const_vals

    @covers(CobolFeature.CONDITION_VALUES_THRU)
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
        ctx, materialised, idx = _setup_with_fields(fields)
        result_reg = lower_condition(
            ctx, {"not": False, "condition_name": "VALID-CODE"}, materialised, idx
        )
        assert str(result_reg).startswith("%")
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
        # Verify discrete 'A' and range boundaries 'X', 'Z' appear as CONSTs. The
        # parent is PIC X(1) (ALPHANUMERIC), so each VALUE is emitted as a QUOTED
        # string literal to compare as a character against the decoded field
        # (red-dragon-xcm9).
        const_vals = [
            i.operands[0] for i in ctx.instructions if i.opcode == Opcode.CONST
        ]
        assert "A" in const_vals
        assert "X" in const_vals
        assert "Z" in const_vals

    @covers(CobolFeature.LEVEL_88_CONDITION)
    def test_unknown_condition_passes_through(self):
        """A single token that is NOT a known condition name must never-match
        without any condition-name expansion (no or/and/== from expansion)."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(4)", usage="DISPLAY", offset=0),
        ]
        ctx, materialised, idx = _setup_with_fields(fields)
        result_reg = lower_condition(
            ctx, {"not": False, "text": "NONEXISTENT-COND"}, materialised, idx
        )
        const_insts = [i for i in ctx.instructions if i.opcode == Opcode.CONST]
        last_const = const_insts[-1]
        assert last_const.operands == [False]
        # No expansion: no or/and BINOPs that condition-name expansion would produce
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        expansion_ops = [i for i in binop_insts if i.operands[0] in ("or", "and", "==")]
        assert len(expansion_ops) == 0, "Unknown condition should not expand"

    @covers(CobolFeature.LEVEL_88_CONDITION)
    def test_regular_comparison_still_works_with_index(self):
        """Normal 'field OP value' conditions still work when index is present.

        Having a condition index should not cause the comparator to expand
        'WS-STATUS = A' as if it were a condition name lookup.
        """
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
        ctx, materialised, idx = _setup_with_fields(fields)
        result_reg = lower_condition(
            ctx,
            {
                "not": False,
                "relation": {
                    "left": {"kind": "ref", "name": "WS-STATUS"},
                    "op": "==",
                    "right": {"kind": "lit", "value": "A"},
                },
            },
            materialised,
            idx,
        )
        assert str(result_reg).startswith("%")
        binop_insts = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        eq_ops = [i for i in binop_insts if i.operands[0] == "=="]
        assert len(eq_ops) == 1
        # No condition-name expansion: no or/and BINOPs from expansion
        or_ops = [i for i in binop_insts if i.operands[0] == "or"]
        assert len(or_ops) == 0, "Regular comparison should not trigger expansion"
