# pyright: standard
"""SVC 19, 20, 200 and 201 in IR: OPEN, CLOSE, GET and PUT over the file provider, reading the DCB's fields from storage on each call."""

from collections.abc import Callable, Mapping

from cobol_asg.file_enums import OpenMode
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.branch_dispatch import emit_branch
from interpreter.hlasm.byte_loop import emit_byte_loop
from interpreter.hlasm.hlasm_constants import (
    BYTES_TO_STRING,
    DCB_BUFFERS_VAR,
    DOUBLEWORD_BYTES,
    END_OF_DATA_ABEND,
    GETMAIN_FREEMAIN_ABEND,
    HALFWORD_BYTES,
    LATIN1,
    LIST_CONCAT,
    LIST_GET,
    LIST_LEN,
    LIST_SLICE,
    MAKE_LIST,
    ONE_BYTE,
    OPERATION_EXCEPTION_ABEND,
    RETURN_CODE_REGISTER,
    STRING_TO_BYTES,
    SVC_PARAMETER_REGISTER,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.program_services import blank_ended_name
from interpreter.hlasm.storage_request import StorageRequest
from interpreter.hlasm.storage_services import obtained
from interpreter.hlasm_run_inputs.record_format import RecordFormat
from interpreter.hlasm_run_inputs.run_input_names import (
    DD_BLKSIZE_FACT,
    DD_BUILTIN,
    DD_LRECL_FACT,
    DD_RECFM_FACT,
    DD_SUPPLIED_FACT,
    DECLARE_FILE_BUILTIN,
)
from interpreter.instructions import (
    Branch,
    BranchIf,
    Label_,
    LoadIndex,
    NewObject,
    StoreField,
    StoreIndex,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.record_io.access_result import AccessCondition
from interpreter.register import Register
from interpreter.var_name import VarName

OPEN_FILE = FuncName("__cobol_open_file")
CLOSE_FILE = FuncName("__cobol_close_file")
READ_RECORD = FuncName("__cobol_read_record")
WRITE_RECORD = FuncName("__cobol_write_record")
IO_OUTCOME = FuncName("__cobol_io_outcome")
IO_DATA = FuncName("__cobol_io_data")
ENTRY_VAR = VarName("__hlasm_dcb_entry")
FAILED_VAR = VarName("__hlasm_open_failed")
SELECTED_VAR = VarName("__hlasm_dcb_selected")
RECORD_VAR = VarName("__hlasm_record")
BUFFER_FIELD = FieldName("buffer")
PENDING_FIELD = FieldName("pending")
AREA_REGISTER = 0
EODAD_OFFSET = 33
EODAD_BYTES = 3
RECFM_OFFSET = 36
DDNAME_OFFSET = 40
OFLGS_OFFSET = 48
MACRF_OFFSET = 50
BLKSIZE_OFFSET = 62
LRECL_OFFSET = 82
OPEN_FLAG = 0x10
FORMAT_BITS = 0xC0
VARIABLE_FORMAT = RecordFormat.V.value
GET_LOCATE = 0x0800
PUT_LOCATE = 0x0008
LIST_END = 0x80
MODE_BITS = 0x0F
LIST_ENTRY_BYTES = 4
DCB_ADDRESS_BYTES = 3
RDW_BYTES = 4
NO_EXIT = 1
OPEN_FAILED_CODE = 8
NO_PROGRAM = ""
NO_LRECL_ABEND = "S013"
LONG_RECORD_ABEND = "S002"
NO_KEY = ""
OPEN_MODES: Mapping[int, OpenMode] = {
    0x00: OpenMode.INPUT,
    0x0F: OpenMode.OUTPUT,
    0x0E: OpenMode.EXTEND,
}

type EntryBody = Callable[[HlasmEmitter, Register, Register], None]


def _has(emitter: HlasmEmitter, value: Register, bits: int) -> Register:
    masked = emitter.binop(BinopKind.BIT_AND, value, emitter.int_(bits))
    return emitter.binop(BinopKind.NE, masked, emitter.int_(0))


def _when(emitter: HlasmEmitter, condition: Register, body: Callable[[], None]) -> None:
    taken, skipped = (emitter.fresh_label(p) for p in ("hl_dcb_then", "hl_dcb_skip"))
    emitter.emit_inst(BranchIf(cond_reg=condition, branch_targets=(taken, skipped)))
    emitter.emit_inst(Label_(label=taken))
    body()
    emitter.emit_inst(Label_(label=skipped))


def _otherwise_to(emitter: HlasmEmitter, condition: Register, away: CodeLabel) -> None:
    stay = emitter.fresh_label("hl_dcb_stay")
    emitter.emit_inst(BranchIf(cond_reg=condition, branch_targets=(stay, away)))
    emitter.emit_inst(Label_(label=stay))


def _selected(
    emitter: HlasmEmitter, condition: Register, choices: tuple[Register, Register]
) -> Register:
    chosen, other, done = (
        emitter.fresh_label(p) for p in ("hl_dcb_chosen", "hl_dcb_other", "hl_dcb_one")
    )
    emitter.emit_inst(BranchIf(cond_reg=condition, branch_targets=(chosen, other)))
    emitter.emit_inst(Label_(label=chosen))
    emitter.store_var(SELECTED_VAR, choices[0])
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=other))
    emitter.store_var(SELECTED_VAR, choices[1])
    emitter.emit_inst(Label_(label=done))
    return emitter.load_var(SELECTED_VAR)


