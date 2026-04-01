# pyright: standard
"""PROCEDURE DIVISION lowering — sections, paragraphs, and statement iteration."""

from __future__ import annotations

import logging

from interpreter.cobol.asg_types import CobolASG, CobolParagraph, CobolSection
from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.continuation_name import ContinuationName
from interpreter.instructions import Label_, ResumeContinuation
from interpreter.ir import CodeLabel

logger = logging.getLogger(__name__)


def lower_procedure_division(
    ctx: EmitContext,
    asg: CobolASG,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """Lower division-level bare statements, standalone paragraphs, and sections."""
    ctx.section_paragraphs = {
        section.name: [p.name for p in section.paragraphs] for section in asg.sections
    }

    for stmt in asg.statements:
        ctx.lower_statement(stmt, layout, region_reg)

    for para in asg.paragraphs:
        lower_paragraph(ctx, para, layout, region_reg)

    for section in asg.sections:
        lower_section(ctx, section, layout, region_reg)


def lower_section(
    ctx: EmitContext,
    section: CobolSection,
    layout: DataLayout,
    region_reg: str,
) -> None:
    ctx.emit_inst(Label_(label=CodeLabel(f"section_{section.name}")))
    for stmt in section.statements:
        ctx.lower_statement(stmt, layout, region_reg)
    for para in section.paragraphs:
        lower_paragraph(ctx, para, layout, region_reg)
    ctx.emit_inst(
        ResumeContinuation(name=ContinuationName(f"section_{section.name}_end"))
    )


def lower_paragraph(
    ctx: EmitContext,
    para: CobolParagraph,
    layout: DataLayout,
    region_reg: str,
) -> None:
    ctx.emit_inst(Label_(label=CodeLabel(f"para_{para.name}")))
    for stmt in para.statements:
        ctx.lower_statement(stmt, layout, region_reg)
    ctx.emit_inst(ResumeContinuation(name=ContinuationName(f"para_{para.name}_end")))
