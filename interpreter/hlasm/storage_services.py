# pyright: standard
"""SVC 10 and SVC 120 in IR: one region per request at an aligned address, recorded in the allocation table, and released only as obtained."""

from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    ALLOCATIONS_VAR,
    BYTE_MASK,
    DOUBLEWORD_BYTES,
    GETMAIN_FREEMAIN_ABEND,
    STORAGE_ABEND,
    SVC_PARAMETER_REGISTER,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.storage_request import StorageRequest
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
from interpreter.register import Register

TABLE_HOLDS = FuncName("dict_contains_key")
LENGTH_FIELD = FieldName("length")
SUBPOOL_FIELD = FieldName("subpool")
RELEASED_LENGTH = -1
PAGE_BYTES = 4096
LENGTH_REGISTER = 0
OPTIONS_REGISTER = 15
SVC_10_LENGTH_MASK = 0xFFFFFF
SVC_10_SUBPOOL_SHIFT = 24
SVC_120_SUBPOOL_SHIFT = 8
RELEASE_FLAG = 1
PAGE_FLAG = 4
PAGE_FLAG_SHIFT = 2
ADDRESS_SIGN_SHIFT = 31


def _flag(emitter: HlasmEmitter, word: Register, bit: int, shift: int) -> Register:
    masked = emitter.binop(BinopKind.BIT_AND, word, emitter.int_(bit))
    return emitter.binop(BinopKind.RSHIFT, masked, emitter.int_(shift))


def _rounded(emitter: HlasmEmitter, length: Register) -> Register:
    up = emitter.binop(BinopKind.ADD, length, emitter.int_(DOUBLEWORD_BYTES - 1))
    over = emitter.binop(BinopKind.MOD, up, emitter.int_(DOUBLEWORD_BYTES))
    return emitter.binop(BinopKind.SUB, up, over)


def _record(
    emitter: HlasmEmitter, address: Register, length: Register, subpool: Register
) -> None:
    entry = emitter.fresh_reg()
    emitter.emit_inst(NewObject(result_reg=entry))
    emitter.emit_inst(
        StoreField(obj_reg=entry, field_name=LENGTH_FIELD, value_reg=length)
    )
    emitter.emit_inst(
        StoreField(obj_reg=entry, field_name=SUBPOOL_FIELD, value_reg=subpool)
    )
    emitter.emit_inst(
        StoreIndex(
            arr_reg=emitter.load_var(ALLOCATIONS_VAR),
            index_reg=address,
            value_reg=entry,
        )
    )


def obtained(emitter: HlasmEmitter, request: StorageRequest) -> Register:
    rounded = _rounded(emitter, request.length)
    address = emitter.aligned_region(rounded, request.alignment)
    _record(emitter, address, rounded, request.subpool)
    return address


def _obtain(emitter: HlasmEmitter, request: StorageRequest) -> None:
    emitter.store_gr32(SVC_PARAMETER_REGISTER, obtained(emitter, request))


def _matches(
    emitter: HlasmEmitter, entry: Register, request: StorageRequest
) -> Register:
    same_length = emitter.binop(
        BinopKind.EQ,
        emitter.load_field(entry, LENGTH_FIELD),
        _rounded(emitter, request.length),
    )
    same_subpool = emitter.binop(
        BinopKind.EQ, emitter.load_field(entry, SUBPOOL_FIELD), request.subpool
    )
    return emitter.binop(BinopKind.AND, same_length, same_subpool)


def _entry(
    emitter: HlasmEmitter, address: Register, known: CodeLabel, bad: CodeLabel
) -> Register:
    table = emitter.load_var(ALLOCATIONS_VAR)
    held = emitter.call(TABLE_HOLDS, (table, address))
    emitter.emit_inst(BranchIf(cond_reg=held, branch_targets=(known, bad)))
    emitter.emit_inst(Label_(label=known))
    entry = emitter.fresh_reg()
    emitter.emit_inst(LoadIndex(result_reg=entry, arr_reg=table, index_reg=address))
    return entry


