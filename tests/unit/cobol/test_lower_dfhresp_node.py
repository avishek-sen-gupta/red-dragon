# pyright: standard
"""EVALUATE WHEN with a prepass-resolved lit node emits a comparison (red-dragon-kieo).

After the CICS dfhresp prepass, {"kind":"dfhresp","condition":"NOTFND"} is replaced
with {"kind":"lit","value":"13"} before the generic COBOL lowering sees the ASG.
These tests verify that lower_evaluate handles that resolved lit-kind dict correctly.
"""

from __future__ import annotations

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_asg.cobol_expression import FieldRefNode, LiteralNode
from cobol_asg.cobol_statements import EvaluateStatement, WhenStatement
from cobol_asg.expression_subject import ExpressionSubject
from cobol_asg.value_object import ValueObject
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.lower_evaluate import lower_evaluate
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    build_sectioned_layout,
)
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.instructions import Binop, Const
from tests.covers import covers


def _eibresp_ctx() -> tuple[EmitContext, MaterialisedSectionedLayout]:
    """EmitContext + layout with EIBRESP field (COMP S9(8))."""
    asg = CobolASG(
        data_fields=[
            CobolField(
                name="EIBRESP",
                level=77,
                pic="S9(8)",
                usage="COMP",
                offset=0,
            ),
        ]
    )
    sl = build_sectioned_layout(asg)
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    materialised = lower_sectioned_data_division(ctx, sl, "TESTPGM")
    return ctx, materialised


@covers(CobolFeature.EXEC_CICS)
def test_lower_evaluate_when_dfhresp_prepass_lit_emits_comparison() -> None:
    """EVALUATE EIBRESP WHEN <prepass-resolved lit 13> emits a comparison instruction.

    The CICS dfhresp prepass has already replaced {"kind":"dfhresp","condition":"NOTFND"}
    with {"kind":"lit","value":"13"} before we reach lower_evaluate.  The generic
    EVALUATE lowering compares the subject with the WHEN value LiteralNode(13)
    and emits a Binop comparing EIBRESP against 13 (red-dragon-kieo).
    """
    ctx, materialised = _eibresp_ctx()
    stmt = EvaluateStatement(
        subjects=(ExpressionSubject(expr=FieldRefNode(name="EIBRESP")),),
        children=[
            WhenStatement(objects=(ValueObject(value=LiteralNode(value="13")),)),
        ],
    )
    n_before = len(ctx.instructions)
    lower_evaluate(ctx, stmt, materialised)
    new_insts = ctx.instructions[n_before:]
    binop_insts = [i for i in new_insts if isinstance(i, Binop)]
    assert binop_insts, f"Expected a Binop comparison instruction; got: {new_insts}"
    const_insts = [i for i in new_insts if isinstance(i, Const)]
    assert any(
        i.value == 13 for i in const_insts
    ), f"Expected Const(13) in EVALUATE WHEN; got {[i.value for i in const_insts]}"


@covers(CobolFeature.EXEC_CICS)
def test_lower_evaluate_when_lit_27_emits_comparison() -> None:
    """EVALUATE WHEN LiteralNode(27) — same path, different value."""
    ctx, materialised = _eibresp_ctx()
    stmt = EvaluateStatement(
        subjects=(ExpressionSubject(expr=FieldRefNode(name="EIBRESP")),),
        children=[
            WhenStatement(objects=(ValueObject(value=LiteralNode(value="27")),)),
        ],
    )
    n_before = len(ctx.instructions)
    lower_evaluate(ctx, stmt, materialised)
    new_insts = ctx.instructions[n_before:]
    const_insts = [i for i in new_insts if isinstance(i, Const)]
    assert any(
        i.value == 27 for i in const_insts
    ), f"Expected Const(27); got {[i.value for i in const_insts]}"
