"""ALTER and the GO TOs it redirects: each alterable GO TO dispatches, in IR, on an
ordinal that ALTER stores and the program's initial state resets to 0."""

from __future__ import annotations

import logging

from cobol_asg.asg_types import CobolParagraph
from cobol_asg.cobol_statements import (
    AlteredGoto,
    AlterStatement,
    GotoStatement,
    ProcedureRef,
    SimpleGoto,
)
from interpreter.cobol.alterable_goto import AlterableGoto
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.ordinal_dispatch_ir import emit_ordinal_dispatch
from interpreter.cobol.program_object import program_name
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.continuation_name import ContinuationName
from interpreter.instructions import (
    Branch,
    Label_,
    LoadVar,
    ResumeContinuation,
    SetContinuation,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)


def alterable_goto(para: CobolParagraph) -> tuple[GotoStatement, ...]:
    """The paragraph's GO TO when it is the paragraph's only statement and has no
    DEPENDING ON phrase: the only GO TO an ALTER may name (IBM Enterprise COBOL
    LR, ALTER)."""
    match para.statements:
        case [GotoStatement(form=SimpleGoto() | AlteredGoto()) as goto]:
            return (goto,)
        case _:
            return ()


def lower_alterable_goto(
    ctx: EmitContext, paragraph: CodeLabel, goto: GotoStatement
) -> None:
    """The GO TO branches to its paragraph's dispatch, which comes back here
    while it is unaltered; it then goes to its written target, or, with none,
    on past it."""
    unaltered = ctx.fresh_label("unaltered_goto")
    alterable = AlterableGoto(paragraph=paragraph, unaltered=unaltered)
    ctx.record_alterable_goto(alterable)
    ctx.emit_inst(Branch(label=alterable.dispatch), span=goto.span)
    ctx.emit_inst(Label_(label=unaltered), span=goto.span)
    if isinstance(goto.form, SimpleGoto):
        ctx.emit_inst(
            Branch(label=ctx.procedure_label(goto.form.target)), span=goto.span
        )


def lower_alter(
    ctx: EmitContext,
    stmt: AlterStatement,
    _materialised: MaterialisedSectionedLayout,
) -> None:
    """ALTER para-1 TO PROCEED TO para-2: para-1's GO TO goes to para-2 from now
    on. Stored as para-2's ordinal among para-1's ALTER targets."""
    span = stmt.span
    program = program_name(ctx._asg)
    for pt in stmt.proceed_tos:
        paragraph = ctx.procedure_label(ProcedureRef(paragraph=pt.source))
        target = ctx.procedure_label(ProcedureRef(paragraph=pt.target))
        ordinal = ctx.record_alter(paragraph, target)
        ctx.emit_inst(
            StoreVar(
                name=alter_var(program, paragraph),
                value_reg=ctx.const_to_reg(ordinal, span=span),
            ),
            span=span,
        )
        logger.info("ALTER %s TO PROCEED TO %s", pt.source, pt.target)


def emit_alter_dispatches(ctx: EmitContext) -> None:
    """Each alterable GO TO's dispatch, over every target an ALTER in the
    program names for it, then back to the GO TO. Placed after the
    procedure, out of the path of control falling through."""
    gotos = ctx.alters.gotos
    if not gotos:
        return
    program = program_name(ctx._asg)
    past = ctx.fresh_label("altered_gotos_end")
    ctx.emit_inst(Branch(label=past), span=None)
    _ = [_emit_dispatch(ctx, program, goto) for goto in gotos]
    ctx.emit_inst(Label_(label=past), span=None)


def _emit_dispatch(ctx: EmitContext, program: str, goto: AlterableGoto) -> None:
    ctx.emit_inst(Label_(label=goto.dispatch), span=None)
    ordinal = ctx.fresh_reg()
    ctx.emit_inst(
        LoadVar(result_reg=ordinal, name=alter_var(program, goto.paragraph)),
        span=None,
    )
    emit_ordinal_dispatch(
        IrEmitter(ctx, None), ordinal, ctx.alters.targets_of(goto.paragraph)
    )
    ctx.emit_inst(Branch(label=goto.unaltered), span=None)


def perform_alter_reset(ctx: EmitContext, program_id: str) -> None:
    """Every alterable GO TO back to its unaltered target, as part of the
    program's initial state: at load, and on the next entry after a CANCEL."""
    back = CodeLabel(f"__alter_reset_done_{program_id.lower()}_0")
    ctx.emit_inst(
        SetContinuation(name=_reset_continuation(program_id), target_label=back),
        span=None,
    )
    ctx.emit_inst(Branch(label=_reset_label(program_id)), span=None)
    ctx.emit_inst(Label_(label=back), span=None)


def lower_alter_reset(ctx: EmitContext, program_id: str) -> None:
    """The reset block perform_alter_reset performs. Lowered after the
    procedure, once every alterable GO TO is known; control at load steps over
    it."""
    past = CodeLabel(f"__alter_reset_end_{program_id.lower()}_0")
    ctx.emit_inst(Branch(label=past), span=None)
    ctx.emit_inst(Label_(label=_reset_label(program_id)), span=None)
    zero = ctx.const_to_reg(0, span=None)
    _ = [
        ctx.emit_inst(
            StoreVar(name=alter_var(program_id, goto.paragraph), value_reg=zero),
            span=None,
        )
        for goto in ctx.alters.gotos
    ]
    ctx.emit_inst(ResumeContinuation(name=_reset_continuation(program_id)), span=None)
    ctx.emit_inst(Label_(label=past), span=None)


def alter_var(program_id: str, paragraph: CodeLabel) -> VarName:
    return VarName(f"__alter_{program_id.upper()}_{paragraph}")


def _reset_label(program_id: str) -> CodeLabel:
    return CodeLabel(f"__alter_reset_{program_id.lower()}_0")


def _reset_continuation(program_id: str) -> ContinuationName:
    return ContinuationName(str(_reset_label(program_id)))
