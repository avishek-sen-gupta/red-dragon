"""I/O statement lowering — ACCEPT, OPEN, CLOSE, READ, WRITE, REWRITE, START, DELETE."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from functools import partial

from cobol_asg.cobol_statements import (
    AcceptStatement,
    CloseStatement,
    DeleteStatement,
    FileControlEntry,
    MoveStatement,
    OpenStatement,
    ReadStatement,
    RewriteStatement,
    StartStatement,
    WriteStatement,
)
from cobol_asg.file_enums import AccessMode, FileOrganization, OpenMode
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.accept_fill import AcceptFill
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.fd_record_format import (
    depending_on,
    minimum_length,
    records_vary,
)
from interpreter.cobol.field_resolution import whole_field_extent
from interpreter.cobol.file_facts import (
    key_number,
    largest_record,
    prime_key,
    record_area,
    relative_key_digits,
)
from interpreter.cobol.file_logic_status import FileLogicStatus
from interpreter.cobol.file_position import FilePosition
from interpreter.cobol.file_state import file_state, file_state_of
from interpreter.cobol.file_verb_ir import (
    FileVerbIr,
    Refusal,
    VerbOutcome,
    emit_closed,
)
from interpreter.cobol.global_names import visible_file_entries, visible_record_files
from interpreter.cobol.invalid_key_phrases import InvalidKeyPhrases
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.lowering_scope import LoweringScope
from interpreter.cobol.prime_key import PrimeKey
from interpreter.cobol.program_object import entry_var, program_name, use_request_var
from interpreter.cobol.read_plan import ReadPlan
from interpreter.cobol.relative_key import addressing_key, reported_key
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.status_class import StatusClass
from interpreter.cobol.use_selection import NO_USE, UseProcedure, use_procedures
from interpreter.cobol.write_plan import WritePlan
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    CallWithMemory,
    Label_,
    NewArray,
    SetContinuation,
    StoreField,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import resolve_binop
from interpreter.register import NO_REGISTER, Register
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)

_SPACE = "\x40"
_PAST_THE_AREA = _SPACE
_READ_MODES = (OpenMode.INPUT, OpenMode.IO)
_SEQUENTIAL_WRITE_MODES = (OpenMode.OUTPUT, OpenMode.EXTEND)
_KEYED_WRITE_MODES = (OpenMode.OUTPUT, OpenMode.EXTEND, OpenMode.IO)


def _program(scope: LoweringScope) -> Register:
    return Register(
        str(scope.ctx.const_to_reg(program_name(scope.ctx._asg), span=scope.span))
    )


def _verb(scope: LoweringScope, file_name: str) -> FileVerbIr:
    return FileVerbIr(
        scope.emitter,
        file_state_of(scope.ctx._asg, file_name),
        _program(scope),
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


def _emit_status_class(scope: LoweringScope, status_reg: Register) -> Register:
    ctx, span = scope.ctx, scope.span
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
    scope: LoweringScope,
    first_reg: Register,
    status_class: StatusClass,
    skip_lbl: CodeLabel,
) -> None:
    ctx, span = scope.ctx, scope.span
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


def _emit_conditional_use(
    scope: LoweringScope,
    status_reg: Register,
    use: UseProcedure,
    handled: Sequence[StatusClass],
) -> None:
    """Emit: unless the status is successful or of a class the statement's own
    AT END / INVALID KEY phrase handles, run the USE section and return to the
    point of the I/O verb."""
    ctx = scope.ctx
    first_reg = _emit_status_class(scope, status_reg)
    skip_lbl = ctx.fresh_label("use_skip")
    _ = [
        _emit_skip_if_class(scope, first_reg, status_class, skip_lbl)
        for status_class in (StatusClass.SUCCESSFUL, *handled)
    ]
    if use.program == program_name(ctx._asg):
        _emit_use_perform(scope, use.section)
    else:
        _emit_use_call(scope, use)
    ctx.emit_inst(Branch(label=skip_lbl), span=scope.span)
    ctx.emit_inst(Label_(label=skip_lbl), span=scope.span)


def _emit_use_perform(scope: LoweringScope, section: str) -> None:
    ctx, span = scope.ctx, scope.span
    ret_lbl = ctx.fresh_label("use_return")
    ctx.emit_inst(
        SetContinuation(name=ctx.procedures.section_end(section), target_label=ret_lbl),
        span=span,
    )
    ctx.emit_inst(Branch(label=ctx.procedures.section(section)), span=span)
    ctx.emit_inst(Label_(label=ret_lbl), span=span)


def _emit_use_call(scope: LoweringScope, use: UseProcedure) -> None:
    """A containing program's USE GLOBAL section runs in that program: name the
    section in its request variable and enter it, with no arguments."""
    ctx, span = scope.ctx, scope.span
    ctx.emit_inst(
        StoreVar(
            name=use_request_var(use.program),
            value_reg=ctx.const_to_reg(use.section, span=span),
        ),
        span=span,
    )
    count = ctx.const_to_reg(0, span=span)
    args = ctx.fresh_reg()
    ctx.emit_inst(NewArray(result_reg=args, size_reg=count), span=span)
    ctx.emit_inst(
        StoreField(obj_reg=args, field_name=FieldName("count"), value_reg=count),
        span=span,
    )
    ctx.emit_inst(
        CallWithMemory(
            result_reg=ctx.fresh_reg(), location=entry_var(use.program), memory=args
        ),
        span=span,
    )
    _, ws_reg = scope.materialised.working_storage
    ctx.emit_inst(StoreVar(name=VarName("__ws_region"), value_reg=ws_reg), span=span)


def handled_classes(at_end: bool, invalid_key: bool) -> tuple[StatusClass, ...]:
    """The status classes a statement's own AT END / INVALID KEY phrase handles."""
    return (
        *((StatusClass.AT_END,) if at_end else ()),
        *((StatusClass.INVALID_KEY,) if invalid_key else ()),
    )