def _ddname(emitter: HlasmEmitter, dcb: Register) -> Register:
    at = emitter.binop(BinopKind.ADD, dcb, emitter.int_(DDNAME_OFFSET))
    return blank_ended_name(emitter, at)


def _variable(emitter: HlasmEmitter, dcb: Register) -> Register:
    recfm = emitter.load_storage(dcb, RECFM_OFFSET, ONE_BYTE)
    form = emitter.binop(BinopKind.BIT_AND, recfm, emitter.int_(FORMAT_BITS))
    return emitter.binop(BinopKind.EQ, form, emitter.int_(VARIABLE_FORMAT))


def _is_open(emitter: HlasmEmitter, dcb: Register) -> Register:
    flags = emitter.load_storage(dcb, OFLGS_OFFSET, ONE_BYTE)
    return _has(emitter, flags, OPEN_FLAG)


def _mark(emitter: HlasmEmitter, dcb: Register, operator: BinopKind, bits: int) -> None:
    flags = emitter.load_storage(dcb, OFLGS_OFFSET, ONE_BYTE)
    marked = emitter.binop(operator, flags, emitter.int_(bits))
    emitter.store_storage(dcb, OFLGS_OFFSET, ONE_BYTE, marked)


def _locates(emitter: HlasmEmitter, dcb: Register, bits: int) -> Register:
    return _has(emitter, emitter.load_storage(dcb, MACRF_OFFSET, HALFWORD_BYTES), bits)


def _buffers_entry(emitter: HlasmEmitter, dcb: Register) -> Register:
    entry = emitter.fresh_reg()
    table = emitter.load_var(DCB_BUFFERS_VAR)
    emitter.emit_inst(LoadIndex(result_reg=entry, arr_reg=table, index_reg=dcb))
    return entry


def _set_pending(emitter: HlasmEmitter, entry: Register, pending: int) -> None:
    emitter.emit_inst(
        StoreField(
            obj_reg=entry, field_name=PENDING_FIELD, value_reg=emitter.int_(pending)
        )
    )


def _call(emitter: HlasmEmitter, name: FuncName, *args: Register) -> Register:
    return emitter.call(name, (*args, emitter.str_(NO_PROGRAM)))


def _outcome_is(
    emitter: HlasmEmitter, raw: Register, condition: AccessCondition
) -> Register:
    outcome = _call(emitter, IO_OUTCOME, raw)
    return emitter.binop(BinopKind.EQ, outcome, emitter.int_(condition.position()))


