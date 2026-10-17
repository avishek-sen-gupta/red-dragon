"""I/O statement lowering — ACCEPT, OPEN, CLOSE, READ, WRITE, REWRITE, START, DELETE."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from cobol_asg.cobol_statements import (
    AcceptStatement,
    CloseStatement,
    CobolStatementType,
    DeleteStatement,
    FileControlEntry,
    OpenStatement,
    ReadStatement,
    RewriteStatement,
    StartStatement,
    WriteStatement,
)
from cobol_asg.file_enums import AccessMode, FileOrganization, OpenMode
from cobol_asg.ref_mod import RefModOperand
from cobol_asg.source_span import SourceSpan
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.fd_record_format import depending_on
from interpreter.cobol.field_resolution import whole_field_extent
from interpreter.cobol.file_facts import largest_record
from interpreter.cobol.program_object import program_name
from interpreter.cobol.relative_key import addressing_key, reported_key
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.status_class import StatusClass
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Label_,
    SetContinuation,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import resolve_binop
from interpreter.register import NO_REGISTER, Register

logger = logging.getLogger(__name__)

_SPACE = "\x40"
_PAST_THE_AREA = _SPACE
_CLOSE_BUILTINS = {
    False: FuncName("__cobol_close_file"),
    True: FuncName("__cobol_close_file_with_lock"),
}


def _program(ctx: EmitContext, *, span: SourceSpan | None) -> Register:
    return Register(str(ctx.const_to_reg(program_name(ctx._asg), span=span)))


def _emit_status_class(
    ctx: EmitContext, status_reg: Register, *, span: SourceSpan | None
) -> Register:
    first_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=first_reg,
            func_name=FuncName(BuiltinName.STRING_SLICE),
            args=(
                Register(str(status_reg)),
                Register(str(ctx.const_to_reg(0, span=span))),
                Register(str(ctx.const_to_reg(1, span=span))),
            ),
        ),
        span=span,
    )
    return first_reg


def _emit_skip_if_class(
    ctx: EmitContext,
    first_reg: Register,
    status_class: StatusClass,
    skip_lbl: CodeLabel,
    *,
    span: SourceSpan | None,
) -> None:
    match_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=match_reg,
            operator=resolve_binop("=="),
            left=first_reg,
            right=Register(str(ctx.const_to_reg(status_class.value, span=span))),
        ),
        span=span,
    )
    next_lbl = ctx.fresh_label("use_check")
    ctx.emit_inst(
        BranchIf(cond_reg=match_reg, branch_targets=(skip_lbl, next_lbl)), span=span
    )
    ctx.emit_inst(Label_(label=next_lbl), span=span)


def _emit_conditional_use_perform(
    ctx: EmitContext,
    status_reg: Register,
    section: str,
    handled: Sequence[StatusClass],
    *,
    span: SourceSpan | None,
) -> None:
    """Emit: unless the status is successful or of a class the statement's own
    AT END / INVALID KEY phrase handles, PERFORM the USE section and return to
    the point of the I/O verb."""
    first_reg = _emit_status_class(ctx, status_reg, span=span)
    skip_lbl = ctx.fresh_label("use_skip")
    _ = [
        _emit_skip_if_class(ctx, first_reg, status_class, skip_lbl, span=span)
        for status_class in (StatusClass.SUCCESSFUL, *handled)
    ]
    ret_lbl = ctx.fresh_label("use_return")
    ctx.emit_inst(
        SetContinuation(name=ctx.procedures.section_end(section), target_label=ret_lbl),
        span=span,
    )
    ctx.emit_inst(Branch(label=ctx.procedures.section(section)), span=span)
    ctx.emit_inst(Label_(label=ret_lbl), span=span)
    ctx.emit_inst(Branch(label=skip_lbl), span=span)
    ctx.emit_inst(Label_(label=skip_lbl), span=span)


def handled_classes(at_end: bool, invalid_key: bool) -> tuple[StatusClass, ...]:
    """The status classes a statement's own AT END / INVALID KEY phrase handles."""
    return (
        *((StatusClass.AT_END,) if at_end else ()),
        *((StatusClass.INVALID_KEY,) if invalid_key else ()),
    )