def _emit_use_trigger(
    scope: LoweringScope,
    file_name: str,
    status_reg: Register,
    handled: Sequence[StatusClass],
) -> None:
    """Run the USE declarative an I/O verb's error or exception status selects,
    when the statement's own AT END / INVALID KEY phrase does not handle it: the
    first, in order of precedence, whose open mode is the file's (or that names
    the file)."""
    uses = use_procedures(scope.ctx._asg, file_name)
    if not uses:
        return
    ctx, span = scope.ctx, scope.span
    done = ctx.fresh_label("use_done")
    mode_reg = scope.emitter.load(file_state_of(ctx._asg, file_name).mode)
    _ = [
        _emit_use_candidate(scope, use, mode_reg, (status_reg, done), handled)
        for use in uses
    ]
    ctx.emit_inst(Label_(label=done), span=span)


def _emit_use_candidate(
    scope: LoweringScope,
    use: UseProcedure,
    mode_reg: Register,
    outcome: tuple[Register, CodeLabel],
    handled: Sequence[StatusClass],
) -> None:
    ctx, span = scope.ctx, scope.span
    status_reg, done = outcome
    next_lbl = ctx.fresh_label("use_mode_next")
    if use.mode:
        match_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=match_reg,
                operator=resolve_binop("=="),
                left=mode_reg,
                right=ctx.const_to_reg(use.mode, span=span),
            ),
            span=span,
        )
        do_lbl = ctx.fresh_label("use_mode_do")
        ctx.emit_inst(
            BranchIf(cond_reg=match_reg, branch_targets=(do_lbl, next_lbl)), span=span
        )
        ctx.emit_inst(Label_(label=do_lbl), span=span)
    _emit_conditional_use(scope, status_reg, use, handled)
    ctx.emit_inst(Branch(label=done), span=span)
    ctx.emit_inst(Label_(label=next_lbl), span=span)


def _emit_open_use_trigger(
    scope: LoweringScope, file_name: str, mode: OpenMode, status_reg: Register
) -> None:
    """A failed OPEN leaves the file closed, so an open-mode USE is chosen by the
    mode the OPEN attempted, not by the file's current mode."""
    use = next(
        (
            use
            for use in use_procedures(scope.ctx._asg, file_name)
            if use.mode in ("", mode.value)
        ),
        NO_USE,
    )
    if not use.section:
        return
    _emit_conditional_use(scope, status_reg, use, ())


