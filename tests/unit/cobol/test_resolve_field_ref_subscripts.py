"""Task 4: resolve_field_ref consumes structured subscripts (red-dragon-6ddr)."""

from __future__ import annotations

import pytest

from interpreter.cobol.asg_types import CobolASG, CobolField
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.cobol.features import CobolFeature
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
        ]
    )
    sl = build_sectioned_layout(asg)
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    materialised = lower_sectioned_data_division(ctx, sl)
    return ctx, materialised


@covers(CobolFeature.OCCURS_FIXED)
def test_structured_subscript_matches_legacy_name():
    ctx, materialised = _occurs_ctx()
    ref_struct, _ = ctx.resolve_field_ref(
        "WS-ELEM", materialised, subscripts=("WS-IDX",)
    )
    ref_legacy, _ = ctx.resolve_field_ref("WS-ELEM(WS-IDX)", materialised)
    assert ref_struct.fl.byte_length == ref_legacy.fl.byte_length
    assert ref_struct.fl.offset == ref_legacy.fl.offset


@covers(CobolFeature.OCCURS_FIXED)
def test_two_subscripts_raise():
    ctx, materialised = _occurs_ctx()
    with pytest.raises(NotImplementedError):
        ctx.resolve_field_ref("WS-ELEM", materialised, subscripts=("I", "J"))


@covers(CobolFeature.OCCURS_FIXED)
def test_lower_expr_node_threads_field_ref_subscripts():
    """A FieldRefNode carrying structured subscripts resolves via the bare base
    name + subscripts, raising for multi-dimensional subscripts (proving the
    node's .subscripts is threaded to resolve_field_ref)."""
    from interpreter.cobol.cobol_expression import FieldRefNode
    from interpreter.cobol.condition_lowering import lower_expr_node

    ctx, materialised = _occurs_ctx()
    node = FieldRefNode(name="WS-ELEM", subscripts=("I", "J"))
    with pytest.raises(NotImplementedError):
        lower_expr_node(ctx, node, materialised)


@covers(CobolFeature.OCCURS_FIXED)
def test_lower_display_threads_operand_subscripts():
    """DISPLAY of a subscripted operand threads operand.subscripts to the
    resolver (multi-dim subscripts raise, proving threading from
    lower_arithmetic's RefModOperand source site)."""
    from interpreter.cobol.cobol_statements import DisplayStatement
    from interpreter.cobol.lower_arithmetic import lower_display
    from interpreter.cobol.ref_mod import RefModOperand

    ctx, materialised = _occurs_ctx()
    stmt = DisplayStatement(
        operand=RefModOperand(name="WS-ELEM", subscripts=("I", "J"))
    )
    with pytest.raises(NotImplementedError):
        lower_display(ctx, stmt, materialised)
