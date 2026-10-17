"""SORT, RELEASE and RETURN lowering: the sort file is a sequential work file that
the USING files or the input procedure's RELEASEs fill, that is put in key order,
and that the GIVING files copy or the output procedure's RETURNs read."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from cobol_asg.cobol_statements import (
    CloseStatement,
    OpenStatement,
    PerformStatement,
    ProcedureRange,
    ReadStatement,
    ReleaseStatement,
    ReturnStatement,
    SortStatement,
    WriteStatement,
)
from cobol_asg.file_enums import OpenMode
from cobol_asg.sort_files import SortFiles
from cobol_asg.sort_key import SortKey
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_io import lower_close, lower_open, lower_read, lower_write
from interpreter.cobol.lower_perform import emit_perform_branch
from interpreter.cobol.program_object import program_name
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.sort_field import SortField, sort_field_arguments
from interpreter.cobol.sort_key_layout import sort_key_encoding
from interpreter.func_name import FuncName
from interpreter.instructions import CallFunction
from interpreter.register import Register

_SORT_USING = FuncName("__cobol_sort_using")
_SORT_GIVING = FuncName("__cobol_sort_giving")
_SORT_FILE = FuncName("__cobol_sort_file")


def _first_record(ctx: EmitContext, sort_file: str) -> str:
    return next(
        record
        for record, selected in ctx._asg.file_record_to_select.items()
        if selected == sort_file.upper()
    )


def _emit_call(
    ctx: EmitContext,
    stmt: SortStatement,
    name: FuncName,
    values: tuple[int | str, ...],
) -> None:
    ctx.emit_inst(
        CallFunction(
            result_reg=ctx.fresh_reg(),
            func_name=name,
            args=tuple(
                Register(str(ctx.const_to_reg(value, span=stmt.span)))
                for value in (*values, program_name(ctx._asg))
            ),
        ),
        span=stmt.span,
    )


def _open(
    ctx: EmitContext,
    stmt: SortStatement,
    mode: OpenMode,
    filename: str,
    materialised: MaterialisedSectionedLayout,
) -> None:
    lower_open(
        ctx,
        OpenStatement(mode_groups=[(mode, [filename])], span=stmt.span),
        materialised,
    )


def _close(
    ctx: EmitContext,
    stmt: SortStatement,
    filename: str,
    materialised: MaterialisedSectionedLayout,
) -> None:
    lower_close(ctx, CloseStatement(files=[filename], span=stmt.span), materialised)


def _transfer(
    ctx: EmitContext,
    stmt: SortStatement,
    filename: str,
    materialised: MaterialisedSectionedLayout,
    direction: tuple[FuncName, OpenMode],
) -> None:
    name, mode = direction
    _open(ctx, stmt, mode, filename, materialised)
    _emit_call(ctx, stmt, name, (stmt.file_name, filename))
    _close(ctx, stmt, filename, materialised)


def _perform(
    ctx: EmitContext,
    stmt: SortStatement,
    procedure: ProcedureRange,
    materialised: MaterialisedSectionedLayout,
) -> None:
    emit_perform_branch(
        ctx,
        PerformStatement(
            target=procedure.target.paragraph,
            target_section=procedure.target.section,
            thru=procedure.thru.paragraph,
            thru_section=procedure.thru.section,
            span=stmt.span,
        ),
        materialised,
    )


def _copy_in(
    ctx: EmitContext,
    stmt: SortStatement,
    files: SortFiles,
    materialised: MaterialisedSectionedLayout,
) -> None:
    for filename in files.names:
        _transfer(ctx, stmt, filename, materialised, (_SORT_USING, OpenMode.INPUT))


def _reading(
    ctx: EmitContext,
    stmt: SortStatement,
    materialised: MaterialisedSectionedLayout,
    emit: Callable[[], None],
) -> None:
    _open(ctx, stmt, OpenMode.INPUT, stmt.file_name, materialised)
    emit()
    _close(ctx, stmt, stmt.file_name, materialised)


def _copy_out(
    ctx: EmitContext,
    stmt: SortStatement,
    files: SortFiles,
    materialised: MaterialisedSectionedLayout,
) -> None:
    for filename in files.names:
        _reading(
            ctx,
            stmt,
            materialised,
            partial(
                _transfer,
                ctx,
                stmt,
                filename,
                materialised,
                (_SORT_GIVING, OpenMode.OUTPUT),
            ),
        )


def _fill(
    ctx: EmitContext, stmt: SortStatement, materialised: MaterialisedSectionedLayout
) -> None:
    match stmt.source:
        case SortFiles() as files:
            _copy_in(ctx, stmt, files, materialised)
        case ProcedureRange() as procedure:
            _perform(ctx, stmt, procedure, materialised)


def _drain(
    ctx: EmitContext, stmt: SortStatement, materialised: MaterialisedSectionedLayout
) -> None:
    match stmt.sink:
        case SortFiles() as files:
            _copy_out(ctx, stmt, files, materialised)
        case ProcedureRange() as procedure:
            _reading(
                ctx,
                stmt,
                materialised,
                partial(_perform, ctx, stmt, procedure, materialised),
            )


def _sort_field(
    key: SortKey, record: FieldLayout, materialised: MaterialisedSectionedLayout
) -> SortField:
    layout, _ = materialised.resolve(key.key.name, key.key.qualifiers)
    return SortField(
        offset=layout.offset - record.offset,
        length=layout.byte_length,
        encoding=sort_key_encoding(layout),
        direction=key.direction,
    )


def _emit_order(
    ctx: EmitContext, stmt: SortStatement, materialised: MaterialisedSectionedLayout
) -> None:
    record, _ = materialised.resolve(_first_record(ctx, stmt.file_name))
    fields = (_sort_field(key, record, materialised) for key in stmt.keys)
    weights = "".join(chr(w) for w in ctx.collating_sequence.weights)
    arguments = tuple(a for f in fields for a in sort_field_arguments(f))
    _emit_call(
        ctx, stmt, _SORT_FILE, (stmt.file_name, record.byte_length, weights, *arguments)
    )


def lower_sort(
    ctx: EmitContext, stmt: SortStatement, materialised: MaterialisedSectionedLayout
) -> None:
    _open(ctx, stmt, OpenMode.OUTPUT, stmt.file_name, materialised)
    _fill(ctx, stmt, materialised)
    _emit_order(ctx, stmt, materialised)
    _drain(ctx, stmt, materialised)


def lower_release(
    ctx: EmitContext, stmt: ReleaseStatement, materialised: MaterialisedSectionedLayout
) -> None:
    lower_write(
        ctx,
        WriteStatement(
            record_name=stmt.record_name, from_field=stmt.from_field, span=stmt.span
        ),
        materialised,
    )


def lower_return(
    ctx: EmitContext, stmt: ReturnStatement, materialised: MaterialisedSectionedLayout
) -> None:
    lower_read(
        ctx,
        ReadStatement(
            file_name=stmt.file_name,
            into=stmt.into,
            at_end=list(stmt.at_end),
            not_at_end=list(stmt.not_at_end),
            span=stmt.span,
        ),
        materialised,
    )