def lower_accept(
    ctx: EmitContext,
    stmt: AcceptStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ACCEPT target [FROM device] — fill the receiver from __cobol_accept records and
    store it unedited, as characters over the receiver's bytes."""
    scope = LoweringScope(ctx, materialised, stmt.span)
    span = stmt.span
    program = _program(scope)
    if not ctx.has_field(stmt.target.name, materialised):
        AcceptFill(scope.emitter, stmt.from_device, 0).emit(program, _ignored)
        return
    target_ref, target_rr = ctx.resolve_field_ref(
        stmt.target.name,
        materialised,
        stmt.target.qualifiers,
        subscripts=stmt.target.subscripts,
        span=span,
    )

    def store(received: Register) -> None:
        ctx.emit_encode_and_write(
            target_rr,
            target_ref.fl.as_characters(),
            ctx.emit_to_string(received, span=span),
            target_ref.offset_reg,
            extent=target_ref.extent,
            span=span,
        )

    AcceptFill(scope.emitter, stmt.from_device, target_ref.fl.byte_length).emit(
        program, store
    )
    logger.info("ACCEPT %s FROM %s", stmt.target.name, stmt.from_device)


def _lower_open_file(scope: LoweringScope, filename: str, mode: OpenMode) -> None:
    v = _verb(scope, filename)
    outcome = v.outcome()
    v.guarded(
        (
            Refusal(v.open_, FileLogicStatus.ALREADY_OPEN),
            Refusal(v.locked, FileLogicStatus.CLOSED_WITH_LOCK),
        ),
        outcome,
        partial(_emit_open, v, outcome, mode, _entry(scope.ctx, filename)),
        _nothing,
    )
    status_reg = v.e.load(outcome.status)
    scope.ctx.emit_file_status_update(
        filename, status_reg, scope.materialised, span=scope.span
    )
    _emit_open_use_trigger(scope, filename, mode, status_reg)
    logger.info("OPEN %s %s", mode.value, filename)


def _emit_open(
    v: FileVerbIr, outcome: VerbOutcome, mode: OpenMode, entry: FileControlEntry
) -> None:
    v.called(
        "__cobol_open_file", outcome, v.e.text(entry.file_name), v.e.text(mode.value)
    )
    _emit_optional_absent(v, outcome, mode, entry)
    v.when(v.successful(outcome), partial(_opened, v, mode, entry))


def _opened(v: FileVerbIr, mode: OpenMode, entry: FileControlEntry) -> None:
    v.set_mode(mode.value)
    v.set_position(FilePosition.NO_CURRENT_RECORD)
    v.e.store(v.state.last_key, v.e.text(""))
    v.e.store(v.state.read_refused, v.e.bool_(mode not in _READ_MODES))
    v.e.store(v.state.write_refused, v.e.bool_(mode not in _write_modes(entry)))
    v.e.store(v.state.update_refused, v.e.bool_(mode is not OpenMode.IO))


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
    scope = LoweringScope(ctx, materialised, stmt.span)
    _ = [
        _lower_open_file(scope, filename, mode)
        for mode, files in stmt.mode_groups
        for filename in files
    ]


def lower_close(
    ctx: EmitContext,
    stmt: CloseStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CLOSE file1 file2 ... — close files via __cobol_close_file. Every file here
    is on a non-reel/unit medium: REEL or UNIT leaves it open, and REEL/UNIT, FOR
    REMOVAL and NO REWIND each report 07."""
    scope = LoweringScope(ctx, materialised, stmt.span)
    _ = [_lower_close_file(scope, stmt, filename) for filename in stmt.files]


def _lower_close_file(
    scope: LoweringScope, stmt: CloseStatement, filename: str
) -> None:
    v = _verb(scope, filename)
    outcome = v.outcome()
    v.guarded(
        (Refusal(v.closed, FileLogicStatus.NOT_OPEN),),
        outcome,
        partial(_close_as_phrased, v, outcome, stmt, _entry(scope.ctx, filename)),
        _nothing,
    )
    status_reg = v.e.load(outcome.status)
    scope.ctx.emit_file_status_update(
        filename, status_reg, scope.materialised, span=scope.span
    )
    _emit_use_trigger(scope, filename, status_reg, ())
    logger.info("CLOSE %s", filename)


def _close_as_phrased(
    v: FileVerbIr, outcome: VerbOutcome, stmt: CloseStatement, entry: FileControlEntry
) -> None:
    """IBM's effect of CLOSE on a non-reel/unit file: REEL or UNIT is code F, the
    file stays open with only its I-O status updated; any other CLOSE closes it.
    A REEL/UNIT, FOR REMOVAL or NO REWIND phrase sets that status to 07."""
    name = entry.file_name
    if name in stmt.reel_unit:
        v.set_status(outcome, FileLogicStatus.NON_REEL_MEDIUM)
        return
    _emit_close(v, outcome, entry, name in stmt.with_lock)
    if name in stmt.no_rewind:
        v.when(
            v.status_is(outcome, FileLogicStatus.PERMITTED),
            partial(v.set_status, outcome, FileLogicStatus.NON_REEL_MEDIUM),
        )


def emit_implicit_close(ctx: EmitContext, entry: FileControlEntry) -> None:
    """The close CANCEL makes of a file its program left open: the CLOSE
    statement's own close, with no FILE STATUS update and no USE procedure."""
    e = IrEmitter(ctx, None)
    v = FileVerbIr(
        e,
        file_state(program_name(ctx._asg), entry.file_name),
        e.text(program_name(ctx._asg)),
    )
    v.when(v.open_(), partial(_emit_close, v, v.outcome(), entry, False))


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
    emit_closed(v.e, v.state, with_lock)


def _emit_key_text(scope: LoweringScope, key: RefModOperand) -> Register:
    if not scope.materialised.has_field(key.name):
        return Register(str(scope.ctx.const_to_reg("", span=scope.span)))
    return scope.ctx.emit_to_string(_emit_key_value(scope, key), span=scope.span)


def _emit_key_value(scope: LoweringScope, key: RefModOperand) -> Register:
    ctx, span = scope.ctx, scope.span
    key_ref, key_rr = ctx.resolve_field_ref(
        key.name, scope.materialised, key.qualifiers, key.subscripts, span=span
    )
    return ctx.emit_decode_field(
        key_rr, key_ref.fl, key_ref.offset_reg, extent=key_ref.extent, span=span
    )


def _emit_record_number_report(
    scope: LoweringScope,
    number: Callable[[], Register],
    status_reg: Register,
    key: RefModOperand,
) -> None:
    """After a successful sequential READ or WRITE of a relative file, MOVE the
    record number it used to the RELATIVE KEY."""
    if not scope.materialised.has_field(key.name):
        return
    _emit_store_if_successful(scope, status_reg, number(), key)


def _emit_record_length_report(
    scope: LoweringScope, data_reg: Register, status_reg: Register, file_name: str
) -> None:
    ctx = scope.ctx
    item = RefModOperand(name=depending_on(ctx._asg, file_name))
    if not scope.materialised.has_field(item.name):
        return
    length_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=length_reg,
            func_name=FuncName(BuiltinName.LENGTH),
            args=(data_reg,),
        ),
        span=scope.span,
    )
    _emit_store_if_successful(scope, status_reg, length_reg, item)


