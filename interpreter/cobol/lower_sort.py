"""SORT lowering: the sort file is a sequential work file that the USING files are
copied into, that is put in key order, and that is copied to the GIVING files."""

from __future__ import annotations

from cobol_asg.cobol_statements import CloseStatement, OpenStatement, SortStatement
from cobol_asg.file_enums import OpenMode
from cobol_asg.sort_key import SortKey
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_io import lower_close, lower_open
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


def _give(
    ctx: EmitContext,
    stmt: SortStatement,
    filename: str,
    materialised: MaterialisedSectionedLayout,
) -> None:
    _open(ctx, stmt, OpenMode.INPUT, stmt.file_name, materialised)
    _transfer(ctx, stmt, filename, materialised, (_SORT_GIVING, OpenMode.OUTPUT))
    _close(ctx, stmt, stmt.file_name, materialised)


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
    for filename in stmt.using:
        _transfer(ctx, stmt, filename, materialised, (_SORT_USING, OpenMode.INPUT))
    _emit_order(ctx, stmt, materialised)
    for given in stmt.giving:
        _give(ctx, stmt, given, materialised)
