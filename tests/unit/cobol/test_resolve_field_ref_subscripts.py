"""resolve_field_ref consumes structured ExprNode subscripts (red-dragon-l445).

Subscript interiors are now structured ExprNodes (LiteralNode / FieldRefNode /
BinOpNode / ...) resolved via lower_expr_node, retiring the last stringly-typed
subscript form. The prior string-interpretation path (int(subscript) /
has_field / default-to-1) is gone; an arithmetic subscript that used to silently
resolve to index 1 now resolves to its real computed value.
"""

from __future__ import annotations

import pytest

from interpreter.cobol.asg_types import CobolASG, CobolField
from interpreter.cobol.cobol_expression import (
    BinOpNode,
    FieldRefNode,
    LiteralNode,
)
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.cobol.features import CobolFeature
from interpreter.instructions import Binop, Const
from interpreter.operator_kind import resolve_binop
from tests.covers import covers


def _occurs_ctx():
    """EmitContext + MaterialisedSectionedLayout with an OCCURS table WS-ELEM."""
    asg = CobolASG(
        data_fields=[
            CobolField(
                name="WS-ELEM",
                level=77,
                pic="9(4)",
                usage="DISPLAY",
                offset=0,
                occurs=5,
                element_size=4,
            ),
            CobolField(
                name="WS-IDX",
                level=77,
                pic="9(4)",
                usage="DISPLAY",
                offset=20,
            ),
            CobolField(
                name="WS-I",
                level=77,
                pic="9(4)",
                usage="DISPLAY",
                offset=24,
            ),
        ]
    )
    sl = build_sectioned_layout(asg)
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    materialised = lower_sectioned_data_division(ctx, sl)
    return ctx, materialised


@covers(CobolFeature.OCCURS_FIXED)
def test_structured_field_subscript_yields_element_layout():
    """A FieldRefNode single subscript resolves to the element-level FieldLayout:
    base offset, element-sized byte_length (4, not the whole-table 20)."""
    ctx, materialised = _occurs_ctx()
    ref_struct, _ = ctx.resolve_field_ref(
        "WS-ELEM", materialised, subscripts=(FieldRefNode("WS-IDX"),)
    )
    assert ref_struct.fl.byte_length == 4
    assert ref_struct.fl.offset == 0


@covers(CobolFeature.OCCURS_FIXED)
def test_literal_subscript_computes_constant_offset():
    """A LiteralNode subscript (TBL(2)) is evaluated, not string-parsed: the
    offset arithmetic uses index 2, yielding element-level byte_length 4."""
    ctx, materialised = _occurs_ctx()
    ref_struct, _ = ctx.resolve_field_ref(
        "WS-ELEM", materialised, subscripts=(LiteralNode("2"),)
    )
    assert ref_struct.fl.byte_length == 4
    # The literal index value 2 was emitted as a Const (not defaulted to 1).
    const_vals = [i.value for i in ctx.instructions if isinstance(i, Const)]
    assert 2 in const_vals


@covers(CobolFeature.OCCURS_FIXED)
def test_arithmetic_subscript_resolves_to_computed_index_not_default_one():
    """An arithmetic subscript WS-I + 1 used to silently resolve to index 1 (the
    string path could not parse it). It now lowers via lower_expr_node, emitting
    a Binop("+") for the WS-I + 1 index — proving the real computed index is
    used, not the default-1 fallback (red-dragon-l445)."""
    ctx, materialised = _occurs_ctx()
    n_before = len(ctx.instructions)
    ref_struct, _ = ctx.resolve_field_ref(
        "WS-ELEM",
        materialised,
        subscripts=(BinOpNode("+", FieldRefNode("WS-I"), LiteralNode("1")),),
    )
    emitted = ctx.instructions[n_before:]
    # The index expression itself emitted an addition (WS-I + 1). The old
    # default-1 path would never emit a "+" for the index.
    add_ops = [
        i for i in emitted if isinstance(i, Binop) and i.operator == resolve_binop("+")
    ]
    assert add_ops, "arithmetic subscript must emit its '+' index computation"
    assert ref_struct.fl.byte_length == 4


@covers(CobolFeature.OCCURS_FIXED)
def test_two_subscripts_raise():
    ctx, materialised = _occurs_ctx()
    with pytest.raises(NotImplementedError):
        ctx.resolve_field_ref(
            "WS-ELEM",
            materialised,
            subscripts=(FieldRefNode("I"), FieldRefNode("J")),
        )


@covers(CobolFeature.OCCURS_FIXED)
def test_lower_expr_node_threads_field_ref_subscripts():
    """A FieldRefNode carrying multi-dim structured subscripts raises at resolve
    time (proving the node's .subscripts is threaded to resolve_field_ref)."""
    from interpreter.cobol.condition_lowering import lower_expr_node

    ctx, materialised = _occurs_ctx()
    node = FieldRefNode(
        name="WS-ELEM", subscripts=(FieldRefNode("I"), FieldRefNode("J"))
    )
    with pytest.raises(NotImplementedError):
        lower_expr_node(ctx, node, materialised)


@covers(CobolFeature.OCCURS_FIXED)
def test_lower_expr_node_threads_single_subscript_happy_path():
    """A FieldRefNode with a SINGLE structured subscript lowers cleanly to IR
    (no exception) and yields a result register."""
    from interpreter.cobol.condition_lowering import lower_expr_node

    ctx, materialised = _occurs_ctx()
    node = FieldRefNode(name="WS-ELEM", subscripts=(FieldRefNode("WS-IDX"),))
    n_before = len(ctx.instructions)
    result_reg = lower_expr_node(ctx, node, materialised)
    assert result_reg is not None
    assert len(ctx.instructions) > n_before

    ref_struct, _ = ctx.resolve_field_ref(
        "WS-ELEM", materialised, subscripts=(FieldRefNode("WS-IDX"),)
    )
    assert ref_struct.fl.byte_length == 4


@covers(CobolFeature.OCCURS_FIXED)
def test_lower_display_threads_operand_subscripts():
    """DISPLAY of a subscripted operand threads operand.subscripts to the
    resolver (multi-dim subscripts raise, proving threading)."""
    from interpreter.cobol.cobol_statements import DisplayStatement
    from interpreter.cobol.lower_arithmetic import lower_display
    from interpreter.cobol.ref_mod import RefModOperand

    ctx, materialised = _occurs_ctx()
    stmt = DisplayStatement(
        operands=(
            RefModOperand(
                name="WS-ELEM", subscripts=(FieldRefNode("I"), FieldRefNode("J"))
            ),
        )
    )
    with pytest.raises(NotImplementedError):
        lower_display(ctx, stmt, materialised)


@covers(CobolFeature.OCCURS_FIXED)
def test_lower_display_threads_single_subscript_happy_path():
    """DISPLAY of an operand with a SINGLE valid subscript lowers cleanly to IR."""
    from interpreter.cobol.cobol_statements import DisplayStatement
    from interpreter.cobol.lower_arithmetic import lower_display
    from interpreter.cobol.ref_mod import RefModOperand

    ctx, materialised = _occurs_ctx()
    stmt = DisplayStatement(
        operands=(RefModOperand(name="WS-ELEM", subscripts=(FieldRefNode("WS-IDX"),)),)
    )
    n_before = len(ctx.instructions)
    lower_display(ctx, stmt, materialised)  # must not raise
    assert len(ctx.instructions) > n_before
