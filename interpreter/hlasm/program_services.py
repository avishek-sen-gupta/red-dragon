# pyright: standard
"""SVC 6, 8 and 9 in IR: LINK calls the program R15's list names through the far branch and leaves the registers as it left them, LOAD answers its entry and length from the names table and counts the load, or abends 806 unless R1's high bit asks for a return; DELETE releases a counted load or answers 4."""

from interpreter.func_name import FuncName
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.far_branch import FarBranch
from interpreter.hlasm.hlasm_constants import (
    AMODE_31_LINK_BIT,
    BYTES_TO_STRING,
    EBCDIC,
    FAR_BRANCH_FUNCTION,
    LINK_REGISTER,
    NAME_ADDRESS_FIELD,
    NAME_LENGTH_FIELD,
    NAME_LOADS_FIELD,
    NAMES_VAR,
    NOTHING_BELOW,
    PROGRAM_NAME_BYTES,
    PROGRAM_NOT_FOUND_ABEND,
    PROGRAM_NOT_FOUND_CODE,
    PROGRAM_NOT_FOUND_REASON,
    RETURN_CODE_REGISTER,
    RETURN_SENTINEL,
    STRING_CONCAT_PAIR,
    STRING_FIND,
    STRING_SLICE,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.program_entry import emit_program_entry_name
from interpreter.hlasm.storage_services import TABLE_HOLDS
from interpreter.hlasm.unresolved_call import emit_unresolved_call
from interpreter.instructions import (
    Branch,
    BranchIf,
    Label_,
    LoadIndex,
    StoreField,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

NAME_REGISTER = 0
LENGTH_REGISTER = 1
ERROR_RETURN_REGISTER = 1
CONTROL_LIST_REGISTER = 15
NOT_LOADED_CODE = 4
NO_MODULE = 0
LINKING = 1
NAME_END = " "


def _name_at(emitter: HlasmEmitter) -> Register:
    return emitter.masked_address(emitter.load_gr32(NAME_REGISTER))


def _listed_name_at(emitter: HlasmEmitter) -> Register:
    control = emitter.masked_address(emitter.load_gr32(CONTROL_LIST_REGISTER))
    return emitter.masked_address(emitter.load_storage(control, 0, WORD_BYTES))


def _named(
    emitter: HlasmEmitter, name: Register, labels: tuple[CodeLabel, CodeLabel]
) -> Register:
    found, missing = labels
    table = emitter.load_var(NAMES_VAR)
    held = emitter.call(TABLE_HOLDS, (table, name))
    emitter.emit_inst(BranchIf(cond_reg=held, branch_targets=(found, missing)))
    emitter.emit_inst(Label_(label=found))
    entry = emitter.fresh_reg()
    emitter.emit_inst(LoadIndex(result_reg=entry, arr_reg=table, index_reg=name))
    return entry


def _labels(emitter: HlasmEmitter, service: str) -> tuple[CodeLabel, ...]:
    return tuple(
        emitter.fresh_label(f"hl_{service}_{part}")
        for part in ("found", "missing", "done")
    )


def blank_ended_name(emitter: HlasmEmitter, name_at: Register) -> Register:
    image = emitter.load_bytes(name_at, emitter.int_(0), PROGRAM_NAME_BYTES)
    text = emitter.call(BYTES_TO_STRING, (image, emitter.str_(EBCDIC)))
    ended = emitter.call(STRING_CONCAT_PAIR, (text, emitter.str_(NAME_END)))
    length = emitter.call(STRING_FIND, (ended, emitter.str_(NAME_END)))
    return emitter.call(STRING_SLICE, (text, emitter.int_(0), length))


def _entry_name(emitter: HlasmEmitter, name_at: Register) -> Register:
    return emit_program_entry_name(emitter, blank_ended_name(emitter, name_at))


def _link_found(emitter: HlasmEmitter, entry: Register) -> None:
    address = emitter.load_field(entry, NAME_ADDRESS_FIELD)
    emitter.store_gr32(LINK_REGISTER, emitter.int_(RETURN_SENTINEL))
    emitter.store_gr32(RETURN_CODE_REGISTER, address)
    request = FarBranch(
        address,
        emitter.int_(NOTHING_BELOW),
        emitter.int_(NO_MODULE),
        emitter.int_(LINKING),
    )
    emitter.call(FuncName(FAR_BRANCH_FUNCTION), request.arguments())


def emit_link(emitter: HlasmEmitter) -> None:
    found, missing, done = _labels(emitter, "link")
    name = _entry_name(emitter, _listed_name_at(emitter))
    _link_found(emitter, _named(emitter, name, (found, missing)))
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=missing))
    result = emit_unresolved_call(emitter, name)
    emitter.store_gr32(RETURN_CODE_REGISTER, result)
    emitter.emit_inst(Label_(label=done))


