# pyright: standard
"""PROCEDURE DIVISION lowering — sections, paragraphs, and statement iteration."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from cobol_asg.asg_types import CobolASG, CobolParagraph, CobolSection
from cobol_asg.cobol_statements import CobolStatementType
from cobol_asg.source_span import SourceSpan
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_alter import (
    alterable_goto,
    emit_alter_dispatches,
    lower_alterable_goto,
)
from interpreter.cobol.lower_program_exit import lower_program_exit
from interpreter.cobol.procedure_labels import procedure_labels
from interpreter.cobol.program_object import program_name, use_request_var
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    Label_,
    LoadVar,
    ResumeContinuation,
    Return_,
    SetContinuation,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import resolve_binop
from interpreter.register import Register

logger = logging.getLogger(__name__)


def lower_procedure_division(
    ctx: EmitContext,
    asg: CobolASG,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Lower division-level bare statements, standalone paragraphs, and sections."""
    for strat in ctx.extension_strategies:
        strat.on_procedure_entry(ctx, materialised)
    ctx.procedures = procedure_labels(
        [*asg.sections, *asg.declaratives], asg.paragraphs
    )

    _lower_use_requests(ctx, asg)

    for stmt in asg.statements:
        ctx.lower_statement(stmt, materialised)

    for para in asg.paragraphs:
        lower_paragraph(ctx, para, materialised)

    for section in asg.sections:
        lower_section(ctx, section, materialised)

    # Running off the last statement is a legal program exit and returns control
    # to the caller, exactly as GOBACK does. It is emitted HERE — after the real
    # flow, before the declaratives — because that is where control falls to; put
    # it after the declaratives and a program without GOBACK would fall into a USE
    # procedure instead of returning (red-dragon-i0jd).
    lower_program_exit(ctx, materialised, span=_end_of_flow_span(asg), implicit=True)

    _lower_after_flow(ctx, asg, materialised)


def _lower_after_flow(
    ctx: EmitContext, asg: CobolASG, materialised: MaterialisedSectionedLayout
) -> None:
    """Declaratives last: real flow above keeps the entry point on the first real
    element. Then the dispatch of every alterable GO TO, now that every ALTER is
    known."""
    for section in asg.declaratives:
        lower_section(ctx, section, materialised)
    emit_alter_dispatches(ctx)


def global_uses(asg: CobolASG) -> list[CobolSection]:
    """The program's USE GLOBAL declaratives."""
    return [s for s in asg.declaratives if s.use and s.use.is_global]


def lower_use_request(ctx: EmitContext, asg: CobolASG) -> None:
    """At load, no USE GLOBAL section of the program is asked for."""
    if not global_uses(asg):
        return
    ctx.emit_inst(
        StoreVar(
            name=use_request_var(program_name(asg)),
            value_reg=ctx.const_to_reg("", span=None),
        ),
        span=None,
    )


def _lower_use_requests(ctx: EmitContext, asg: CobolASG) -> None:
    """A contained program enters this one to run one of its USE GLOBAL sections
    for an I-O condition of its own: it names the section in the request
    variable. On entry the procedure runs the section named, clears the request
    and returns; with none named it carries on."""
    uses = global_uses(asg)
    if not uses:
        return
    request = ctx.fresh_reg()
    ctx.emit_inst(
        LoadVar(result_reg=request, name=use_request_var(program_name(asg))),
        span=uses[0].span,
    )
    _ = [_lower_use_request(ctx, asg, request, section) for section in uses]


def _lower_use_request(
    ctx: EmitContext, asg: CobolASG, request: Register, section: CobolSection
) -> None:
    span = section.span
    asked = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=asked,
            operator=resolve_binop("=="),
            left=request,
            right=ctx.const_to_reg(section.name, span=span),
        ),
        span=span,
    )
    run_lbl, done_lbl, next_lbl = (
        ctx.fresh_label(f"use_request_{tag}") for tag in ("run", "done", "next")
    )
    ctx.emit_inst(
        BranchIf(cond_reg=asked, branch_targets=(run_lbl, next_lbl)), span=span
    )
    ctx.emit_inst(Label_(label=run_lbl), span=span)
    ctx.emit_inst(
        StoreVar(
            name=use_request_var(program_name(asg)),
            value_reg=ctx.const_to_reg("", span=span),
        ),
        span=span,
    )
    ctx.emit_inst(
        SetContinuation(
            name=ctx.procedures.section_end(section.name), target_label=done_lbl
        ),
        span=span,
    )
    ctx.emit_inst(Branch(label=ctx.procedures.section(section.name)), span=span)
    ctx.emit_inst(Label_(label=done_lbl), span=span)
    ctx.emit_inst(Return_(), span=span)
    ctx.emit_inst(Label_(label=next_lbl), span=span)