def _each_entry(emitter: HlasmEmitter, body: EntryBody) -> None:
    list_at = emitter.masked_address(emitter.load_gr32(SVC_PARAMETER_REGISTER))
    emitter.store_var(ENTRY_VAR, list_at)
    loop, done = (emitter.fresh_label(p) for p in ("hl_dcb_list", "hl_dcb_listed"))
    emitter.emit_inst(Label_(label=loop))
    entry = emitter.load_var(ENTRY_VAR)
    option = emitter.load_storage(entry, 0, ONE_BYTE)
    body(emitter, emitter.load_storage(entry, ONE_BYTE, DCB_ADDRESS_BYTES), option)
    _next_entry(emitter, entry, option, (loop, done))


def _next_entry(
    emitter: HlasmEmitter,
    entry: Register,
    option: Register,
    labels: tuple[CodeLabel, CodeLabel],
) -> None:
    loop, done = labels
    after = emitter.binop(BinopKind.ADD, entry, emitter.int_(LIST_ENTRY_BYTES))
    emitter.store_var(ENTRY_VAR, after)
    last = _has(emitter, option, LIST_END)
    emitter.emit_inst(BranchIf(cond_reg=last, branch_targets=(done, loop)))
    emitter.emit_inst(Label_(label=done))


def _merged(
    emitter: HlasmEmitter, at: tuple[Register, int, int], supplied: Register
) -> Register:
    dcb, offset, width = at
    written = emitter.load_storage(dcb, offset, width)
    empty = emitter.binop(BinopKind.EQ, written, emitter.int_(0))
    merged = _selected(emitter, empty, (supplied, written))
    emitter.store_storage(dcb, offset, width, merged)
    return merged


def _dd_fact(emitter: HlasmEmitter, facts: Register, index: int) -> Register:
    return emitter.call(LIST_GET, (facts, emitter.int_(index)))


def _merge_field(
    emitter: HlasmEmitter, dcb: Register, facts: Register, field: tuple[int, int, int]
) -> Register:
    offset, width, index = field
    return _merged(emitter, (dcb, offset, width), _dd_fact(emitter, facts, index))


def _merge_dd(emitter: HlasmEmitter, dcb: Register, facts: Register) -> Register:
    _merge_field(emitter, dcb, facts, (RECFM_OFFSET, ONE_BYTE, DD_RECFM_FACT))
    _merge_field(emitter, dcb, facts, (BLKSIZE_OFFSET, HALFWORD_BYTES, DD_BLKSIZE_FACT))
    return _merge_field(
        emitter, dcb, facts, (LRECL_OFFSET, HALFWORD_BYTES, DD_LRECL_FACT)
    )


def _mode_case(
    emitter: HlasmEmitter, mode: Register, case: tuple[int, OpenMode], chosen: CodeLabel
) -> None:
    code, name = case
    this, other = (emitter.fresh_label(p) for p in ("hl_open_mode", "hl_open_other"))
    same = emitter.binop(BinopKind.EQ, mode, emitter.int_(code))
    emitter.emit_inst(BranchIf(cond_reg=same, branch_targets=(this, other)))
    emitter.emit_inst(Label_(label=this))
    emitter.store_var(SELECTED_VAR, emitter.str_(name.value))
    emitter.emit_inst(Branch(label=chosen))
    emitter.emit_inst(Label_(label=other))


def _open_mode(emitter: HlasmEmitter, option: Register, failed: CodeLabel) -> Register:
    mode = emitter.binop(BinopKind.BIT_AND, option, emitter.int_(MODE_BITS))
    chosen = emitter.fresh_label("hl_open_moded")
    _ = [_mode_case(emitter, mode, case, chosen) for case in OPEN_MODES.items()]
    emitter.emit_inst(Branch(label=failed))
    emitter.emit_inst(Label_(label=chosen))
    return emitter.load_var(SELECTED_VAR)


def _declared(
    emitter: HlasmEmitter, dcb: Register, name: Register, lrecl: Register
) -> None:
    variable = _variable(emitter, dcb)
    descriptor = _selected(
        emitter, variable, (emitter.int_(RDW_BYTES), emitter.int_(0))
    )
    length = emitter.binop(BinopKind.SUB, lrecl, descriptor)
    emitter.call(DECLARE_FILE_BUILTIN, (name, variable, length))