def _release(emitter: HlasmEmitter, request: StorageRequest) -> None:
    known, matches, bad, done = (
        emitter.fresh_label(prefix)
        for prefix in ("hl_known", "hl_matches", "hl_bad_release", "hl_released")
    )
    entry = _entry(emitter, _address(emitter), known, bad)
    same = _matches(emitter, entry, request)
    emitter.emit_inst(BranchIf(cond_reg=same, branch_targets=(matches, bad)))
    emitter.emit_inst(Label_(label=matches))
    emitter.emit_inst(
        StoreField(
            obj_reg=entry,
            field_name=LENGTH_FIELD,
            value_reg=emitter.int_(RELEASED_LENGTH),
        )
    )
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=bad))
    emit_abend(emitter, request.abend)
    emitter.emit_inst(Label_(label=done))


def _address(emitter: HlasmEmitter) -> Register:
    return emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_gr32(SVC_PARAMETER_REGISTER),
        emitter.int_(ADDRESS_MASK_31),
    )


def _obtain_or_release(
    emitter: HlasmEmitter, release: Register, request: StorageRequest
) -> None:
    obtain_label, release_label, done = (
        emitter.fresh_label(f"hl_storage_{part}")
        for part in ("obtain", "release", "done")
    )
    emitter.emit_inst(
        BranchIf(cond_reg=release, branch_targets=(release_label, obtain_label))
    )
    emitter.emit_inst(Label_(label=obtain_label))
    _obtain(emitter, request)
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=release_label))
    _release(emitter, request)
    emitter.emit_inst(Label_(label=done))


def emit_getmain_freemain(emitter: HlasmEmitter) -> None:
    r0 = emitter.load_gr32(LENGTH_REGISTER)
    sign = emitter.binop(
        BinopKind.RSHIFT,
        emitter.load_gr32(SVC_PARAMETER_REGISTER),
        emitter.int_(ADDRESS_SIGN_SHIFT),
    )
    request = StorageRequest(
        length=emitter.binop(BinopKind.BIT_AND, r0, emitter.int_(SVC_10_LENGTH_MASK)),
        subpool=emitter.binop(BinopKind.RSHIFT, r0, emitter.int_(SVC_10_SUBPOOL_SHIFT)),
        alignment=emitter.int_(DOUBLEWORD_BYTES),
        abend=GETMAIN_FREEMAIN_ABEND,
    )
    release = emitter.binop(BinopKind.EQ, sign, emitter.int_(0))
    _obtain_or_release(emitter, release, request)


def _alignment(emitter: HlasmEmitter, options: Register) -> Register:
    page = _flag(emitter, options, PAGE_FLAG, PAGE_FLAG_SHIFT)
    extra = emitter.binop(
        BinopKind.MUL, page, emitter.int_(PAGE_BYTES - DOUBLEWORD_BYTES)
    )
    return emitter.binop(BinopKind.ADD, extra, emitter.int_(DOUBLEWORD_BYTES))


def _subpool(emitter: HlasmEmitter, options: Register) -> Register:
    shifted = emitter.binop(
        BinopKind.RSHIFT, options, emitter.int_(SVC_120_SUBPOOL_SHIFT)
    )
    return emitter.binop(BinopKind.BIT_AND, shifted, emitter.int_(BYTE_MASK))


def emit_storage(emitter: HlasmEmitter) -> None:
    options = emitter.load_gr32(OPTIONS_REGISTER)
    request = StorageRequest(
        length=emitter.load_gr32(LENGTH_REGISTER),
        subpool=_subpool(emitter, options),
        alignment=_alignment(emitter, options),
        abend=STORAGE_ABEND,
    )
    release = emitter.binop(
        BinopKind.NE, _flag(emitter, options, RELEASE_FLAG, 0), emitter.int_(0)
    )
    _obtain_or_release(emitter, release, request)
    emitter.store_gr32(OPTIONS_REGISTER, emitter.int_(0))