def _load_found(emitter: HlasmEmitter, entry: Register) -> None:
    address = emitter.load_field(entry, NAME_ADDRESS_FIELD)
    emitter.store_gr32(
        NAME_REGISTER,
        emitter.binop(BinopKind.BIT_OR, address, emitter.int_(AMODE_31_LINK_BIT)),
    )
    emitter.store_gr32(LENGTH_REGISTER, emitter.load_field(entry, NAME_LENGTH_FIELD))
    emitter.store_gr32(RETURN_CODE_REGISTER, emitter.int_(0))
    _count_loads(emitter, entry, 1)


def _count_loads(emitter: HlasmEmitter, entry: Register, change: int) -> None:
    loads = emitter.binop(
        BinopKind.ADD, emitter.load_field(entry, NAME_LOADS_FIELD), emitter.int_(change)
    )
    emitter.emit_inst(
        StoreField(obj_reg=entry, field_name=NAME_LOADS_FIELD, value_reg=loads)
    )


def _load_missing(emitter: HlasmEmitter, returning: Register) -> None:
    taken, abend = (emitter.fresh_label(f"hl_load_{p}") for p in ("erret", "abend"))
    emitter.emit_inst(BranchIf(cond_reg=returning, branch_targets=(taken, abend)))
    emitter.emit_inst(Label_(label=abend))
    emit_abend(emitter, PROGRAM_NOT_FOUND_ABEND)
    emitter.emit_inst(Label_(label=taken))
    emitter.store_gr32(LENGTH_REGISTER, emitter.int_(PROGRAM_NOT_FOUND_CODE))
    emitter.store_gr32(RETURN_CODE_REGISTER, emitter.int_(PROGRAM_NOT_FOUND_REASON))


def emit_load(emitter: HlasmEmitter) -> None:
    found, missing, done = _labels(emitter, "load")
    returning = emitter.binop(
        BinopKind.GE,
        emitter.load_gr32(ERROR_RETURN_REGISTER),
        emitter.int_(AMODE_31_LINK_BIT),
    )
    _load_found(
        emitter,
        _named(emitter, _entry_name(emitter, _name_at(emitter)), (found, missing)),
    )
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=missing))
    _load_missing(emitter, returning)
    emitter.emit_inst(Label_(label=done))


def _delete_found(
    emitter: HlasmEmitter, entry: Register, not_loaded: CodeLabel
) -> None:
    held = emitter.fresh_label("hl_delete_held")
    loaded = emitter.binop(
        BinopKind.GT, emitter.load_field(entry, NAME_LOADS_FIELD), emitter.int_(0)
    )
    emitter.emit_inst(BranchIf(cond_reg=loaded, branch_targets=(held, not_loaded)))
    emitter.emit_inst(Label_(label=held))
    _count_loads(emitter, entry, -1)
    emitter.store_gr32(RETURN_CODE_REGISTER, emitter.int_(0))


def emit_delete(emitter: HlasmEmitter) -> None:
    found, missing, done = _labels(emitter, "delete")
    _delete_found(
        emitter,
        _named(emitter, _entry_name(emitter, _name_at(emitter)), (found, missing)),
        missing,
    )
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=missing))
    emitter.store_gr32(RETURN_CODE_REGISTER, emitter.int_(NOT_LOADED_CODE))
    emitter.emit_inst(Label_(label=done))