def _emit_record_of_its_length(
    scope: LoweringScope, data_reg: Register, file_name: str
) -> Register:
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
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
    scope: LoweringScope,
    status_reg: Register,
    data_reg: Register,
    into: RefModOperand,
) -> None:
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
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
    skip_lbl = _emit_branch_if_successful(scope, status_reg)
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


def _emit_branch_if_successful(scope: LoweringScope, status_reg: Register) -> CodeLabel:
    ctx, span = scope.ctx, scope.span
    ok_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=ok_reg,
            operator=resolve_binop("=="),
            left=_emit_status_class(scope, status_reg),
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
    scope: LoweringScope,
    status_reg: Register,
    value_reg: Register,
    target: RefModOperand,
) -> None:
    ctx, span = scope.ctx, scope.span
    skip_lbl = _emit_branch_if_successful(scope, status_reg)
    target_ref, target_rr = ctx.resolve_field_ref(
        target.name, scope.materialised, target.qualifiers, target.subscripts, span=span
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


def _read_key_reg(scope: LoweringScope, stmt: ReadStatement) -> Register:
    ctx = scope.ctx
    entry = _file_entries(ctx).get(
        stmt.file_name, FileControlEntry(file_name=stmt.file_name)
    )
    if entry.organization is FileOrganization.INDEXED:
        return _indexed_read_key_reg(scope, entry, stmt)
    return _emit_key_text(
        scope,
        (
            stmt.key
            if stmt.key.name
            else addressing_key(ctx._asg, stmt.file_name, stmt.next_record)
        ),
    )


def _indexed_read_key_reg(
    scope: LoweringScope, entry: FileControlEntry, stmt: ReadStatement
) -> Register:
    sequential = entry.access_mode is AccessMode.SEQUENTIAL or stmt.next_record
    key = stmt.key if stmt.key.name else entry.record_key
    if sequential or not scope.materialised.has_field(key.name):
        return Register(str(scope.ctx.const_to_reg("", span=scope.span)))
    return _key_value_reg(scope, entry.organization, key)


def _sequential_read(scope: LoweringScope, stmt: ReadStatement) -> bool:
    ctx, materialised = scope.ctx, scope.materialised
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


def _refer(v: FileVerbIr, file_name: str, reference: Sequence[int]) -> None:
    _ = [
        v.e.call(
            "__cobol_key_of_reference", v.e.text(file_name), v.e.int_(n), v.program
        )
        for n in reference
    ]


def _key_of_reference(
    scope: LoweringScope, entry: FileControlEntry, key: RefModOperand
) -> tuple[int, ...]:
    if not entry.alternate_keys:
        return ()
    return (key_number(scope.ctx._asg, entry, scope.materialised, key),)


def _read_reference(scope: LoweringScope, stmt: ReadStatement) -> tuple[int, ...]:
    entry = _entry(scope.ctx, stmt.file_name)
    if _sequential_read(scope, stmt):
        return ()
    return _key_of_reference(
        scope, entry, stmt.key if stmt.key.name else entry.record_key
    )


def _read_present(v: FileVerbIr, outcome: VerbOutcome, plan: ReadPlan) -> None:
    _refer(v, plan.file_name, plan.reference)
    raw = v.called("__cobol_read_record", outcome, v.e.text(plan.file_name), plan.key)
    v.keep_record(raw, outcome)
    _keep_number_if(v, outcome, raw, plan.numbered)
    _emit_relative_key_overflow(v, outcome, plan.key_digits)
    _remember_key(v, v.e.load(outcome.data), plan.sequence)


def _keep_number_if(
    v: FileVerbIr, outcome: VerbOutcome, raw: Register, numbered: bool
) -> None:
    if numbered:
        v.keep_number(raw, outcome)


def _start_numbered(v: FileVerbIr, outcome: VerbOutcome, numbered: bool) -> None:
    if numbered:
        v.with_number(outcome)


def _read_absent(v: FileVerbIr, outcome: VerbOutcome, plan: ReadPlan) -> None:
    v.set_status(
        outcome,
        FileLogicStatus.AT_END if plan.sequential else FileLogicStatus.NOT_FOUND,
    )


def _read_performed(v: FileVerbIr, outcome: VerbOutcome, plan: ReadPlan) -> None:
    v.unless_absent(
        plan.optional,
        partial(_read_absent, v, outcome, plan),
        partial(_read_present, v, outcome, plan),
    )
    v.e.store(v.state.position, _read_position(v, outcome))


def _read_refusals(v: FileVerbIr, sequential: bool) -> tuple[Refusal, ...]:
    after_end = Refusal(
        partial(v.position_is, FilePosition.AT_END), FileLogicStatus.NO_NEXT_RECORD
    )
    return (
        Refusal(v.read_refused, FileLogicStatus.READ_NOT_PERMITTED),
        *((after_end,) if sequential else ()),
    )


def _emit_guarded_read(v: FileVerbIr, outcome: VerbOutcome, plan: ReadPlan) -> None:
    v.with_record(outcome)
    _start_numbered(v, outcome, plan.numbered)
    v.guarded(
        _read_refusals(v, plan.sequential),
        outcome,
        partial(_read_performed, v, outcome, plan),
        v.forget_current_record,
    )


def _read_plan(
    scope: LoweringScope, stmt: ReadStatement, key_reg: Register
) -> ReadPlan:
    ctx, materialised = scope.ctx, scope.materialised
    entry = _entry(ctx, stmt.file_name)
    digits = relative_key_digits(materialised, entry)
    report = reported_key(ctx._asg, stmt.file_name, stmt.next_record)
    return ReadPlan(
        stmt.file_name,
        key_reg,
        _sequential_read(scope, stmt),
        entry.optional,
        digits,
        _key_sequence(scope, stmt.file_name),
        bool(digits) or materialised.has_field(report.name),
        _read_reference(scope, stmt),
    )


def lower_read(
    ctx: EmitContext,
    stmt: ReadStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """READ file [INTO target] [KEY k] [AT END ...] [INVALID KEY ...] — with IOResult branching."""
    scope = LoweringScope(ctx, materialised, stmt.span)
    span = stmt.span
    key_str_reg = _read_key_reg(scope, stmt)
    v = _verb(scope, stmt.file_name)
    outcome = v.outcome()
    _emit_guarded_read(v, outcome, _read_plan(scope, stmt, key_str_reg))
    status_reg = v.e.load(outcome.status)
    ctx.emit_file_status_update(stmt.file_name, status_reg, materialised, span=span)
    _emit_record_number_report(
        scope,
        partial(v.e.load, outcome.number),
        status_reg,
        reported_key(ctx._asg, stmt.file_name, stmt.next_record),
    )
    _emit_use_trigger(
        scope,
        stmt.file_name,
        status_reg,
        handled_classes(bool(stmt.at_end), bool(stmt.invalid_key)),
    )
    data_reg = v.e.load(outcome.data)
    _emit_record_length_report(scope, data_reg, status_reg, stmt.file_name)

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

    _emit_read_into(scope, status_reg, data_reg, stmt.into)

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
                left=_emit_status_class(scope, status_reg),
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
                left=_emit_status_class(scope, status_reg),
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
    scope: LoweringScope,
    status_reg: Register,
    phrases: InvalidKeyPhrases,
    after_label: CodeLabel,
) -> None:
    if not phrases.written:
        return
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    inv_lbl = ctx.fresh_label("inv_key")
    not_inv_lbl = ctx.fresh_label("not_inv_key")
    cond_reg = ctx.fresh_reg()
    invalid_key_class = ctx.const_to_reg(StatusClass.INVALID_KEY.value, span=span)
    ctx.emit_inst(
        Binop(
            result_reg=cond_reg,
            operator=resolve_binop("=="),
            left=_emit_status_class(scope, status_reg),
            right=Register(str(invalid_key_class)),
        ),
        span=span,
    )
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(inv_lbl, not_inv_lbl)), span=span
    )
    ctx.emit_inst(Label_(label=inv_lbl), span=span)
    [ctx.lower_statement(s, materialised) for s in phrases.invalid_key]
    ctx.emit_inst(Branch(label=after_label), span=span)
    ctx.emit_inst(Label_(label=not_inv_lbl), span=span)
    [ctx.lower_statement(s, materialised) for s in phrases.not_invalid_key]
    ctx.emit_inst(Branch(label=after_label), span=span)


