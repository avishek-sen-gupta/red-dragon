"""The run unit's EXTERNAL areas: allocated once, by the first program loaded that
describes each, and found by name by every program that describes it.

A program's load-time code finds each of its areas in the run unit's directory of that
kind and allocates it zero-filled when it is not there yet; an EXTERNAL file's
connector starts closed at the same moment. Its procedure loads each area's region
from the directory on entry."""

from __future__ import annotations

from collections.abc import Sequence

from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.external_area import (
    ExternalArea,
    ExternalKind,
    external_directory,
)
from interpreter.cobol.external_binding import ExternalBinding
from interpreter.cobol.file_state import external_file_state
from interpreter.cobol.file_verb_ir import emit_closed
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.field_name import FieldName
from interpreter.instructions import AllocRegion, LoadField, StoreField

_CONTAINS = "dict_contains_key"


def lower_external_areas(ctx: EmitContext, areas: Sequence[ExternalArea]) -> None:
    _ = [_described(IrEmitter(ctx, None), area) for area in areas]


def bind_external(
    ctx: EmitContext, areas: Sequence[ExternalArea]
) -> tuple[ExternalBinding, ...]:
    return tuple(_bound(IrEmitter(ctx, None), area) for area in areas)


def _described(e: IrEmitter, area: ExternalArea) -> None:
    directory = e.load(external_directory(area.kind))
    present = e.call(_CONTAINS, directory, e.text(area.name))
    done = e.label("external_present")
    e.skip_if(present, done)
    region = e.ctx.fresh_reg()
    e.ctx.emit_inst(AllocRegion(result_reg=region, size_reg=e.int_(area.length)))
    e.ctx.emit_inst(
        StoreField(obj_reg=directory, field_name=FieldName(area.name), value_reg=region)
    )
    if area.kind is ExternalKind.FILE:
        emit_closed(e, external_file_state(area.name), False)
    e.place(done)


def _bound(e: IrEmitter, area: ExternalArea) -> ExternalBinding:
    region = e.ctx.fresh_reg()
    e.ctx.emit_inst(
        LoadField(
            result_reg=region,
            obj_reg=e.load(external_directory(area.kind)),
            field_name=FieldName(area.name),
        )
    )
    return ExternalBinding(area, region)