def emit_use_trigger(
    ctx: EmitContext,
    file_name: str,
    status_reg: Register,
    handled: Sequence[StatusClass],
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    """Inject a conditional PERFORM of the matching USE declarative when an I/O
    verb returns an error/exception status that the statement's own AT END /
    INVALID KEY phrase does not handle."""
    section = ctx.use_by_file.get(file_name.upper(), "") or ctx.use_global or ""
    if section:
        _emit_conditional_use_perform(ctx, status_reg, section, handled, span=span)
        return
    if not ctx.use_by_mode:
        return
    # Open-mode scoped: pick the USE section matching this file's CURRENT open
    # mode — a runtime fact, queried via __cobol_file_open_mode.
    mode_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=mode_reg,
            func_name=FuncName("__cobol_file_open_mode"),
            args=(
                Register(str(ctx.const_to_reg(file_name, span=span))),
                _program(ctx, span=span),
            ),
        ),
        span=span,
    )
    for mode_key, sec in ctx.use_by_mode.items():
        match_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=match_reg,
                operator=resolve_binop("=="),
                left=mode_reg,
                right=Register(str(ctx.const_to_reg(mode_key, span=span))),
            ),
            span=span,
        )
        do_lbl = ctx.fresh_label("use_mode_do")
        next_lbl = ctx.fresh_label("use_mode_next")
        ctx.emit_inst(
            BranchIf(cond_reg=match_reg, branch_targets=(do_lbl, next_lbl)), span=span
        )
        ctx.emit_inst(Label_(label=do_lbl), span=span)
        _emit_conditional_use_perform(ctx, status_reg, sec, handled, span=span)
        ctx.emit_inst(Branch(label=next_lbl), span=span)
        ctx.emit_inst(Label_(label=next_lbl), span=span)


def _emit_open_use_trigger(
    ctx: EmitContext,
    file_name: str,
    mode: OpenMode,
    status_reg: Register,
    *,
    span: SourceSpan | None,
) -> None:
    """A failed OPEN leaves the file closed, so an open-mode USE is chosen by the
    mode the OPEN attempted, not by the file's current mode."""
    section = (
        ctx.use_by_file.get(file_name.upper(), "")
        or ctx.use_global
        or ctx.use_by_mode.get(mode.value, "")
    )
    if not section:
        return
    _emit_conditional_use_perform(ctx, status_reg, section, (), span=span)


def lower_accept(
    ctx: EmitContext,
    stmt: AcceptStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ACCEPT target [FROM device] — read input via __cobol_accept and store it
    unedited, as characters over the receiver's bytes."""
    span = stmt.span
    if not ctx.has_field(stmt.target.name, materialised):
        _emit_accept_call(ctx, stmt, 0)
        return
    target_ref, target_rr = ctx.resolve_field_ref(
        stmt.target.name,
        materialised,
        stmt.target.qualifiers,
        subscripts=stmt.target.subscripts,
        span=span,
    )
    result_reg = _emit_accept_call(ctx, stmt, target_ref.fl.byte_length)
    str_reg = ctx.emit_to_string(result_reg, span=span)
    ctx.emit_encode_and_write(
        target_rr,
        target_ref.fl.as_characters(),
        str_reg,
        target_ref.offset_reg,
        extent=target_ref.extent,
        span=span,
    )
    logger.info("ACCEPT %s FROM %s", stmt.target.name, stmt.from_device)


def _emit_accept_call(ctx: EmitContext, stmt: AcceptStatement, length: int) -> Register:
    span = stmt.span
    device_reg = ctx.const_to_reg(stmt.from_device, span=span)
    length_reg = ctx.const_to_reg(length, span=span)
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName("__cobol_accept"),
            args=(Register(str(device_reg)), Register(str(length_reg))),
        ),
        span=span,
    )
    return result_reg


def _lower_open_file(
    ctx: EmitContext,
    filename: str,
    mode: OpenMode,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    raw_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=raw_reg,
            func_name=FuncName("__cobol_open_file"),
            args=(
                Register(str(ctx.const_to_reg(filename, span=span))),
                Register(str(ctx.const_to_reg(mode.value, span=span))),
                _program(ctx, span=span),
            ),
        ),
        span=span,
    )
    status_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=status_reg,
            func_name=FuncName("__cobol_io_status"),
            args=(Register(str(raw_reg)), _program(ctx, span=span)),
        ),
        span=span,
    )
    ctx.emit_file_status_update(filename, status_reg, materialised, span=span)
    _emit_open_use_trigger(ctx, filename, mode, status_reg, span=span)
    logger.info("OPEN %s %s", mode.value, filename)


