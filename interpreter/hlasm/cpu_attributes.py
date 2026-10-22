# pyright: standard
"""ECAG: constant z17-like cache and CPU attributes (ruling R37), selected by bits 40-63 of the second-operand address; a reserved or unprovided selection gives all ones."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.effective_address import effective_address
from interpreter.hlasm.hlasm_constants import WORD_BITS
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import reg_operand, storage_operand
from interpreter.hlasm.range_dispatch import emit_range_dispatch
from interpreter.instructions import Branch, BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

SELECTION_BITS = 0xFFFFFF
RESERVED_BITS = 0xFFFC00
SELECTOR_BITS = 0x1FF
TYPE_INDICATION_BITS = 1
ATTRIBUTE_OPERAND = 2
NOT_PROVIDED = 0xFFFFFFFF_FFFFFFFF
TOPOLOGY = 0x04070B0B_00000000
LINE_BYTES = 256
MEBIBYTE = 1 << 20
CPU_SPEED = 5500
CPU_SPEEDS = (CPU_SPEED << WORD_BITS) | CPU_SPEED

ATTRIBUTE_RANGES = (
    (8, TOPOLOGY),
    (12, LINE_BYTES),
    (16, NOT_PROVIDED),
    (17, 128 * 1024),
    (18, 36 * MEBIBYTE),
    (19, 360 * MEBIBYTE),
    (20, 2880 * MEBIBYTE),
    (24, NOT_PROVIDED),
    (25, 8),
    (26, 18),
    (28, 48),
    (128, NOT_PROVIDED),
    (136, CPU_SPEEDS),
)


def _attribute(
    emitter: HlasmEmitter, r1: int, entry: tuple[int, CodeLabel], join: CodeLabel
) -> None:
    value, label = entry
    emitter.emit_inst(Label_(label=label))
    emitter.store_gr64(r1, emitter.int_(value))
    emitter.emit_inst(Branch(label=join))


def _selector(emitter: HlasmEmitter, code: Register) -> Register:
    moved = emitter.binop(BinopKind.RSHIFT, code, emitter.int_(TYPE_INDICATION_BITS))
    return emitter.binop(BinopKind.BIT_AND, moved, emitter.int_(SELECTOR_BITS))


def _reserved(emitter: HlasmEmitter, code: Register) -> Register:
    bits = emitter.binop(BinopKind.BIT_AND, code, emitter.int_(RESERVED_BITS))
    return emitter.binop(BinopKind.NE, bits, emitter.int_(0))


def _value_labels(emitter: HlasmEmitter) -> Mapping[int, CodeLabel]:
    values = sorted({value for _, value in ATTRIBUTE_RANGES} | {NOT_PROVIDED})
    return {value: emitter.fresh_label("hl_cpu_attribute") for value in values}


def _dispatch(
    emitter: HlasmEmitter, code: Register, labels: Mapping[int, CodeLabel]
) -> None:
    selected = emitter.fresh_label("hl_cpu_selected")
    emitter.emit_inst(
        BranchIf(
            cond_reg=_reserved(emitter, code),
            branch_targets=(labels[NOT_PROVIDED], selected),
        )
    )
    emitter.emit_inst(Label_(label=selected))
    emit_range_dispatch(
        emitter,
        _selector(emitter, code),
        tuple((bound, labels[value]) for bound, value in ATTRIBUTE_RANGES),
        labels[NOT_PROVIDED],
    )


def lower_extract_cpu_attribute(
    emitter: HlasmEmitter, statement: MachineStatement
) -> None:
    r1 = reg_operand(statement, 0)
    address = effective_address(emitter, storage_operand(statement, ATTRIBUTE_OPERAND))
    code = emitter.binop(BinopKind.BIT_AND, address, emitter.int_(SELECTION_BITS))
    labels = _value_labels(emitter)
    join = emitter.fresh_label("hl_cpu_attribute_done")
    _dispatch(emitter, code, labels)
    _ = [_attribute(emitter, r1, entry, join) for entry in labels.items()]
    emitter.emit_inst(Label_(label=join))
