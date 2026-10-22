# pyright: standard
"""SVC 35 in IR: the text of the WTO list at R1, decoded from EBCDIC, as one console line."""

from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    BINARY_BYTES_TO_INT,
    BYTES_TO_STRING,
    EBCDIC,
    LIST_CONCAT,
    MAKE_LIST,
    PRINTLN,
    SVC_PARAMETER_REGISTER,
    WTO_AT_VAR,
    WTO_HEADER_BYTES,
    WTO_LENGTH_BYTES,
    WTO_TEXT_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import (
    Branch,
    BranchIf,
    Const,
    Label_,
    StoreVar,
)
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def _text_length(emitter: HlasmEmitter, wto_list: Register) -> Register:
    header = emitter.load_bytes(wto_list, emitter.int_(0), WTO_LENGTH_BYTES)
    unsigned = emitter.fresh_reg()
    emitter.emit_inst(Const.bool_(unsigned, False))
    total = emitter.call(BINARY_BYTES_TO_INT, (header, unsigned))
    return emitter.binop(BinopKind.SUB, total, emitter.int_(WTO_HEADER_BYTES))


def _append_byte(emitter: HlasmEmitter, wto_list: Register, at: Register) -> None:
    offset = emitter.binop(BinopKind.ADD, at, emitter.int_(WTO_HEADER_BYTES))
    byte = emitter.load_bytes(wto_list, offset, 1)
    text = emitter.call(LIST_CONCAT, (emitter.load_var(WTO_TEXT_VAR), byte))
    emitter.emit_inst(StoreVar(name=WTO_TEXT_VAR, value_reg=text))
    after = emitter.binop(BinopKind.ADD, at, emitter.int_(1))
    emitter.emit_inst(StoreVar(name=WTO_AT_VAR, value_reg=after))


def _start_text(emitter: HlasmEmitter) -> None:
    empty = emitter.call(MAKE_LIST, (emitter.int_(0), emitter.int_(0)))
    emitter.emit_inst(StoreVar(name=WTO_TEXT_VAR, value_reg=empty))
    emitter.emit_inst(StoreVar(name=WTO_AT_VAR, value_reg=emitter.int_(0)))


def _read_text(emitter: HlasmEmitter, wto_list: Register, length: Register) -> None:
    _start_text(emitter)
    loop, body, done = (
        emitter.fresh_label(prefix)
        for prefix in ("hl_wto_loop", "hl_wto_byte", "hl_wto_done")
    )
    emitter.emit_inst(Label_(label=loop))
    at = emitter.load_var(WTO_AT_VAR)
    more = emitter.binop(BinopKind.LT, at, length)
    emitter.emit_inst(BranchIf(cond_reg=more, branch_targets=(body, done)))
    emitter.emit_inst(Label_(label=body))
    _append_byte(emitter, wto_list, at)
    emitter.emit_inst(Branch(label=loop))
    emitter.emit_inst(Label_(label=done))


def emit_write_to_operator(emitter: HlasmEmitter) -> None:
    wto_list = emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_gr32(SVC_PARAMETER_REGISTER),
        emitter.int_(ADDRESS_MASK_31),
    )
    _read_text(emitter, wto_list, _text_length(emitter, wto_list))
    text = emitter.call(
        BYTES_TO_STRING, (emitter.load_var(WTO_TEXT_VAR), emitter.str_(EBCDIC))
    )
    emitter.call(PRINTLN, (text,))
