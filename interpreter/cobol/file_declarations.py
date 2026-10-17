"""Declares each SELECT's frame to the file provider once, from the program's start-up code."""

from __future__ import annotations

from cobol_asg.cobol_statements import FileControlEntry
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.file_facts import file_frame
from interpreter.cobol.program_object import program_name
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    SectionedLayout,
)
from interpreter.cobol.special_registers import SPECIAL_REGISTERS_LAYOUT
from interpreter.func_name import FuncName
from interpreter.instructions import CallFunction, Const
from interpreter.register import NO_REGISTER
from interpreter.types.type_expr import UNKNOWN


def _layout_only(sectioned: SectionedLayout) -> MaterialisedSectionedLayout:
    return MaterialisedSectionedLayout(
        working_storage=(sectioned.working_storage, NO_REGISTER),
        linkage=(sectioned.linkage, NO_REGISTER),
        local_storage=(sectioned.local_storage, NO_REGISTER),
        file=(sectioned.file, NO_REGISTER),
        special_registers=(SPECIAL_REGISTERS_LAYOUT, NO_REGISTER),
        indexes=(sectioned.indexes, NO_REGISTER),
        linkage_owners=sectioned.linkage_owners,
    )


def _declare(
    ctx: EmitContext, entry: FileControlEntry, layout: MaterialisedSectionedLayout
) -> None:
    frame_reg, program_reg = ctx.fresh_reg(), ctx.fresh_reg()
    ctx.emit_inst(
        Const(
            result_reg=frame_reg,
            value=file_frame(ctx._asg, entry, layout).data(),
            type_expr=UNKNOWN,
        )
    )
    ctx.emit_inst(Const.string(program_reg, program_name(ctx._asg)))
    ctx.emit_inst(
        CallFunction(
            result_reg=ctx.fresh_reg(),
            func_name=FuncName("__cobol_declare_file"),
            args=(frame_reg, program_reg),
        )
    )


def lower_file_declarations(ctx: EmitContext, sectioned: SectionedLayout) -> None:
    layout = _layout_only(sectioned)
    _ = [_declare(ctx, entry, layout) for entry in ctx._asg.file_control]