def _buffer(emitter: HlasmEmitter, dcb: Register, lrecl: Register) -> None:
    request = StorageRequest(
        length=lrecl,
        subpool=emitter.int_(0),
        alignment=emitter.int_(DOUBLEWORD_BYTES),
        abend=GETMAIN_FREEMAIN_ABEND,
    )
    entry = emitter.fresh_reg()
    emitter.emit_inst(NewObject(result_reg=entry))
    emitter.emit_inst(
        StoreField(
            obj_reg=entry, field_name=BUFFER_FIELD, value_reg=obtained(emitter, request)
        )
    )
    _set_pending(emitter, entry, 0)
    table = emitter.load_var(DCB_BUFFERS_VAR)
    emitter.emit_inst(StoreIndex(arr_reg=table, index_reg=dcb, value_reg=entry))


def _opened(emitter: HlasmEmitter, dcb: Register, lrecl: Register) -> None:
    _mark(emitter, dcb, BinopKind.BIT_OR, OPEN_FLAG)
    locates = _locates(emitter, dcb, GET_LOCATE | PUT_LOCATE)
    _when(emitter, locates, lambda: _buffer(emitter, dcb, lrecl))


def _open_entry(emitter: HlasmEmitter, dcb: Register, option: Register) -> None:
    failed, done = (emitter.fresh_label(p) for p in ("hl_open_failed", "hl_open_done"))
    _attempt_open(emitter, dcb, option, failed)
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=failed))
    emitter.store_var(FAILED_VAR, emitter.int_(1))
    emitter.emit_inst(Label_(label=done))


def _merged_lrecl(emitter: HlasmEmitter, dcb: Register, facts: Register) -> Register:
    lrecl = _merge_dd(emitter, dcb, facts)
    missing = emitter.binop(BinopKind.EQ, lrecl, emitter.int_(0))
    _abend_when(emitter, missing, NO_LRECL_ABEND)
    return lrecl


def _attempt_open(
    emitter: HlasmEmitter, dcb: Register, option: Register, failed: CodeLabel
) -> None:
    name = _ddname(emitter, dcb)
    facts = emitter.call(DD_BUILTIN, (name,))
    supplied = emitter.binop(
        BinopKind.NE, _dd_fact(emitter, facts, DD_SUPPLIED_FACT), emitter.int_(0)
    )
    _otherwise_to(emitter, supplied, failed)
    mode = _open_mode(emitter, option, failed)
    lrecl = _merged_lrecl(emitter, dcb, facts)
    _declared(emitter, dcb, name, lrecl)
    raw = _call(emitter, OPEN_FILE, name, mode)
    _otherwise_to(emitter, _outcome_is(emitter, raw, AccessCondition.OK), failed)
    _opened(emitter, dcb, lrecl)


def emit_open(emitter: HlasmEmitter) -> None:
    emitter.store_var(FAILED_VAR, emitter.int_(0))
    _each_entry(emitter, _open_entry)
    code = emitter.binop(
        BinopKind.MUL, emitter.load_var(FAILED_VAR), emitter.int_(OPEN_FAILED_CODE)
    )
    emitter.store_gr32(RETURN_CODE_REGISTER, code)


def _abend_when(emitter: HlasmEmitter, condition: Register, code: str) -> None:
    _when(emitter, condition, lambda: emit_abend(emitter, code))


def _written_length(
    emitter: HlasmEmitter, dcb: Register, source: Register, variable: Register
) -> Register:
    described = emitter.load_storage(source, 0, HALFWORD_BYTES)
    lrecl = emitter.load_storage(dcb, LRECL_OFFSET, HALFWORD_BYTES)
    longer = emitter.binop(BinopKind.GT, described, lrecl)
    _abend_when(
        emitter, emitter.binop(BinopKind.AND, variable, longer), LONG_RECORD_ABEND
    )
    data = emitter.binop(BinopKind.SUB, described, emitter.int_(RDW_BYTES))
    return _selected(emitter, variable, (data, lrecl))


