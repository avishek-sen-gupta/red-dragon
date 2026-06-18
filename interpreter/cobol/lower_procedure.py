# pyright: standard
"""PROCEDURE DIVISION lowering — sections, paragraphs, and statement iteration."""

from __future__ import annotations

import logging

from interpreter.cobol.asg_types import CobolASG, CobolParagraph, CobolSection
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.continuation_name import ContinuationName
from interpreter.instructions import Label_, ResumeContinuation
from interpreter.ir import CodeLabel

logger = logging.getLogger(__name__)


def lower_procedure_division(
    ctx: EmitContext,
    asg: CobolASG,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Lower division-level bare statements, standalone paragraphs, and sections."""
    for strat in ctx.extension_strategies:
        strat.on_procedure_entry(ctx, materialised)
    ctx.section_paragraphs = {
        section.name: [p.name for p in section.paragraphs] for section in asg.sections
    }
    # Declaratives sections are PERFORM-able within declaratives; register them too.
    for section in asg.declaratives:
        ctx.section_paragraphs[section.name] = [p.name for p in section.paragraphs]

    # Build the USE-declarative registry: map each registered USE to its
    # declarative SECTION NAME so I/O verbs can fire the matching procedure on an
    # unhandled error. Open-mode resolution (use_by_mode) is wired here but
    # consumed in a later task; this task does named-file + GLOBAL only.
    for section in asg.declaratives:
        if section.use is None:
            continue
        if section.use.is_global:
            ctx.use_global = section.name
        elif section.use.target == "FILE":
            for fname in section.use.files:
                ctx.use_by_file[fname.upper()] = section.name
        else:  # INPUT / OUTPUT / I-O / EXTEND
            ctx.use_by_mode[section.use.target] = section.name

    for stmt in asg.statements:
        ctx.lower_statement(stmt, materialised)

    for para in asg.paragraphs:
        lower_paragraph(ctx, para, materialised)

    for section in asg.sections:
        lower_section(ctx, section, materialised)

    # Declaratives last: real flow above keeps the entry point on the first real
    # element. USE-procedure triggering on I/O errors is deferred to m0oa.4.
    for section in asg.declaratives:
        lower_section(ctx, section, materialised)


def lower_section(
    ctx: EmitContext,
    section: CobolSection,
    materialised: MaterialisedSectionedLayout,
) -> None:
    ctx.emit_inst(Label_(label=CodeLabel(f"section_{section.name}")))
    for stmt in section.statements:
        ctx.lower_statement(stmt, materialised)
    for para in section.paragraphs:
        lower_paragraph(ctx, para, materialised)
    ctx.emit_inst(
        ResumeContinuation(name=ContinuationName(f"section_{section.name}_end"))
    )


def lower_paragraph(
    ctx: EmitContext,
    para: CobolParagraph,
    materialised: MaterialisedSectionedLayout,
) -> None:
    ctx.emit_inst(Label_(label=CodeLabel(f"para_{para.name}")))
    for stmt in para.statements:
        ctx.lower_statement(stmt, materialised)
    ctx.emit_inst(ResumeContinuation(name=ContinuationName(f"para_{para.name}_end")))
