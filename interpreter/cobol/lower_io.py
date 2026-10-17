"""I/O statement lowering — ACCEPT, OPEN, CLOSE, READ, WRITE, REWRITE, START, DELETE."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from functools import partial

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
from interpreter.cobol.fd_record_format import (
    depending_on,
    minimum_length,
    records_vary,
)
from interpreter.cobol.field_resolution import whole_field_extent
from interpreter.cobol.file_facts import (
    largest_record,
    prime_key,
    record_area,
    relative_key_digits,
)
from interpreter.cobol.file_logic_status import FileLogicStatus
from interpreter.cobol.file_position import FilePosition
from interpreter.cobol.file_state import file_state
from interpreter.cobol.file_verb_ir import FileVerbIr, Refusal, VerbOutcome
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.prime_key import PrimeKey
from interpreter.cobol.program_object import program_name
from interpreter.cobol.read_plan import ReadPlan
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
_READ_MODES = (OpenMode.INPUT, OpenMode.IO)
_SEQUENTIAL_WRITE_MODES = (OpenMode.OUTPUT, OpenMode.EXTEND)
_KEYED_WRITE_MODES = (OpenMode.OUTPUT, OpenMode.EXTEND, OpenMode.IO)


def _program(ctx: EmitContext, *, span: SourceSpan | None) -> Register:
    return Register(str(ctx.const_to_reg(program_name(ctx._asg), span=span)))


def _verb(ctx: EmitContext, file_name: str, *, span: SourceSpan | None) -> FileVerbIr:
    return FileVerbIr(
        IrEmitter(ctx, span),
        file_state(program_name(ctx._asg), file_name),
        _program(ctx, span=span),
    )


def _entry(ctx: EmitContext, file_name: str) -> FileControlEntry:
    return _file_entries(ctx).get(file_name, FileControlEntry(file_name=file_name))


def _sequential_access(entry: FileControlEntry) -> bool:
    return (
        entry.organization is FileOrganization.SEQUENTIAL
        or entry.access_mode is AccessMode.SEQUENTIAL
    )


def _write_modes(entry: FileControlEntry) -> tuple[OpenMode, ...]:
    if entry.organization is FileOrganization.SEQUENTIAL:
        return _SEQUENTIAL_WRITE_MODES
    return _KEYED_WRITE_MODES


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
    mode_reg = IrEmitter(ctx, span).load(
        file_state(program_name(ctx._asg), file_name).mode
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
    v = _verb(ctx, filename, span=span)
    outcome = v.outcome()
    v.guarded(
        (
            Refusal(v.open_, FileLogicStatus.ALREADY_OPEN),
            Refusal(v.locked, FileLogicStatus.CLOSED_WITH_LOCK),
        ),
        outcome,
        partial(_emit_open, v, outcome, mode, _entry(ctx, filename)),
        _nothing,
    )
    status_reg = v.e.load(outcome.status)
    ctx.emit_file_status_update(filename, status_reg, materialised, span=span)
    _emit_open_use_trigger(ctx, filename, mode, status_reg, span=span)
    logger.info("OPEN %s %s", mode.value, filename)


def _emit_open(
    v: FileVerbIr, outcome: VerbOutcome, mode: OpenMode, entry: FileControlEntry
) -> None:
    v.called(
        "__cobol_open_file", outcome, v.e.text(entry.file_name), v.e.text(mode.value)
    )
    _emit_optional_absent(v, outcome, mode, entry)
    v.when(v.successful(outcome), partial(_opened, v, mode))


def _opened(v: FileVerbIr, mode: OpenMode) -> None:
    v.set_mode(mode.value)
    v.set_position(FilePosition.NO_CURRENT_RECORD)
    v.e.store(v.state.last_key, v.e.text(""))


def _emit_optional_absent(
    v: FileVerbIr, outcome: VerbOutcome, mode: OpenMode, entry: FileControlEntry
) -> None:
    """An OPTIONAL file that is absent opens with 05: for INPUT as a file of no records,
    left uncreated; for I-O and EXTEND created, by opening it OUTPUT and closing it."""
    if not entry.optional or mode is OpenMode.OUTPUT:
        return
    v.when(
        v.status_is(outcome, FileLogicStatus.FILE_ABSENT),
        (
            partial(_absent_input, v, outcome)
            if mode is OpenMode.INPUT
            else partial(_created, v, outcome, mode, entry.file_name)
        ),
    )


def _absent_input(v: FileVerbIr, outcome: VerbOutcome) -> None:
    v.e.store(v.state.absent, v.e.bool_(True))
    v.set_status(outcome, FileLogicStatus.OPTIONAL_ABSENT)


def _created(
    v: FileVerbIr, outcome: VerbOutcome, mode: OpenMode, filename: str
) -> None:
    name = v.e.text(filename)
    v.e.call("__cobol_open_file", name, v.e.text(OpenMode.OUTPUT.value), v.program)
    v.e.call("__cobol_close_file", name, v.program)
    v.called("__cobol_open_file", outcome, name, v.e.text(mode.value))
    v.when(
        v.status_is(outcome, FileLogicStatus.PERMITTED),
        partial(v.set_status, outcome, FileLogicStatus.OPTIONAL_ABSENT),
    )


def _nothing() -> None:
    return


def _ignored(raw: Register) -> None:
    return


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
    _ = [
        _lower_close_file(
            ctx, filename, filename in stmt.with_lock, materialised, span=stmt.span
        )
        for filename in stmt.files
    ]


def _lower_close_file(
    ctx: EmitContext,
    filename: str,
    with_lock: bool,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    v = _verb(ctx, filename, span=span)
    outcome = v.outcome()
    v.guarded(
        (Refusal(v.closed, FileLogicStatus.NOT_OPEN),),
        outcome,
        partial(_emit_close, v, outcome, _entry(ctx, filename), with_lock),
        _nothing,
    )
    status_reg = v.e.load(outcome.status)
    ctx.emit_file_status_update(filename, status_reg, materialised, span=span)
    emit_use_trigger(ctx, filename, status_reg, (), materialised, span=span)
    logger.info("CLOSE %s", filename)


def _emit_close(
    v: FileVerbIr, outcome: VerbOutcome, entry: FileControlEntry, with_lock: bool
) -> None:
    v.unless_absent(
        entry.optional,
        partial(v.set_status, outcome, FileLogicStatus.PERMITTED),
        lambda: _ignored(
            v.called("__cobol_close_file", outcome, v.e.text(entry.file_name))
        ),
    )
    v.when(
        v.status_is(outcome, FileLogicStatus.PERMITTED),
        partial(_closed, v, with_lock),
    )


def _closed(v: FileVerbIr, with_lock: bool) -> None:
    v.set_mode("")
    v.e.store(v.state.locked, v.e.bool_(with_lock))
    v.e.store(v.state.absent, v.e.bool_(False))


def _emit_key_text(
    ctx: EmitContext,
    key: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    if not materialised.has_field(key.name):
        return Register(str(ctx.const_to_reg("", span=span)))
    return ctx.emit_to_string(
        _emit_key_value(ctx, key, materialised, span=span), span=span
    )


def _emit_key_value(
    ctx: EmitContext,
    key: RefModOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> Register:
    key_ref, key_rr = ctx.resolve_field_ref(
        key.name, materialised, key.qualifiers, key.subscripts, span=span
    )
    return ctx.emit_decode_field(
        key_rr, key_ref.fl, key_ref.offset_reg, extent=key_ref.extent, span=span
    )


def _emit_record_number_report(
    ctx: EmitContext,
    number_reg: Register,
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


def _sequential_read(
    ctx: EmitContext, stmt: ReadStatement, materialised: MaterialisedSectionedLayout
) -> bool:
    entry = _entry(ctx, stmt.file_name)
    if entry.organization is FileOrganization.INDEXED:
        key = stmt.key if stmt.key.name else entry.record_key
        sequential = entry.access_mode is AccessMode.SEQUENTIAL or stmt.next_record
        return sequential or not materialised.has_field(key.name)
    addressed = (
        stmt.key
        if stmt.key.name
        else addressing_key(ctx._asg, stmt.file_name, stmt.next_record)
    )
    return not materialised.has_field(addressed.name)


def _read_position(v: FileVerbIr, outcome: VerbOutcome) -> Register:
    e = v.e
    return e.choose(
        "read_position",
        e.text(FilePosition.CURRENT_RECORD.value),
        v.status_is(
            outcome, FileLogicStatus.PERMITTED, FileLogicStatus.DUPLICATES_FOLLOW
        ),
        lambda: e.choose(
            "read_position",
            e.text(FilePosition.AT_END.value),
            v.status_is(
                outcome, FileLogicStatus.AT_END, FileLogicStatus.RELATIVE_KEY_TOO_SMALL
            ),
            lambda: e.text(FilePosition.NO_CURRENT_RECORD.value),
        ),
    )


def _emit_relative_key_overflow(
    v: FileVerbIr, outcome: VerbOutcome, digits: int
) -> None:
    """A READ of a relative file whose record number has more digits than its RELATIVE
    KEY gives 14, and neither the record nor its number."""
    if not digits:
        return

    def overflowed() -> None:
        v.set_status(outcome, FileLogicStatus.RELATIVE_KEY_TOO_SMALL)
        v.e.store(outcome.data, v.e.text(""))
        v.e.store(outcome.number, v.e.int_(0))

    v.when(v.e.binop(">=", v.e.load(outcome.number), v.e.int_(10**digits)), overflowed)


def _emit_guarded_read(v: FileVerbIr, outcome: VerbOutcome, plan: ReadPlan) -> None:
    def present() -> None:
        raw = v.called(
            "__cobol_read_record", outcome, v.e.text(plan.file_name), plan.key
        )
        v.keep_record(raw, outcome)
        v.keep_number(raw, outcome)
        _emit_relative_key_overflow(v, outcome, plan.key_digits)
        _remember_key(v, v.e.load(outcome.data), plan.sequence)

    def perform() -> None:
        v.unless_absent(
            plan.optional,
            lambda: v.set_status(
                outcome,
                (
                    FileLogicStatus.AT_END
                    if plan.sequential
                    else FileLogicStatus.NOT_FOUND
                ),
            ),
            present,
        )
        v.e.store(v.state.position, _read_position(v, outcome))

    v.guarded(
        (
            Refusal(
                lambda: v.mode_is_not(*_READ_MODES),
                FileLogicStatus.READ_NOT_PERMITTED,
            ),
            *(
                (
                    Refusal(
                        lambda: v.position_is(FilePosition.AT_END),
                        FileLogicStatus.NO_NEXT_RECORD,
                    ),
                )
                if plan.sequential
                else ()
            ),
        ),
        outcome,
        perform,
        v.forget_current_record,
    )


def lower_read(
    ctx: EmitContext,
    stmt: ReadStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """READ file [INTO target] [KEY k] [AT END ...] [INVALID KEY ...] — with IOResult branching."""
    span = stmt.span
    key_str_reg = _read_key_reg(ctx, stmt, materialised)
    v = _verb(ctx, stmt.file_name, span=span)
    outcome = v.outcome()
    entry = _entry(ctx, stmt.file_name)
    _emit_guarded_read(
        v,
        outcome,
        ReadPlan(
            stmt.file_name,
            key_str_reg,
            _sequential_read(ctx, stmt, materialised),
            entry.optional,
            relative_key_digits(materialised, entry),
            _key_sequence(ctx, stmt.file_name, materialised),
        ),
    )
    status_reg = v.e.load(outcome.status)
    ctx.emit_file_status_update(stmt.file_name, status_reg, materialised, span=span)
    _emit_record_number_report(
        ctx,
        v.e.load(outcome.number),
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
    data_reg = v.e.load(outcome.data)
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


def _emit_guarded_update(
    v: FileVerbIr,
    outcome: VerbOutcome,
    call: tuple[str, tuple[Register, ...], Callable[[], None]],
    refusals: Sequence[Refusal],
) -> None:
    primitive, args, performed = call

    def perform() -> None:
        raw = v.called(primitive, outcome, *args)
        v.keep_number(raw, outcome)
        v.set_position(FilePosition.NO_CURRENT_RECORD)
        performed()

    v.guarded(refusals, outcome, perform, v.forget_current_record)


def _size_refusals(
    ctx: EmitContext,
    v: FileVerbIr,
    file_name: str,
    data_reg: Register,
    materialised: MaterialisedSectionedLayout,
) -> tuple[Refusal, ...]:
    """A variable-length record shorter than the file's smallest or longer than its
    largest record is a boundary violation, 44."""
    if not records_vary(ctx._asg, file_name):
        return ()
    smallest = minimum_length(ctx._asg, file_name)
    largest = next(
        (area.byte_length for area in record_area(ctx._asg, file_name, materialised)),
        0,
    )

    def outside() -> Register:
        size = v.e.call(BuiltinName.LENGTH, data_reg)
        short = v.e.binop("<", size, v.e.int_(smallest))
        return v.e.binop("or", short, v.e.binop(">", size, v.e.int_(largest)))

    return (Refusal(outside, FileLogicStatus.RECORD_SIZE_VIOLATION),)


def _boundary_refusals(
    v: FileVerbIr, key_values: Sequence[Register]
) -> tuple[Refusal, ...]:
    """A WRITE of a relative file at a record number below 1 is a boundary violation, 24."""
    return tuple(
        Refusal(
            lambda value=value: v.e.binop("<", value, v.e.int_(1)),
            FileLogicStatus.BOUNDARY_VIOLATION,
        )
        for value in key_values
    )


def _addressed_key_values(
    ctx: EmitContext,
    file_name: str,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> tuple[Register, ...]:
    key = addressing_key(ctx._asg, file_name, False)
    if not materialised.has_field(key.name):
        return ()
    return (_emit_key_value(ctx, key, materialised, span=span),)


def _key_sequence(
    ctx: EmitContext, file_name: str, materialised: MaterialisedSectionedLayout
) -> tuple[PrimeKey, ...]:
    """The prime key an indexed file in sequential access keeps in sequence by; none
    for any other file."""
    entry = _entry(ctx, file_name)
    indexed = entry.organization is FileOrganization.INDEXED
    if not (indexed and entry.access_mode is AccessMode.SEQUENTIAL):
        return ()
    return (
        prime_key(record_area(ctx._asg, file_name, materialised), materialised, entry),
    )


def _key_of(v: FileVerbIr, record: Register, key: PrimeKey) -> Register:
    return v.e.call(
        BuiltinName.STRING_SLICE, record, v.e.int_(key.offset), v.e.int_(key.length)
    )


def _sequence_refusals(
    v: FileVerbIr, record: Register, keys: Sequence[PrimeKey], operator: str
) -> tuple[Refusal, ...]:
    """In sequential access to an indexed file a WRITE whose prime key is below the last
    one written, or a REWRITE whose prime key differs from the record read, is 21."""
    return tuple(
        Refusal(
            lambda key=key: v.e.binop(
                operator, _key_of(v, record, key), v.e.load(v.state.last_key)
            ),
            FileLogicStatus.SEQUENCE_ERROR,
        )
        for key in keys
    )


def _remember_key(v: FileVerbIr, record: Register, keys: Sequence[PrimeKey]) -> None:
    _ = [v.e.store(v.state.last_key, _key_of(v, record, key)) for key in keys]


def _current_record_refusals(
    v: FileVerbIr, entry: FileControlEntry
) -> tuple[Refusal, ...]:
    return (
        Refusal(
            lambda: v.mode_is_not(OpenMode.IO), FileLogicStatus.UPDATE_NOT_PERMITTED
        ),
        *(
            (
                Refusal(
                    lambda: v.position_is_not(FilePosition.CURRENT_RECORD),
                    FileLogicStatus.NO_CURRENT_RECORD,
                ),
            )
            if _sequential_access(entry)
            else ()
        ),
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
    key_values = _addressed_key_values(ctx, file_name, materialised, span=span)
    key_reg = next(
        (ctx.emit_to_string(value, span=span) for value in key_values),
        Register(str(ctx.const_to_reg("", span=span))),
    )
    v = _verb(ctx, file_name, span=span)
    outcome = v.outcome()
    entry = _entry(ctx, file_name)
    sequence = _key_sequence(ctx, file_name, materialised)
    _emit_guarded_update(
        v,
        outcome,
        (
            "__cobol_write_record",
            (v.e.text(file_name), data_reg, key_reg),
            lambda: v.when(
                v.status_is(outcome, FileLogicStatus.PERMITTED),
                partial(_remember_key, v, data_reg, sequence),
            ),
        ),
        (
            Refusal(
                lambda: v.mode_is_not(*_write_modes(entry)),
                FileLogicStatus.WRITE_NOT_PERMITTED,
            ),
            *_size_refusals(ctx, v, file_name, data_reg, materialised),
            *_boundary_refusals(v, key_values),
            *_sequence_refusals(v, data_reg, sequence, "<"),
        ),
    )
    status_reg = v.e.load(outcome.status)
    ctx.emit_file_status_update(file_name, status_reg, materialised, span=span)
    _emit_record_number_report(
        ctx,
        v.e.load(outcome.number),
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
    key_reg = _emit_key_text(
        ctx, addressing_key(ctx._asg, file_name, False), materialised, span=span
    )
    v = _verb(ctx, file_name, span=span)
    outcome = v.outcome()
    _emit_guarded_update(
        v,
        outcome,
        ("__cobol_rewrite_record", (v.e.text(file_name), data_reg, key_reg), _nothing),
        (
            *_current_record_refusals(v, _entry(ctx, file_name)),
            *_size_refusals(ctx, v, file_name, data_reg, materialised),
            *_sequence_refusals(
                v, data_reg, _key_sequence(ctx, file_name, materialised), "!="
            ),
        ),
    )
    status_reg = v.e.load(outcome.status)
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
    key_reg = _start_key_reg(ctx, stmt, materialised, span=span)
    relop_reg = Register(str(ctx.const_to_reg(stmt.relop or "=", span=span)))
    v = _verb(ctx, stmt.file_name, span=span)
    outcome = v.outcome()
    optional = _entry(ctx, stmt.file_name).optional

    def perform() -> None:
        v.unless_absent(
            optional,
            lambda: v.set_status(outcome, FileLogicStatus.NOT_FOUND),
            lambda: _ignored(
                v.called(
                    "__cobol_start_file",
                    outcome,
                    v.e.text(stmt.file_name),
                    key_reg,
                    relop_reg,
                )
            ),
        )
        v.set_position(FilePosition.NO_CURRENT_RECORD)

    v.guarded(
        (
            Refusal(
                lambda: v.mode_is_not(*_READ_MODES),
                FileLogicStatus.READ_NOT_PERMITTED,
            ),
        ),
        outcome,
        perform,
        v.forget_current_record,
    )
    status_reg = v.e.load(outcome.status)
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
    key_reg = _delete_key_reg(ctx, stmt.file_name, materialised, span=span)
    v = _verb(ctx, stmt.file_name, span=span)
    outcome = v.outcome()
    _emit_guarded_update(
        v,
        outcome,
        ("__cobol_delete_record", (v.e.text(stmt.file_name), key_reg), _nothing),
        _current_record_refusals(v, _entry(ctx, stmt.file_name)),
    )
    status_reg = v.e.load(outcome.status)
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
