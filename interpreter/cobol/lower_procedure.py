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

    for stmt in asg.statements:
        ctx.lower_statement(stmt, materialised)

    for para in asg.paragraphs:
        lower_paragraph(ctx, para, materialised)

    for section in asg.sections:
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