def _record_from(emitter: HlasmEmitter, dcb: Register, source: Register) -> Register:
    variable = _variable(emitter, dcb)
    length = _written_length(emitter, dcb, source, variable)
    start = _selected(emitter, variable, (emitter.int_(RDW_BYTES), emitter.int_(0)))
    first = emitter.binop(BinopKind.ADD, source, start)
    emitter.store_var(
        RECORD_VAR, emitter.call(MAKE_LIST, (emitter.int_(0), emitter.int_(0)))
    )
    emit_byte_loop(emitter, length, lambda at: _append_byte(emitter, first, at))
    return emitter.call(
        BYTES_TO_STRING, (emitter.load_var(RECORD_VAR), emitter.str_(LATIN1))
    )


def _append_byte(emitter: HlasmEmitter, first: Register, at: Register) -> None:
    byte = emitter.load_bytes(first, at, ONE_BYTE)
    record = emitter.call(LIST_CONCAT, (emitter.load_var(RECORD_VAR), byte))
    emitter.store_var(RECORD_VAR, record)


def _write(emitter: HlasmEmitter, dcb: Register, source: Register) -> None:
    data = _record_from(emitter, dcb, source)
    _call(emitter, WRITE_RECORD, _ddname(emitter, dcb), data, emitter.str_(NO_KEY))


def _write_pending(emitter: HlasmEmitter, dcb: Register, entry: Register) -> None:
    pending = emitter.binop(
        BinopKind.NE, emitter.load_field(entry, PENDING_FIELD), emitter.int_(0)
    )
    _when(
        emitter,
        pending,
        lambda: _write(emitter, dcb, emitter.load_field(entry, BUFFER_FIELD)),
    )


def _required_open(emitter: HlasmEmitter, dcb: Register) -> None:
    opened, closed = (emitter.fresh_label(p) for p in ("hl_dcb_open", "hl_dcb_closed"))
    emitter.emit_inst(
        BranchIf(cond_reg=_is_open(emitter, dcb), branch_targets=(opened, closed))
    )
    emitter.emit_inst(Label_(label=closed))
    emit_abend(emitter, OPERATION_EXCEPTION_ABEND)
    emitter.emit_inst(Label_(label=opened))


def _opened_dcb(emitter: HlasmEmitter) -> Register:
    dcb = emitter.masked_address(emitter.load_gr32(SVC_PARAMETER_REGISTER))
    _required_open(emitter, dcb)
    return dcb


def _area(emitter: HlasmEmitter) -> Register:
    return emitter.masked_address(emitter.load_gr32(AREA_REGISTER))


def _end_of_data(emitter: HlasmEmitter, dcb: Register) -> None:
    exit_at = emitter.load_storage(dcb, EODAD_OFFSET, EODAD_BYTES)
    routine, missing = (emitter.fresh_label(p) for p in ("hl_eodad", "hl_no_eodad"))
    given = emitter.binop(BinopKind.GT, exit_at, emitter.int_(NO_EXIT))
    emitter.emit_inst(BranchIf(cond_reg=given, branch_targets=(routine, missing)))
    emitter.emit_inst(Label_(label=routine))
    emit_branch(emitter, exit_at)
    emitter.emit_inst(Label_(label=missing))
    emit_abend(emitter, END_OF_DATA_ABEND)


def _descriptor(emitter: HlasmEmitter, dcb: Register, data: Register) -> Register:
    length = emitter.binop(
        BinopKind.ADD, emitter.call(LIST_LEN, (data,)), emitter.int_(RDW_BYTES)
    )
    word = emitter.binop(BinopKind.MUL, length, emitter.int_(1 << 16))
    image = emitter.image(word, RDW_BYTES)
    kept = _selected(
        emitter, _variable(emitter, dcb), (emitter.int_(RDW_BYTES), emitter.int_(0))
    )
    return emitter.call(LIST_SLICE, (image, emitter.int_(0), kept))