def _end_of_flow_span(asg: CobolASG) -> SourceSpan | None:
    """The span of the last element control runs through before the program ends.

    The implicit exit has no source text of its own, but every PROCEDURE DIVISION
    instruction must carry a location, so it borrows the last real element's —
    which is where a reader looking for "why did it return here" should land.

    Read with ``getattr`` because the last element need not be a red-dragon type.
    A coprocessor frontend swaps its own statement types into the ASG through the
    extension seam — cicada's ``EXEC CICS``, squall's ``EXEC SQL`` — and that seam
    promises only that ``dispatch_statement`` can route them, not that they carry
    any particular attribute. red-dragon cannot import those types to find out,
    and must not: naming one here would be an import contract violation and would
    still miss the next extension. A span is optional on this path anyway, so
    "there isn't one" is an answer, not a failure (red-dragon-7qmn).
    """
    for elements in (asg.sections, asg.paragraphs, asg.statements):
        if elements:
            return getattr(elements[-1], "span", None)
    return None


def lower_section(
    ctx: EmitContext,
    section: CobolSection,
    materialised: MaterialisedSectionedLayout,
) -> None:
    span = section.span
    labels = ctx.procedures
    ctx.emit_inst(Label_(label=labels.section(section.name)), span=span)
    with ctx.in_section(section.name):
        _lower_section_body(ctx, section, materialised)
    exit_label = labels.section_exit(section.name)
    if ctx.exit_requested(exit_label):
        ctx.emit_inst(Label_(label=exit_label), span=span)
    ctx.emit_inst(
        ResumeContinuation(name=labels.section_end(section.name)),
        span=span,
    )


def _lower_section_body(
    ctx: EmitContext,
    section: CobolSection,
    materialised: MaterialisedSectionedLayout,
) -> None:
    for stmt in section.statements:
        ctx.lower_statement(stmt, materialised)
    for para in section.paragraphs:
        lower_paragraph(ctx, para, materialised)


def lower_paragraph(
    ctx: EmitContext,
    para: CobolParagraph,
    materialised: MaterialisedSectionedLayout,
) -> None:
    span = para.span
    labels = ctx.procedures
    section = ctx.section
    paragraph = labels.paragraph(para.name, section)
    ctx.emit_inst(Label_(label=paragraph), span=span)
    with ctx.in_paragraph(para.name):
        _lower_paragraph_body(ctx, para, paragraph, materialised)
    exit_label = labels.paragraph_exit(para.name, section)
    if ctx.exit_requested(exit_label):
        ctx.emit_inst(Label_(label=exit_label), span=span)
    ctx.emit_inst(
        ResumeContinuation(name=labels.paragraph_end(para.name, section)), span=span
    )


def _lower_paragraph_body(
    ctx: EmitContext,
    para: CobolParagraph,
    paragraph: CodeLabel,
    materialised: MaterialisedSectionedLayout,
) -> None:
    alterable = alterable_goto(para)
    if alterable:
        lower_alterable_goto(ctx, paragraph, alterable[0])
        return
    for position, sentence in enumerate(_sentences(para)):
        _lower_sentence(ctx, para, position, sentence, materialised)


def _sentences(para: CobolParagraph) -> list[list[CobolStatementType]]:
    """The paragraph's statements cut at each period; one sentence when the ASG
    records none."""
    ends = para.sentence_ends or [len(para.statements) - 1]
    starts = [0, *(end + 1 for end in ends[:-1])]
    return [
        para.statements[start : end + 1]
        for start, end in zip(starts, ends, strict=True)
    ]


def _lower_sentence(
    ctx: EmitContext,
    para: CobolParagraph,
    position: int,
    statements: Sequence[CobolStatementType],
    materialised: MaterialisedSectionedLayout,
) -> None:
    """A sentence's statements, then the landing a NEXT SENTENCE in them branched
    to -- only if one did, so a program without one lowers unchanged."""
    exit_label = ctx.procedures.sentence_exit(para.name, ctx.section, position)
    with ctx.in_sentence(exit_label):
        for stmt in statements:
            ctx.lower_statement(stmt, materialised)
    if ctx.exit_requested(exit_label):
        ctx.emit_inst(Label_(label=exit_label), span=para.span)
