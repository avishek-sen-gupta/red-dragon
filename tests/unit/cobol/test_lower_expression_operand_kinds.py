"""Lowering the three operand kinds the bridge emits beyond lit/ref/binop.

``expr_from_dict`` learned ``figurative``, ``length_of`` and ``dfhresp`` so that
one unrecognised operand stops costing a whole program's ASG. Reading them is
only half the job: with no branch in ``lower_expr_node`` all three fell through
to its "Unknown expression node type" fallback and became the constant 0, which
is a wrong answer rather than a loud one -- ``COMPUTE WS-N = LENGTH OF WS-A``
silently computed 0.
"""

from __future__ import annotations

import pytest

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_asg.cobol_expression import (
    DfhRespNode,
    FigurativeNode,
    LengthOfNode,
)
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.condition_lowering import lower_expr_node
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.lowering_scope import LoweringScope
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.instructions import Const, LoadRegion


def _ctx():
    """EmitContext with WS-A PIC X(8) and WS-N PIC 9(4)."""
    asg = CobolASG(
        data_fields=[
            CobolField(name="WS-A", level=77, pic="X(8)", usage="DISPLAY", offset=0),
            CobolField(name="WS-N", level=77, pic="9(4)", usage="DISPLAY", offset=8),
        ]
    )
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    materialised = lower_sectioned_data_division(ctx, build_sectioned_layout(asg), "T")
    return ctx, materialised


def _consts_after(ctx, n_before) -> list:
    return [i.value for i in ctx.instructions[n_before:] if isinstance(i, Const)]


def test_length_of_lowers_to_the_fields_byte_length_not_a_decode():
    """LENGTH OF is a compile-time constant, the same reading eval_ref_mod_expr
    gives it inside a ref-mod subscript."""
    ctx, materialised = _ctx()
    n = len(ctx.instructions)
    lower_expr_node(LoweringScope(ctx, materialised, None), LengthOfNode(name="WS-A"))
    assert 8 in _consts_after(ctx, n)


def test_length_of_an_item_ending_in_an_odo_table_reads_the_object():
    """LENGTH OF such an item is its current length: the one load it makes is
    of the one-byte object, and the result is computed, not a constant."""
    asg = CobolASG(
        data_fields=[
            CobolField(name="WS-N", level=77, pic="9", usage="DISPLAY", offset=0),
            CobolField(
                name="G",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=1,
                children=[
                    CobolField(
                        name="H", level=2, pic="X(2)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="T",
                        level=2,
                        pic="X(4)",
                        usage="DISPLAY",
                        offset=2,
                        occurs=5,
                        element_size=4,
                        occurs_depending_on=RefModOperand(name="WS-N"),
                        occurs_min=1,
                    ),
                ],
            ),
        ]
    )
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    materialised = lower_sectioned_data_division(ctx, build_sectioned_layout(asg), "T")
    n = len(ctx.instructions)
    result = lower_expr_node(
        LoweringScope(ctx, materialised, None), LengthOfNode(name="G")
    )
    emitted = ctx.instructions[n:]
    assert (
        [i.length for i in emitted if isinstance(i, LoadRegion)],
        [type(i).__name__ for i in emitted if i.result_reg == result],
    ) == ([1], ["Binop"])


def test_length_of_an_unknown_field_is_zero_and_warns(caplog):
    ctx, materialised = _ctx()
    n = len(ctx.instructions)
    lower_expr_node(
        LoweringScope(ctx, materialised, None), LengthOfNode(name="NO-SUCH")
    )
    assert 0 in _consts_after(ctx, n)
    assert "LENGTH OF unknown field" in caplog.text


@pytest.mark.parametrize("value", ["ZERO", "ZEROS", "ZEROES", "zeroes"])
def test_the_zero_family_is_the_integer_zero(value):
    """COMPUTE WS-PCT = ZEROES is the case that motivated reading `figurative`
    at all, and the only figurative with an unambiguous arithmetic value."""
    ctx, materialised = _ctx()
    n = len(ctx.instructions)
    lower_expr_node(LoweringScope(ctx, materialised, None), FigurativeNode(value=value))
    assert 0 in _consts_after(ctx, n)


def test_a_non_numeric_figurative_emits_its_fill_character_and_says_it_is_unsized(
    caplog,
):
    """SPACES has no numeric value, and an arithmetic context has no sibling
    operand to size the fill against -- unlike a comparison, which does. One
    fill character is all that can be honestly emitted, so it is warned about."""
    ctx, materialised = _ctx()
    n = len(ctx.instructions)
    lower_expr_node(
        LoweringScope(ctx, materialised, None), FigurativeNode(value="SPACES")
    )
    assert " " in _consts_after(ctx, n)
    assert "no length to size it to" in caplog.text


def test_an_unresolved_dfhresp_refuses_to_invent_a_response_code():
    """DFHRESP's number is release-dependent, so the bridge keeps the name and
    cicada's pre-pass rewrites the node to a literal before the expression tree
    exists. Reaching lowering means that pre-pass did not run; guessing a code
    would silently mis-compare every EIBRESP test in the program."""
    ctx, materialised = _ctx()
    with pytest.raises(ValueError, match=r"DFHRESP.*pre-pass did not run"):
        lower_expr_node(
            LoweringScope(ctx, materialised, None), DfhRespNode(condition="NOTFND")
        )