def _read(emitter: HlasmEmitter, dcb: Register) -> Register:
    raw = _call(emitter, READ_RECORD, _ddname(emitter, dcb), emitter.str_(NO_KEY))
    ended = _outcome_is(emitter, raw, AccessCondition.END_OF_FILE)
    _when(emitter, ended, lambda: _end_of_data(emitter, dcb))
    text = _call(emitter, IO_DATA, raw)
    data = emitter.call(STRING_TO_BYTES, (text, emitter.str_(LATIN1)))
    return emitter.call(LIST_CONCAT, (_descriptor(emitter, dcb, data), data))


def _copy_byte(
    emitter: HlasmEmitter, record: Register, target: Register, at: Register
) -> None:
    after = emitter.binop(BinopKind.ADD, at, emitter.int_(ONE_BYTE))
    byte = emitter.call(LIST_SLICE, (record, at, after))
    emitter.write_bytes(target, at, ONE_BYTE, byte)


def _located(emitter: HlasmEmitter, dcb: Register) -> Register:
    buffer = emitter.load_field(_buffers_entry(emitter, dcb), BUFFER_FIELD)
    emitter.store_gr32(SVC_PARAMETER_REGISTER, buffer)
    return buffer


def _target(emitter: HlasmEmitter, dcb: Register) -> Register:
    moved, located, done = (
        emitter.fresh_label(p) for p in ("hl_get_move", "hl_get_locate", "hl_get_to")
    )
    locate = _locates(emitter, dcb, GET_LOCATE)
    emitter.emit_inst(BranchIf(cond_reg=locate, branch_targets=(located, moved)))
    emitter.emit_inst(Label_(label=moved))
    emitter.store_var(SELECTED_VAR, _area(emitter))
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=located))
    emitter.store_var(SELECTED_VAR, _located(emitter, dcb))
    emitter.emit_inst(Label_(label=done))
    return emitter.load_var(SELECTED_VAR)


def emit_get(emitter: HlasmEmitter) -> None:
    dcb = _opened_dcb(emitter)
    record = _read(emitter, dcb)
    target = _target(emitter, dcb)
    length = emitter.call(LIST_LEN, (record,))
    emit_byte_loop(emitter, length, lambda at: _copy_byte(emitter, record, target, at))


def _put_located(emitter: HlasmEmitter, dcb: Register) -> None:
    entry = _buffers_entry(emitter, dcb)
    _write_pending(emitter, dcb, entry)
    _set_pending(emitter, entry, 1)
    emitter.store_gr32(SVC_PARAMETER_REGISTER, emitter.load_field(entry, BUFFER_FIELD))


def emit_put(emitter: HlasmEmitter) -> None:
    dcb = _opened_dcb(emitter)
    moved, located, done = (
        emitter.fresh_label(p) for p in ("hl_put_move", "hl_put_locate", "hl_put_done")
    )
    locate = _locates(emitter, dcb, PUT_LOCATE)
    emitter.emit_inst(BranchIf(cond_reg=locate, branch_targets=(located, moved)))
    emitter.emit_inst(Label_(label=moved))
    _write(emitter, dcb, _area(emitter))
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=located))
    _put_located(emitter, dcb)
    emitter.emit_inst(Label_(label=done))


def _flush(emitter: HlasmEmitter, dcb: Register) -> None:
    entry = _buffers_entry(emitter, dcb)
    _write_pending(emitter, dcb, entry)
    _set_pending(emitter, entry, 0)


def _closed(emitter: HlasmEmitter, dcb: Register) -> None:
    _when(emitter, _locates(emitter, dcb, PUT_LOCATE), lambda: _flush(emitter, dcb))
    _call(emitter, CLOSE_FILE, _ddname(emitter, dcb))
    _mark(emitter, dcb, BinopKind.BIT_AND, ~OPEN_FLAG & 0xFF)


def _close_entry(emitter: HlasmEmitter, dcb: Register, option: Register) -> None:
    _when(emitter, _is_open(emitter, dcb), lambda: _closed(emitter, dcb))


def emit_close(emitter: HlasmEmitter) -> None:
    _each_entry(emitter, _close_entry)
    emitter.store_gr32(RETURN_CODE_REGISTER, emitter.int_(0))
