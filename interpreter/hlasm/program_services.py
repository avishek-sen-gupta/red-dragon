# pyright: standard
"""SVC 6, 8 and 9 in IR: LINK calls the named program through the far branch and gives back R2-R14, LOAD answers its entry and length from the names table or abends 806, DELETE succeeds."""

from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.branch_dispatch import emit_branch
from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    AMODE_31_LINK_BIT,
    BYTES_TO_STRING,
    EBCDIC,
    FAR_BRANCH_FUNCTION,
    LINK_REGISTER,
    NAME_ADDRESS_FIELD,
    NAME_LENGTH_FIELD,
    NAMES_VAR,
    PROGRAM_ENTRY_PREFIX,
    PROGRAM_NAME_BYTES,
    PROGRAM_NOT_FOUND_ABEND,
    PROGRAM_NOT_FOUND_CODE,
    PROGRAM_NOT_FOUND_REASON,
    RETURN_CODE_REGISTER,
    RETURN_SENTINEL,
    STRING_CONCAT_PAIR,
    STRING_FIND,
    STRING_SLICE,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.storage_services import TABLE_HOLDS
from interpreter.hlasm.unresolved_call import emit_unresolved_call
from interpreter.instructions import Branch, BranchIf, Label_, LoadField, LoadIndex
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

NAME_REGISTER = 0
LENGTH_REGISTER = 1
ERROR_EXIT_REGISTER = 15
FIRST_KEPT_REGISTER = 2
LAST_KEPT_REGISTER = 14
NOTHING_BELOW = 0
NO_MODULE = 0
LINKING = 1
NAME_END = " "


def _name_at(emitter: HlasmEmitter) -> Register:
    return emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_gr32(NAME_REGISTER),
        emitter.int_(ADDRESS_MASK_31),
    )


def _field(emitter: HlasmEmitter, entry: Register, name: FieldName) -> Register:
    value = emitter.fresh_reg()
    emitter.emit_inst(LoadField(result_reg=value, obj_reg=entry, field_name=name))
    return value


def _named(
    emitter: HlasmEmitter, name_at: Register, labels: tuple[CodeLabel, CodeLabel]
) -> Register:
    found, missing = labels
    table = emitter.load_var(NAMES_VAR)
    name_image = emitter.load_storage(name_at, 0, PROGRAM_NAME_BYTES)
    held = emitter.call(TABLE_HOLDS, (table, name_image))
    emitter.emit_inst(BranchIf(cond_reg=held, branch_targets=(found, missing)))
    emitter.emit_inst(Label_(label=found))
    entry = emitter.fresh_reg()
    emitter.emit_inst(LoadIndex(result_reg=entry, arr_reg=table, index_reg=name_image))
    return entry


def _labels(emitter: HlasmEmitter, service: str) -> tuple[CodeLabel, ...]:
    return tuple(
        emitter.fresh_label(f"hl_{service}_{part}")
        for part in ("found", "missing", "done")
    )


def _entry_name(emitter: HlasmEmitter, name_at: Register) -> Register:
    image = emitter.load_bytes(name_at, emitter.int_(0), PROGRAM_NAME_BYTES)
    text = emitter.call(BYTES_TO_STRING, (image, emitter.str_(EBCDIC)))
    ended = emitter.call(STRING_CONCAT_PAIR, (text, emitter.str_(NAME_END)))
    length = emitter.call(STRING_FIND, (ended, emitter.str_(NAME_END)))
    name = emitter.call(STRING_SLICE, (text, emitter.int_(0), length))
    return emitter.call(STRING_CONCAT_PAIR, (emitter.str_(PROGRAM_ENTRY_PREFIX), name))


def _link_found(emitter: HlasmEmitter, entry: Register) -> None:
    kept = range(FIRST_KEPT_REGISTER, LAST_KEPT_REGISTER + 1)
    saved = [emitter.load_gr64(r) for r in kept]
    address = _field(emitter, entry, NAME_ADDRESS_FIELD)
    emitter.store_gr32(LINK_REGISTER, emitter.int_(RETURN_SENTINEL))
    emitter.store_gr32(RETURN_CODE_REGISTER, address)
    emitter.call(
        FuncName(FAR_BRANCH_FUNCTION),
        (
            address,
            emitter.int_(NOTHING_BELOW),
            emitter.int_(NO_MODULE),
            emitter.int_(LINKING),
        ),
    )
    _ = [emitter.store_gr64(r, value) for r, value in zip(kept, saved, strict=True)]


def emit_link(emitter: HlasmEmitter) -> None:
    found, missing, done = _labels(emitter, "link")
    name_at = _name_at(emitter)
    _link_found(emitter, _named(emitter, name_at, (found, missing)))
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=missing))
    result = emit_unresolved_call(emitter, _entry_name(emitter, name_at))
    emitter.store_gr32(RETURN_CODE_REGISTER, result)
    emitter.emit_inst(Label_(label=done))


def _load_found(emitter: HlasmEmitter, entry: Register) -> None:
    address = _field(emitter, entry, NAME_ADDRESS_FIELD)
    emitter.store_gr32(
        NAME_REGISTER,
        emitter.binop(BinopKind.BIT_OR, address, emitter.int_(AMODE_31_LINK_BIT)),
    )
    emitter.store_gr32(LENGTH_REGISTER, _field(emitter, entry, NAME_LENGTH_FIELD))
    emitter.store_gr32(RETURN_CODE_REGISTER, emitter.int_(0))


def _load_missing(emitter: HlasmEmitter, error_exit: Register) -> None:
    taken, abend = (emitter.fresh_label(f"hl_load_{p}") for p in ("erret", "abend"))
    has_exit = emitter.binop(BinopKind.NE, error_exit, emitter.int_(0))
    emitter.emit_inst(BranchIf(cond_reg=has_exit, branch_targets=(taken, abend)))
    emitter.emit_inst(Label_(label=taken))
    emitter.store_gr32(LENGTH_REGISTER, emitter.int_(PROGRAM_NOT_FOUND_CODE))
    emitter.store_gr32(RETURN_CODE_REGISTER, emitter.int_(PROGRAM_NOT_FOUND_REASON))
    emit_branch(emitter, error_exit)
    emitter.emit_inst(Label_(label=abend))
    emit_abend(emitter, PROGRAM_NOT_FOUND_ABEND)


def emit_load(emitter: HlasmEmitter) -> None:
    found, missing, done = _labels(emitter, "load")
    error_exit = emitter.load_gr32(ERROR_EXIT_REGISTER)
    _load_found(emitter, _named(emitter, _name_at(emitter), (found, missing)))
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=missing))
    _load_missing(emitter, error_exit)
    emitter.emit_inst(Label_(label=done))


def emit_delete(emitter: HlasmEmitter) -> None:
    emitter.store_gr32(RETURN_CODE_REGISTER, emitter.int_(0))
