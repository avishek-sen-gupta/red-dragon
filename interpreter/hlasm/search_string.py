# pyright: standard
"""SEARCH STRING and SEARCH STRING UNICODE: search from R2 for the GR0 character, one unit at a time while the unit starts before the address in R1, in one execution; found puts its address in R1 with CC 1, otherwise CC 2 leaves both registers."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import emit_scan_loop
from interpreter.hlasm.effective_address import register_address
from interpreter.hlasm.ending_character import ending_unit
from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    HALFWORD_BYTES,
    ONE_BYTE,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_registers import operand_pairs, store_address
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.unit_value import UnitReader, unit_reader
from interpreter.instructions import Branch, BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

FOUND_CC = 1
NOT_FOUND_CC = 2


def _stop_if_equal(
    emitter: HlasmEmitter,
    search: tuple[UnitReader, Register, Register],
    at: Register,
    found: CodeLabel,
) -> None:
    read, start, character = search
    more = emitter.fresh_label("hl_srst_more")
    equal = emitter.binop(BinopKind.EQ, read(start, at), character)
    emitter.emit_inst(BranchIf(cond_reg=equal, branch_targets=(found, more)))
    emitter.emit_inst(Label_(label=more))


def _length(emitter: HlasmEmitter, start: Register, end: Register) -> Register:
    return emitter.binop(
        BinopKind.BIT_AND,
        emitter.binop(BinopKind.SUB, end, start),
        emitter.int_(ADDRESS_MASK_31),
    )


def _outcome(
    emitter: HlasmEmitter,
    first: int,
    found_at: tuple[Register, Register],
    found: CodeLabel,
) -> None:
    start, at = found_at
    done = emitter.fresh_label("hl_srst_done")
    emitter.set_cc(emitter.int_(NOT_FOUND_CC))
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=found))
    store_address(emitter, first, emitter.binop(BinopKind.ADD, start, at))
    emitter.set_cc(emitter.int_(FOUND_CC))
    emitter.emit_inst(Label_(label=done))


def _search(width: int) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        first, second = operand_pairs(statement)
        character = ending_unit(emitter, width)
        start = register_address(emitter, second)
        length = _length(emitter, start, register_address(emitter, first))
        search = (unit_reader(emitter, width), start, character)
        found = emitter.fresh_label("hl_srst_found")
        at, _ = emit_scan_loop(
            emitter,
            (emitter.int_(0), length),
            width,
            lambda at: _stop_if_equal(emitter, search, at, found),
        )
        _outcome(emitter, first, (start, at), found)

    return lower


SEARCH_STRING = _search(ONE_BYTE)
SEARCH_STRING_UNICODE = _search(HALFWORD_BYTES)
