# pyright: standard
"""COMPARE LOGICAL STRING: compares up to the ending character in GR0 bits 56-63 in one execution; an operand that ends first is low, and on inequality R1 and R2 point at the last bytes processed."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import advance
from interpreter.hlasm.effective_address import register_address
from interpreter.hlasm.ending_character import ending_character
from interpreter.hlasm.hlasm_constants import BYTE_LOOP_AT_VAR, ONE_BYTE
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_registers import advance_address, operand_pairs
from interpreter.hlasm.unequal_order import (
    FIRST_HIGH_CC,
    FIRST_LOW_CC,
    emit_cc_constant,
    emit_unequal_order,
)
from interpreter.instructions import BranchIf, Label_, StoreVar
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Images = tuple[Register, Register]

EQUAL_CC = 0


def _branch_if_equal(
    emitter: HlasmEmitter, images: Images, targets: tuple[CodeLabel, CodeLabel]
) -> None:
    left, right = images
    equal = emitter.binop(BinopKind.EQ, left, right)
    emitter.emit_inst(BranchIf(cond_reg=equal, branch_targets=targets))


def _compare_bytes(
    emitter: HlasmEmitter,
    addresses: tuple[Register, Register],
    ending: Register,
    exits: tuple[CodeLabel, CodeLabel, CodeLabel],
) -> tuple[Register, Images]:
    ended, unequal, more = exits
    at = emitter.load_var(BYTE_LOOP_AT_VAR)
    first, second = (emitter.load_bytes(a, at, ONE_BYTE) for a in addresses)
    same = emitter.fresh_label("hl_clst_same")
    _branch_if_equal(emitter, (first, second), (same, unequal))
    emitter.emit_inst(Label_(label=same))
    _branch_if_equal(emitter, (first, ending), (ended, more))
    emitter.emit_inst(Label_(label=more))
    return at, (first, second)


def _scan(
    emitter: HlasmEmitter,
    addresses: tuple[Register, Register],
    ending: Register,
    exits: tuple[CodeLabel, CodeLabel],
) -> tuple[Register, Images]:
    step = emitter.int_(ONE_BYTE)
    emitter.emit_inst(StoreVar(name=BYTE_LOOP_AT_VAR, value_reg=emitter.int_(0)))
    loop, more = emitter.fresh_label("hl_clst_loop"), emitter.fresh_label(
        "hl_clst_more"
    )
    emitter.emit_inst(Label_(label=loop))
    at, images = _compare_bytes(emitter, addresses, ending, (*exits, more))
    advance(emitter, at, step, loop)
    return at, images


def _ended_first(
    emitter: HlasmEmitter, ended: tuple[CodeLabel, CodeLabel], then: CodeLabel
) -> None:
    first_ended, second_ended = ended
    emit_cc_constant(emitter, FIRST_LOW_CC, first_ended, then)
    emit_cc_constant(emitter, FIRST_HIGH_CC, second_ended, then)


def _unequal_cc(
    emitter: HlasmEmitter,
    images: Images,
    ending: Register,
    labels: tuple[CodeLabel, CodeLabel],
) -> None:
    unequal, then = labels
    emitter.emit_inst(Label_(label=unequal))
    first, second = images
    first_ended, check_second, second_ended, both_continue = (
        emitter.fresh_label(prefix)
        for prefix in (
            "hl_clst_first_end",
            "hl_clst_check",
            "hl_clst_second_end",
            "hl_clst_bytes",
        )
    )
    _branch_if_equal(emitter, (first, ending), (first_ended, check_second))
    emitter.emit_inst(Label_(label=check_second))
    _branch_if_equal(emitter, (second, ending), (second_ended, both_continue))
    emitter.emit_inst(Label_(label=both_continue))
    emit_unequal_order(emitter, images, then)
    _ended_first(emitter, (first_ended, second_ended), then)


def _point_at(
    emitter: HlasmEmitter,
    pairs: tuple[int, int],
    addresses: tuple[Register, Register],
    at: Register,
    point: CodeLabel,
) -> None:
    emitter.emit_inst(Label_(label=point))
    advance_address(emitter, pairs[0], addresses[0], at)
    advance_address(emitter, pairs[1], addresses[1], at)


def compare_string(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    pairs = operand_pairs(statement)
    ending = emitter.image(ending_character(emitter), ONE_BYTE)
    addresses = (
        register_address(emitter, pairs[0]),
        register_address(emitter, pairs[1]),
    )
    ended, unequal, point, done = (
        emitter.fresh_label(prefix)
        for prefix in (
            "hl_clst_ended",
            "hl_clst_unequal",
            "hl_clst_point",
            "hl_clst_done",
        )
    )
    at, images = _scan(emitter, addresses, ending, (ended, unequal))
    emit_cc_constant(emitter, EQUAL_CC, ended, done)
    _unequal_cc(emitter, images, ending, (unequal, point))
    _point_at(emitter, pairs, addresses, at, point)
    emitter.emit_inst(Label_(label=done))