def _write_source_reg(
    scope: LoweringScope, from_field: RefModOperand, record_name: str
) -> Register:
    """Resolve the byte-faithful data register for WRITE/REWRITE.

    The file holds the record area's raw byte-image (regions are EBCDIC), so the
    data shipped to the provider is the record region's verbatim bytes — read via
    LATIN1 identity so binary subfields (COMP-3/COMP) survive unchanged
    (red-dragon-zwzg). `WRITE rec FROM fld` is COBOL `MOVE fld TO rec; WRITE rec`:
    emit the MOVE into the record region first, then read the region raw.
    The MOVE takes the FROM operand by the kind the bridge states.
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    if from_field.name:
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
    call: tuple[str, tuple[Register, ...], Callable[[Register], None]],
    refusals: Sequence[Refusal],
) -> None:
    primitive, args, performed = call
    v.guarded(
        refusals,
        outcome,
        lambda: performed(v.called(primitive, outcome, *args)),
        v.forget_current_record,
    )


def _no_current_record(v: FileVerbIr, raw: Register) -> None:
    v.set_position(FilePosition.NO_CURRENT_RECORD)


def _after_write(
    v: FileVerbIr, outcome: VerbOutcome, plan: WritePlan, raw: Register
) -> None:
    """A WRITE leaves no current record, which only a file open I-O can have; it
    reports its record number to a RELATIVE KEY, and keeps its prime key in sequence."""
    _keep_number_if(v, outcome, raw, plan.numbered)
    if plan.keyed:
        v.set_position(FilePosition.NO_CURRENT_RECORD)
    _remember_written_key(v, outcome, plan.record, plan.sequence)


def _size_refusals(
    scope: LoweringScope, v: FileVerbIr, file_name: str, data_reg: Register
) -> tuple[Refusal, ...]:
    """A variable-length record shorter than the file's smallest or longer than its
    largest record is a boundary violation, 44."""
    asg = scope.ctx._asg
    if not records_vary(asg, file_name):
        return ()
    smallest = minimum_length(asg, file_name)
    largest = next(
        (area.byte_length for area in record_area(asg, file_name, scope.materialised)),
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


def _addressed_key_values(scope: LoweringScope, file_name: str) -> tuple[Register, ...]:
    key = addressing_key(scope.ctx._asg, file_name, False)
    if not scope.materialised.has_field(key.name):
        return ()
    return (_emit_key_value(scope, key),)


def _key_sequence(scope: LoweringScope, file_name: str) -> tuple[PrimeKey, ...]:
    """The prime key an indexed file in sequential access keeps in sequence by; none
    for any other file."""
    ctx, materialised = scope.ctx, scope.materialised
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


def _remember_written_key(
    v: FileVerbIr, outcome: VerbOutcome, record: Register, keys: Sequence[PrimeKey]
) -> None:
    if not keys:
        return
    v.when(v.successful(outcome), partial(_remember_key, v, record, keys))


def _current_record_refusals(
    v: FileVerbIr, entry: FileControlEntry
) -> tuple[Refusal, ...]:
    return (
        Refusal(v.update_refused, FileLogicStatus.UPDATE_NOT_PERMITTED),
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


def _record_file(ctx: EmitContext, record_name: str) -> str:
    return visible_record_files(ctx._asg).get(record_name.upper(), record_name)


def lower_write(
    ctx: EmitContext,
    stmt: WriteStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """WRITE record-name [FROM field] [INVALID KEY ...] — write record via __cobol_write_record."""
    scope = LoweringScope(ctx, materialised, stmt.span)
    span = stmt.span
    file_name = _record_file(ctx, stmt.record_name)
    data_reg = _emit_record_of_its_length(
        scope,
        _write_source_reg(scope, stmt.from_field, stmt.record_name),
        file_name,
    )
    key_values = _addressed_key_values(scope, file_name)
    key_reg = next(
        (ctx.emit_to_string(value, span=span) for value in key_values),
        Register(str(ctx.const_to_reg("", span=span))),
    )
    v = _verb(scope, file_name)
    outcome = v.outcome()
    entry = _entry(ctx, file_name)
    sequence = _key_sequence(scope, file_name)
    report = reported_key(ctx._asg, file_name, False)
    plan = WritePlan(
        data_reg,
        sequence,
        materialised.has_field(report.name),
        entry.organization is not FileOrganization.SEQUENTIAL,
    )
    _start_numbered(v, outcome, plan.numbered)
    _emit_guarded_update(
        v,
        outcome,
        (
            "__cobol_write_record",
            (v.e.text(file_name), data_reg, key_reg),
            partial(_after_write, v, outcome, plan),
        ),
        (
            Refusal(
                v.write_refused,
                FileLogicStatus.WRITE_NOT_PERMITTED,
            ),
            *_size_refusals(scope, v, file_name, data_reg),
            *_boundary_refusals(v, key_values),
            *_sequence_refusals(v, data_reg, sequence, "<"),
        ),
    )
    status_reg = v.e.load(outcome.status)
    ctx.emit_file_status_update(file_name, status_reg, materialised, span=span)
    _emit_record_number_report(
        scope, partial(v.e.load, outcome.number), status_reg, report
    )
    _emit_use_trigger(
        scope, file_name, status_reg, handled_classes(False, bool(stmt.invalid_key))
    )
    after_label = ctx.fresh_label("write_after")
    _emit_invalid_key_branch(
        scope,
        status_reg,
        InvalidKeyPhrases(stmt.invalid_key, stmt.not_invalid_key),
        after_label,
    )
    ctx.emit_inst(Label_(label=after_label), span=span)
    logger.info("WRITE %s FROM %s", stmt.record_name, stmt.from_field.name or "(none)")


def lower_rewrite(
    ctx: EmitContext,
    stmt: RewriteStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """REWRITE record-name [FROM field] [INVALID KEY ...] — rewrite via __cobol_rewrite_record."""
    scope = LoweringScope(ctx, materialised, stmt.span)
    span = stmt.span
    file_name = _record_file(ctx, stmt.record_name)
    data_reg = _emit_record_of_its_length(
        scope,
        _write_source_reg(scope, stmt.from_field, stmt.record_name),
        file_name,
    )
    key_reg = _emit_key_text(scope, addressing_key(ctx._asg, file_name, False))
    v = _verb(scope, file_name)
    outcome = v.outcome()
    _emit_guarded_update(
        v,
        outcome,
        (
            "__cobol_rewrite_record",
            (v.e.text(file_name), data_reg, key_reg),
            partial(_no_current_record, v),
        ),
        (
            *_current_record_refusals(v, _entry(ctx, file_name)),
            *_size_refusals(scope, v, file_name, data_reg),
            *_sequence_refusals(v, data_reg, _key_sequence(scope, file_name), "!="),
        ),
    )
    status_reg = v.e.load(outcome.status)
    ctx.emit_file_status_update(file_name, status_reg, materialised, span=span)
    _emit_use_trigger(
        scope, file_name, status_reg, handled_classes(False, bool(stmt.invalid_key))
    )
    after_label = ctx.fresh_label("rewrite_after")
    _emit_invalid_key_branch(
        scope,
        status_reg,
        InvalidKeyPhrases(stmt.invalid_key, stmt.not_invalid_key),
        after_label,
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
    scope = LoweringScope(ctx, materialised, stmt.span)
    span = stmt.span
    key_reg = _start_key_reg(scope, stmt)
    relop_reg = Register(str(ctx.const_to_reg(stmt.relop or "=", span=span)))
    v = _verb(scope, stmt.file_name)
    outcome = v.outcome()
    entry = _entry(ctx, stmt.file_name)
    reference = _key_of_reference(
        scope, entry, stmt.key if stmt.key.name else _file_key(entry)
    )

    def started() -> None:
        _refer(v, stmt.file_name, reference)
        _ignored(
            v.called(
                "__cobol_start_file",
                outcome,
                v.e.text(stmt.file_name),
                key_reg,
                relop_reg,
            )
        )

    def perform() -> None:
        v.unless_absent(
            entry.optional,
            lambda: v.set_status(outcome, FileLogicStatus.NOT_FOUND),
            started,
        )
        v.set_position(FilePosition.NO_CURRENT_RECORD)

    v.guarded(
        (
            Refusal(
                v.read_refused,
                FileLogicStatus.READ_NOT_PERMITTED,
            ),
        ),
        outcome,
        perform,
        v.forget_current_record,
    )
    status_reg = v.e.load(outcome.status)
    ctx.emit_file_status_update(stmt.file_name, status_reg, materialised, span=span)
    _emit_use_trigger(
        scope,
        stmt.file_name,
        status_reg,
        handled_classes(False, bool(stmt.invalid_key)),
    )
    after_label = ctx.fresh_label("start_after")
    _emit_invalid_key_branch(
        scope,
        status_reg,
        InvalidKeyPhrases(stmt.invalid_key, stmt.not_invalid_key),
        after_label,
    )
    ctx.emit_inst(Label_(label=after_label), span=span)
    logger.info(
        "START %s KEY %s %s", stmt.file_name, stmt.relop, stmt.key.name or "(none)"
    )


def _file_entries(ctx: EmitContext) -> dict[str, FileControlEntry]:
    return visible_file_entries(ctx._asg)


def _file_key(entry: FileControlEntry) -> RefModOperand:
    if entry.organization is FileOrganization.RELATIVE:
        return entry.relative_key
    return entry.record_key


def _delete_key_reg(scope: LoweringScope, file_name: str) -> Register:
    entries = _file_entries(scope.ctx)
    if (
        file_name not in entries
        or entries[file_name].access_mode is AccessMode.SEQUENTIAL
    ):
        return scope.ctx.const_to_reg("", span=scope.span)
    entry = entries[file_name]
    return _key_value_reg(scope, entry.organization, _file_key(entry))


def _start_key_reg(scope: LoweringScope, stmt: StartStatement) -> Register:
    entries = _file_entries(scope.ctx)
    if (
        stmt.file_name not in entries
        or entries[stmt.file_name].organization is FileOrganization.SEQUENTIAL
    ):
        return scope.ctx.const_to_reg("", span=scope.span)
    entry = entries[stmt.file_name]
    key = stmt.key if stmt.key.name else _file_key(entry)
    return _key_value_reg(scope, entry.organization, key)


def _key_value_reg(
    scope: LoweringScope, organization: FileOrganization, key: RefModOperand
) -> Register:
    ctx, span = scope.ctx, scope.span
    key_ref, key_rr = ctx.resolve_field_ref(
        key.name, scope.materialised, key.qualifiers, key.subscripts, span=span
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
    scope = LoweringScope(ctx, materialised, stmt.span)
    span = stmt.span
    key_reg = _delete_key_reg(scope, stmt.file_name)
    v = _verb(scope, stmt.file_name)
    outcome = v.outcome()
    _emit_guarded_update(
        v,
        outcome,
        (
            "__cobol_delete_record",
            (v.e.text(stmt.file_name), key_reg),
            partial(_no_current_record, v),
        ),
        _current_record_refusals(v, _entry(ctx, stmt.file_name)),
    )
    status_reg = v.e.load(outcome.status)
    ctx.emit_file_status_update(stmt.file_name, status_reg, materialised, span=span)
    _emit_use_trigger(
        scope,
        stmt.file_name,
        status_reg,
        handled_classes(False, bool(stmt.invalid_key)),
    )
    after_label = ctx.fresh_label("delete_after")
    _emit_invalid_key_branch(
        scope,
        status_reg,
        InvalidKeyPhrases(stmt.invalid_key, stmt.not_invalid_key),
        after_label,
    )
    ctx.emit_inst(Label_(label=after_label), span=span)
    logger.info("DELETE %s", stmt.file_name)