def lower_open(
    ctx: EmitContext,
    stmt: OpenStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """OPEN [mode file1 ...] ... — emit __cobol_open_file per file."""
    _ = [
        _lower_open_file(ctx, filename, mode, materialised, span=stmt.span)
        for mode, files in stmt.mode_groups
        for filename in files
    ]


def lower_close(
    ctx: EmitContext,
    stmt: CloseStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CLOSE file1 file2 ... — close files via __cobol_close_file."""
    span = stmt.span
    for filename in stmt.files:
        fn_reg = ctx.const_to_reg(filename, span=span)
        raw_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=raw_reg,
                func_name=_CLOSE_BUILTINS[filename in stmt.with_lock],
                args=(
                    Register(str(fn_reg)),
                    _program(ctx, span=span),
                ),
            ),
            span=span,
        )
        status_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=status_reg,
                func_name=FuncName("__cobol_io_status"),
                args=(
                    Register(str(raw_reg)),
                    _program(ctx, span=span),
                ),
            ),
            span=span,
        )
        ctx.emit_file_status_update(filename, status_reg, materialised, span=span)
        # CLOSE has no AT END / INVALID KEY clause, so a USE declarative fires
        # on a non-success close status (red-dragon-m0oa.8).
        emit_use_trigger(ctx, filename, status_reg, (), materialised, span=span)
        logger.info("CLOSE %s", filename)


def _emit_key_text(
    ctx: EmitContext,
    key: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    if not materialised.has_field(key.name):
        return Register(str(ctx.const_to_reg("", span=span)))
    key_ref, key_rr = ctx.resolve_field_ref(
        key.name, materialised, key.qualifiers, key.subscripts, span=span
    )
    key_val_reg = ctx.emit_decode_field(
        key_rr, key_ref.fl, key_ref.offset_reg, extent=key_ref.extent, span=span
    )
    return ctx.emit_to_string(key_val_reg, span=span)


def _emit_record_number_report(
    ctx: EmitContext,
    raw_reg: Register,
    status_reg: Register,
    key: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    """After a successful sequential READ or WRITE of a relative file, MOVE the
    record number it used to the RELATIVE KEY."""
    if not materialised.has_field(key.name):
        return
    number_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=number_reg,
            func_name=FuncName("__cobol_io_record_number"),
            args=(raw_reg, _program(ctx, span=span)),
        ),
        span=span,
    )
    _emit_store_if_successful(ctx, status_reg, number_reg, key, materialised, span=span)


def _emit_record_length_report(
    ctx: EmitContext,
    data_reg: Register,
    status_reg: Register,
    file_name: str,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    item = RefModOperand(name=depending_on(ctx._asg, file_name))
    if not materialised.has_field(item.name):
        return
    length_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=length_reg,
            func_name=FuncName(BuiltinName.LENGTH),
            args=(data_reg,),
        ),
        span=span,
    )
    _emit_store_if_successful(
        ctx, status_reg, length_reg, item, materialised, span=span
    )


def _emit_record_of_its_length(
    ctx: EmitContext,
    data_reg: Register,
    file_name: str,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    item = RefModOperand(name=depending_on(ctx._asg, file_name))
    if not materialised.has_field(item.name):
        return data_reg
    item_ref, item_rr = ctx.resolve_field_ref(item.name, materialised, span=span)
    length_reg = ctx.emit_decode_field(
        item_rr, item_ref.fl, item_ref.offset_reg, extent=item_ref.extent, span=span
    )
    area_ref, area_rr = ctx.resolve_field_ref(
        largest_record(ctx._asg, file_name, materialised), materialised, span=span
    )
    area_reg = ctx.emit_read_region_raw(
        area_rr, area_ref.fl, area_ref.offset_reg, extent=area_ref.extent, span=span
    )
    overlong_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=overlong_reg,
            func_name=FuncName(BuiltinName.STRING_CONCAT_PAIR),
            args=(
                area_reg,
                Register(str(ctx.const_to_reg(_PAST_THE_AREA, span=span))),
            ),
        ),
        span=span,
    )
    record_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=record_reg,
            func_name=FuncName(BuiltinName.STRING_SLICE),
            args=(
                overlong_reg,
                Register(str(ctx.const_to_reg(0, span=span))),
                Register(str(length_reg)),
            ),
        ),
        span=span,
    )
    return record_reg


def _emit_read_into(
    ctx: EmitContext,
    status_reg: Register,
    data_reg: Register,
    into: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    if not (into.name and materialised.has_field(into.name)):
        return
    into_ref, into_rr = ctx.resolve_field_ref(
        into.name, materialised, into.qualifiers, into.subscripts, span=span
    )
    filled_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=filled_reg,
            func_name=FuncName(BuiltinName.STRING_CONCAT_PAIR),
            args=(
                data_reg,
                Register(
                    str(ctx.const_to_reg(_SPACE * into_ref.fl.byte_length, span=span))
                ),
            ),
        ),
        span=span,
    )
    skip_lbl = _emit_branch_if_successful(ctx, status_reg, span=span)
    ctx.emit_write_region_raw(
        into_rr,
        into_ref.fl,
        filled_reg,
        into_ref.offset_reg,
        extent=into_ref.extent,
        span=span,
    )
    ctx.emit_inst(Branch(label=skip_lbl), span=span)
    ctx.emit_inst(Label_(label=skip_lbl), span=span)


def _emit_branch_if_successful(
    ctx: EmitContext, status_reg: Register, *, span: SourceSpan | None
) -> CodeLabel:
    ok_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=ok_reg,
            operator=resolve_binop("=="),
            left=_emit_status_class(ctx, status_reg, span=span),
            right=Register(
                str(ctx.const_to_reg(StatusClass.SUCCESSFUL.value, span=span))
            ),
        ),
        span=span,
    )
    store_lbl = ctx.fresh_label("io_report_store")
    skip_lbl = ctx.fresh_label("io_report_skip")
    ctx.emit_inst(
        BranchIf(cond_reg=ok_reg, branch_targets=(store_lbl, skip_lbl)), span=span
    )
    ctx.emit_inst(Label_(label=store_lbl), span=span)
    return skip_lbl


def _emit_store_if_successful(
    ctx: EmitContext,
    status_reg: Register,
    value_reg: Register,
    target: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    skip_lbl = _emit_branch_if_successful(ctx, status_reg, span=span)
    target_ref, target_rr = ctx.resolve_field_ref(
        target.name, materialised, target.qualifiers, target.subscripts, span=span
    )
    ctx.emit_encode_and_write(
        target_rr,
        target_ref.fl,
        ctx.emit_to_string(value_reg, span=span),
        target_ref.offset_reg,
        extent=target_ref.extent,
        span=span,
    )
    ctx.emit_inst(Branch(label=skip_lbl), span=span)
    ctx.emit_inst(Label_(label=skip_lbl), span=span)


def _read_key_reg(
    ctx: EmitContext,
    stmt: ReadStatement,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    entry = _file_entries(ctx).get(
        stmt.file_name, FileControlEntry(file_name=stmt.file_name)
    )
    if entry.organization is FileOrganization.INDEXED:
        return _indexed_read_key_reg(ctx, entry, stmt, materialised)
    return _emit_key_text(
        ctx,
        (
            stmt.key
            if stmt.key.name
            else addressing_key(ctx._asg, stmt.file_name, stmt.next_record)
        ),
        materialised,
        span=stmt.span,
    )


def _indexed_read_key_reg(
    ctx: EmitContext,
    entry: FileControlEntry,
    stmt: ReadStatement,
    materialised: MaterialisedSectionedLayout,
) -> Register:
    span = stmt.span
    sequential = entry.access_mode is AccessMode.SEQUENTIAL or stmt.next_record
    key = stmt.key if stmt.key.name else entry.record_key
    if sequential or not materialised.has_field(key.name):
        return Register(str(ctx.const_to_reg("", span=span)))
    return _key_value_reg(ctx, entry.organization, key, materialised, span=span)


def lower_read(
    ctx: EmitContext,
    stmt: ReadStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """READ file [INTO target] [KEY k] [AT END ...] [INVALID KEY ...] — with IOResult branching."""
    span = stmt.span
    fn_reg = ctx.const_to_reg(stmt.file_name, span=span)

    key_str_reg = _read_key_reg(ctx, stmt, materialised)

    raw_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=raw_reg,
            func_name=FuncName("__cobol_read_record"),
            args=(
                Register(str(fn_reg)),
                Register(str(key_str_reg)),
                _program(ctx, span=span),
            ),
        ),
        span=span,
    )

    status_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=status_reg,
            func_name=FuncName("__cobol_io_status"),
            args=(
                Register(str(raw_reg)),
                _program(ctx, span=span),
            ),
        ),
        span=span,
    )
    ctx.emit_file_status_update(stmt.file_name, status_reg, materialised, span=span)
    _emit_record_number_report(
        ctx,
        raw_reg,
        status_reg,
        reported_key(ctx._asg, stmt.file_name, stmt.next_record),
        materialised,
        span=span,
    )
    emit_use_trigger(
        ctx,
        stmt.file_name,
        status_reg,
        handled_classes(bool(stmt.at_end), bool(stmt.invalid_key)),
        materialised,
        span=span,
    )

    data_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=data_reg,
            func_name=FuncName("__cobol_io_data"),
            args=(
                Register(str(raw_reg)),
                _program(ctx, span=span),
            ),
        ),
        span=span,
    )
    _emit_record_length_report(
        ctx, data_reg, status_reg, stmt.file_name, materialised, span=span
    )

    # Write data into file section region via the FD record name for this file
    rec_name = largest_record(ctx._asg, stmt.file_name, materialised)
    if rec_name:
        try:
            file_fl, file_rr, file_region = materialised.resolve_with_region(rec_name)
            # Byte-faithful: land the file's raw bytes into the FD record region
            # verbatim (data_reg is a LATIN1 identity str of the record bytes),
            # preserving binary subfields (red-dragon-zwzg).
            #
            # The whole-field extent is exact here: READ lands a whole record at
            # the FD record's own offset, with no subscript. The region comes
            # from resolve_with_region rather than being assumed — an FD record
            # resolves to FILE, and a FILE extent must never be recorded as
            # WORKING-STORAGE or it would alias nothing at all.
            ctx.emit_write_region_raw(
                file_rr,
                file_fl,
                data_reg,
                NO_REGISTER,
                extent=whole_field_extent(file_fl, file_region),
                span=span,
            )
        except KeyError:
            pass

    _emit_read_into(ctx, status_reg, data_reg, stmt.into, materialised, span=span)

    after_label = ctx.fresh_label("read_after")
    has_at_end = bool(stmt.at_end or stmt.not_at_end)
    has_inv_key = bool(stmt.invalid_key or stmt.not_invalid_key)

    if has_at_end:
        at_end_lbl = ctx.fresh_label("read_at_end")
        ok_lbl = ctx.fresh_label("read_ok")
        cond_reg = ctx.fresh_reg()
        at_end_class = ctx.const_to_reg(StatusClass.AT_END.value, span=span)
        ctx.emit_inst(
            Binop(
                result_reg=cond_reg,
                operator=resolve_binop("=="),
                left=_emit_status_class(ctx, status_reg, span=span),
                right=Register(str(at_end_class)),
            ),
            span=span,
        )
        ctx.emit_inst(
            BranchIf(cond_reg=cond_reg, branch_targets=(at_end_lbl, ok_lbl)),
            span=span,
        )
        ctx.emit_inst(Label_(label=at_end_lbl), span=span)
        [ctx.lower_statement(s, materialised) for s in stmt.at_end]
        ctx.emit_inst(Branch(label=after_label), span=span)
        ctx.emit_inst(Label_(label=ok_lbl), span=span)
        [ctx.lower_statement(s, materialised) for s in stmt.not_at_end]
        ctx.emit_inst(Branch(label=after_label), span=span)

    if has_inv_key:
        inv_lbl = ctx.fresh_label("read_inv_key")
        not_inv_lbl = ctx.fresh_label("read_not_inv")
        inv_cond_reg = ctx.fresh_reg()
        invalid_key_class = ctx.const_to_reg(StatusClass.INVALID_KEY.value, span=span)
        ctx.emit_inst(
            Binop(
                result_reg=inv_cond_reg,
                operator=resolve_binop("=="),
                left=_emit_status_class(ctx, status_reg, span=span),
                right=Register(str(invalid_key_class)),
            ),
            span=span,
        )
        ctx.emit_inst(
            BranchIf(cond_reg=inv_cond_reg, branch_targets=(inv_lbl, not_inv_lbl)),
            span=span,
        )
        ctx.emit_inst(Label_(label=inv_lbl), span=span)
        [ctx.lower_statement(s, materialised) for s in stmt.invalid_key]
        ctx.emit_inst(Branch(label=after_label), span=span)
        ctx.emit_inst(Label_(label=not_inv_lbl), span=span)
        [ctx.lower_statement(s, materialised) for s in stmt.not_invalid_key]
        ctx.emit_inst(Branch(label=after_label), span=span)

    ctx.emit_inst(Label_(label=after_label), span=span)
    logger.info("READ %s INTO %s", stmt.file_name, stmt.into.name or "(none)")


def _emit_invalid_key_branch(
    ctx: EmitContext,
    status_reg: Register,
    file_name: str,
    invalid_key: Sequence[CobolStatementType],
    not_invalid_key: Sequence[CobolStatementType],
    materialised: MaterialisedSectionedLayout,
    after_label: object,
    *,
    span: SourceSpan | None,
) -> None:
    if not (invalid_key or not_invalid_key):
        return
    inv_lbl = ctx.fresh_label("inv_key")
    not_inv_lbl = ctx.fresh_label("not_inv_key")
    cond_reg = ctx.fresh_reg()
    invalid_key_class = ctx.const_to_reg(StatusClass.INVALID_KEY.value, span=span)
    ctx.emit_inst(
        Binop(
            result_reg=cond_reg,
            operator=resolve_binop("=="),
            left=_emit_status_class(ctx, status_reg, span=span),
            right=Register(str(invalid_key_class)),
        ),
        span=span,
    )
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(inv_lbl, not_inv_lbl)), span=span
    )
    ctx.emit_inst(Label_(label=inv_lbl), span=span)
    [ctx.lower_statement(s, materialised) for s in invalid_key]
    ctx.emit_inst(Branch(label=after_label), span=span)  # type: ignore[arg-type]
    ctx.emit_inst(Label_(label=not_inv_lbl), span=span)
    [ctx.lower_statement(s, materialised) for s in not_invalid_key]
    ctx.emit_inst(Branch(label=after_label), span=span)  # type: ignore[arg-type]


def _write_source_reg(
    ctx: EmitContext,
    from_field: RefModOperand,
    record_name: str,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    """Resolve the byte-faithful data register for WRITE/REWRITE.

    The file holds the record area's raw byte-image (regions are EBCDIC), so the
    data shipped to the provider is the record region's verbatim bytes — read via
    LATIN1 identity so binary subfields (COMP-3/COMP) survive unchanged
    (red-dragon-zwzg). `WRITE rec FROM fld` is COBOL `MOVE fld TO rec; WRITE rec`:
    emit the MOVE into the record region first, then read the region raw.

    Only when `record_name` is not a known FD record do we fall back to the bare
    name as a string constant (defensive parity with the prior behaviour for
    feeders that never register the record).
    """
    if not ctx.has_field(record_name, materialised):
        return ctx.const_to_reg(from_field.name or record_name, span=span)
    if from_field.name:
        from cobol_asg.cobol_statements import MoveStatement

        ctx.lower_statement(
            MoveStatement(
                source=from_field,
                targets=[RefModOperand(name=record_name)],
                span=span,
            ),
            materialised,
        )
    ref, rr = ctx.resolve_field_ref(record_name, materialised, span=span)
    return ctx.emit_read_region_raw(
        rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
    )


def lower_write(
    ctx: EmitContext,
    stmt: WriteStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """WRITE record-name [FROM field] [INVALID KEY ...] — write record via __cobol_write_record."""
    span = stmt.span
    file_name = ctx._asg.file_record_to_select.get(
        stmt.record_name.upper(), stmt.record_name
    )
    data_reg = _emit_record_of_its_length(
        ctx,
        _write_source_reg(
            ctx, stmt.from_field, stmt.record_name, materialised, span=span
        ),
        file_name,
        materialised,
        span=span,
    )
    fn_reg = ctx.const_to_reg(file_name, span=span)
    key_reg = _emit_key_text(
        ctx, addressing_key(ctx._asg, file_name, False), materialised, span=span
    )
    raw_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=raw_reg,
            func_name=FuncName("__cobol_write_record"),
            args=(
                Register(str(fn_reg)),
                Register(str(data_reg)),
                key_reg,
                _program(ctx, span=span),
            ),
        ),
        span=span,
    )
    status_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=status_reg,
            func_name=FuncName("__cobol_io_status"),
            args=(
                Register(str(raw_reg)),
                _program(ctx, span=span),
            ),
        ),
        span=span,
    )
    ctx.emit_file_status_update(file_name, status_reg, materialised, span=span)
    _emit_record_number_report(
        ctx,
        raw_reg,
        status_reg,
        reported_key(ctx._asg, file_name, False),
        materialised,
        span=span,
    )
    emit_use_trigger(
        ctx,
        file_name,
        status_reg,
        handled_classes(False, bool(stmt.invalid_key)),
        materialised,
        span=span,
    )
    after_label = ctx.fresh_label("write_after")
    _emit_invalid_key_branch(
        ctx,
        status_reg,
        stmt.record_name,
        stmt.invalid_key,
        stmt.not_invalid_key,
        materialised,
        after_label,
        span=span,
    )
    ctx.emit_inst(Label_(label=after_label), span=span)
    logger.info("WRITE %s FROM %s", stmt.record_name, stmt.from_field.name or "(none)")


def lower_rewrite(
    ctx: EmitContext,
    stmt: RewriteStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """REWRITE record-name [FROM field] [INVALID KEY ...] — rewrite via __cobol_rewrite_record."""
    span = stmt.span
    file_name = ctx._asg.file_record_to_select.get(
        stmt.record_name.upper(), stmt.record_name
    )
    data_reg = _emit_record_of_its_length(
        ctx,
        _write_source_reg(
            ctx, stmt.from_field, stmt.record_name, materialised, span=span
        ),
        file_name,
        materialised,
        span=span,
    )
    fn_reg = ctx.const_to_reg(file_name, span=span)
    key_reg = _emit_key_text(
        ctx, addressing_key(ctx._asg, file_name, False), materialised, span=span
    )
    raw_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=raw_reg,
            func_name=FuncName("__cobol_rewrite_record"),
            args=(
                Register(str(fn_reg)),
                Register(str(data_reg)),
                key_reg,
                _program(ctx, span=span),
            ),
        ),
        span=span,
    )
    status_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=status_reg,
            func_name=FuncName("__cobol_io_status"),
            args=(
                Register(str(raw_reg)),
                _program(ctx, span=span),
            ),
        ),
        span=span,
    )
    ctx.emit_file_status_update(file_name, status_reg, materialised, span=span)
    emit_use_trigger(
        ctx,
        file_name,
        status_reg,
        handled_classes(False, bool(stmt.invalid_key)),
        materialised,
        span=span,
    )
    after_label = ctx.fresh_label("rewrite_after")
    _emit_invalid_key_branch(
        ctx,
        status_reg,
        file_name,
        stmt.invalid_key,
        stmt.not_invalid_key,
        materialised,
        after_label,
        span=span,
    )
    ctx.emit_inst(Label_(label=after_label), span=span)
    logger.info(
        "REWRITE %s FROM %s", stmt.record_name, stmt.from_field.name or "(none)"
    )


def lower_start(
    ctx: EmitContext,
    stmt: StartStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """START file-name [KEY relop key] [INVALID KEY ...] — position via __cobol_start_file."""
    span = stmt.span
    fn_reg = ctx.const_to_reg(stmt.file_name, span=span)
    key_reg = _start_key_reg(ctx, stmt, materialised, span=span)
    relop_reg = ctx.const_to_reg(stmt.relop or "=", span=span)
    raw_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=raw_reg,
            func_name=FuncName("__cobol_start_file"),
            args=(
                Register(str(fn_reg)),
                Register(str(key_reg)),
                Register(str(relop_reg)),
                _program(ctx, span=span),
            ),
        ),
        span=span,
    )
    status_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=status_reg,
            func_name=FuncName("__cobol_io_status"),
            args=(
                Register(str(raw_reg)),
                _program(ctx, span=span),
            ),
        ),
        span=span,
    )
    ctx.emit_file_status_update(stmt.file_name, status_reg, materialised, span=span)
    emit_use_trigger(
        ctx,
        stmt.file_name,
        status_reg,
        handled_classes(False, bool(stmt.invalid_key)),
        materialised,
        span=span,
    )
    after_label = ctx.fresh_label("start_after")
    _emit_invalid_key_branch(
        ctx,
        status_reg,
        stmt.file_name,
        stmt.invalid_key,
        stmt.not_invalid_key,
        materialised,
        after_label,
        span=span,
    )
    ctx.emit_inst(Label_(label=after_label), span=span)
    logger.info(
        "START %s KEY %s %s", stmt.file_name, stmt.relop, stmt.key.name or "(none)"
    )


def _file_entries(ctx: EmitContext) -> dict[str, FileControlEntry]:
    return {entry.file_name: entry for entry in ctx._asg.file_control}


def _file_key(entry: FileControlEntry) -> RefModOperand:
    if entry.organization is FileOrganization.RELATIVE:
        return entry.relative_key
    return entry.record_key


def _delete_key_reg(
    ctx: EmitContext,
    file_name: str,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    entries = _file_entries(ctx)
    if (
        file_name not in entries
        or entries[file_name].access_mode is AccessMode.SEQUENTIAL
    ):
        return ctx.const_to_reg("", span=span)
    entry = entries[file_name]
    return _key_value_reg(
        ctx, entry.organization, _file_key(entry), materialised, span=span
    )


def _start_key_reg(
    ctx: EmitContext,
    stmt: StartStatement,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    entries = _file_entries(ctx)
    if (
        stmt.file_name not in entries
        or entries[stmt.file_name].organization is FileOrganization.SEQUENTIAL
    ):
        return ctx.const_to_reg("", span=span)
    entry = entries[stmt.file_name]
    key = stmt.key if stmt.key.name else _file_key(entry)
    return _key_value_reg(ctx, entry.organization, key, materialised, span=span)


def _key_value_reg(
    ctx: EmitContext,
    organization: FileOrganization,
    key: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    key_ref, key_rr = ctx.resolve_field_ref(
        key.name, materialised, key.qualifiers, key.subscripts, span=span
    )
    if organization is FileOrganization.RELATIVE:
        value_reg = ctx.emit_decode_field(
            key_rr, key_ref.fl, key_ref.offset_reg, extent=key_ref.extent, span=span
        )
        return ctx.emit_to_string(value_reg, span=span)
    return ctx.emit_read_region_raw(
        key_rr, key_ref.fl, key_ref.offset_reg, extent=key_ref.extent, span=span
    )


def lower_delete(
    ctx: EmitContext,
    stmt: DeleteStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """DELETE file-name [INVALID KEY ...] — delete record via __cobol_delete_record."""
    span = stmt.span
    fn_reg = ctx.const_to_reg(stmt.file_name, span=span)
    key_reg = _delete_key_reg(ctx, stmt.file_name, materialised, span=span)
    raw_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=raw_reg,
            func_name=FuncName("__cobol_delete_record"),
            args=(
                Register(str(fn_reg)),
                Register(str(key_reg)),
                _program(ctx, span=span),
            ),
        ),
        span=span,
    )
    status_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=status_reg,
            func_name=FuncName("__cobol_io_status"),
            args=(
                Register(str(raw_reg)),
                _program(ctx, span=span),
            ),
        ),
        span=span,
    )
    ctx.emit_file_status_update(stmt.file_name, status_reg, materialised, span=span)
    emit_use_trigger(
        ctx,
        stmt.file_name,
        status_reg,
        handled_classes(False, bool(stmt.invalid_key)),
        materialised,
        span=span,
    )
    after_label = ctx.fresh_label("delete_after")
    _emit_invalid_key_branch(
        ctx,
        status_reg,
        stmt.file_name,
        stmt.invalid_key,
        stmt.not_invalid_key,
        materialised,
        after_label,
        span=span,
    )
    ctx.emit_inst(Label_(label=after_label), span=span)
    logger.info("DELETE %s", stmt.file_name)
