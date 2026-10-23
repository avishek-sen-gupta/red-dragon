# pyright: standard
"""Statement-level DFP lowering parts: decoded operand sources, the rounding modifier and quantum control, stores through the encoder after delivery, and the condition code of a result (PoO 20-19, 20-20, figure 20-10)."""

from collections.abc import Callable

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bfp_slots import INEXACT_BIT, QUANTUM_BIT
from interpreter.hlasm.data_movement import Source, keep
from interpreter.hlasm.dfp_fields import INFINITY, QUIET_NAN
from interpreter.hlasm.dfp_layout import DfpLayout
from interpreter.hlasm.hlasm_constants import BYTE_MASK, FPC_VAR
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ieee_outcome import IeeeOutcome
from interpreter.hlasm.opcodes.bfp_forms import Deliver, SuppressedBits
from interpreter.hlasm.opcodes.bfp_ir import enabled_traps, field_at
from interpreter.hlasm.opcodes.dfp_codec import DECODERS, ENCODERS
from interpreter.hlasm.opcodes.floating_point_support import (
    DFP_MODE_SHIFT,
    MODE_FIELD,
)
from interpreter.hlasm.opcodes.fpr_images import list_item, pick, store_image
from interpreter.hlasm.operands import optional_mask_operand, reg_operand
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Fields = tuple[Register, Register, Register]
type AfterStore = Callable[[HlasmEmitter, Fields], None]

FPC_TO_MODIFIER = 8
QUANTUM_DXC = 0x04
CURRENT_MODE_CODES = frozenset({0, 2})
FIRST_SUPPRESSING_CODE = 8
NAN_CC = 3
POSITIVE_CC = 2
SIGN, EXPONENT, SIGNIFICAND = 0, 1, 2


def decoded(source: Source, layout: DfpLayout) -> Source:
    return lambda emitter, statement: DECODERS[layout].call(
        emitter, (source(emitter, statement),)
    )


def fields_of(emitter: HlasmEmitter, decoded_fields: Register) -> Fields:
    sign, exponent, significand = (
        list_item(emitter, decoded_fields, at) for at in (SIGN, EXPONENT, SIGNIFICAND)
    )
    return sign, exponent, significand


def current_dfp_mode(emitter: HlasmEmitter) -> Register:
    fpc = emitter.load_var(FPC_VAR)
    mode = keep(MODE_FIELD)(
        emitter, emitter.binop(BinopKind.RSHIFT, fpc, emitter.int_(DFP_MODE_SHIFT))
    )
    return emitter.binop(BinopKind.ADD, mode, emitter.int_(FPC_TO_MODIFIER))


def _code(statement: MachineStatement, index: int) -> int:
    return optional_mask_operand(statement, index, 0)


def dfp_modifier(index: int) -> Source:
    def mode(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
        code = _code(statement, index)
        if code in CURRENT_MODE_CODES:
            return current_dfp_mode(emitter)
        return emitter.int_(code)

    return mode


def quantum_control(index: int) -> SuppressedBits:
    def suppressed(statement: MachineStatement) -> int:
        code = _code(statement, index)
        return QUANTUM_BIT * (code == 0 or code >= FIRST_SUPPRESSING_CODE)

    return suppressed


def quantum_yields(
    emitter: HlasmEmitter, fpc: Register, outcome: IeeeOutcome
) -> IeeeOutcome:
    enabled = enabled_traps(emitter, fpc, outcome.trap)
    taken = emitter.binop(
        BinopKind.NE, keep(INEXACT_BIT)(emitter, enabled), emitter.int_(0)
    )
    unrecognized = emitter.binop(BinopKind.MUL, taken, emitter.int_(QUANTUM_BIT))
    kept = emitter.binop(BinopKind.BIT_XOR, unrecognized, emitter.int_(BYTE_MASK))
    return IeeeOutcome(
        emitter.binop(BinopKind.BIT_AND, outcome.trap, kept),
        emitter.binop(BinopKind.BIT_AND, outcome.flags, kept),
        outcome.scaled_dxc,
        pick(emitter, taken, outcome.inexact_dxc, emitter.int_(QUANTUM_DXC)),
    )


def and_inexact_control(
    quantum: SuppressedBits, inexact: SuppressedBits
) -> SuppressedBits:
    return lambda statement: quantum(statement) | inexact(statement)


def fields_cc(emitter: HlasmEmitter, fields: Fields) -> Register:
    sign, exponent, significand = fields
    nan = emitter.binop(BinopKind.LE, exponent, emitter.int_(QUIET_NAN))
    infinite = emitter.binop(BinopKind.EQ, exponent, emitter.int_(INFINITY))
    nonzero = emitter.binop(
        BinopKind.BIT_OR,
        emitter.binop(BinopKind.NE, significand, emitter.int_(0)),
        infinite,
    )
    signed = emitter.binop(BinopKind.SUB, emitter.int_(POSITIVE_CC), sign)
    number = emitter.binop(BinopKind.MUL, nonzero, signed)
    return pick(emitter, nan, emitter.int_(NAN_CC), number)


def set_fields_cc(emitter: HlasmEmitter, fields: Fields) -> None:
    emitter.set_cc(fields_cc(emitter, fields))


def no_cc(emitter: HlasmEmitter, fields: Fields) -> None:
    return None


def store_fields(
    emitter: HlasmEmitter, r: int, layout: DfpLayout, fields: Fields
) -> None:
    store_image(emitter, r, layout, ENCODERS[layout].call(emitter, fields))


def stored(index: int, layout: DfpLayout, after: AfterStore) -> Deliver:
    def deliver(
        emitter: HlasmEmitter,
        statement: MachineStatement,
        result: Register,
        slot: Register,
    ) -> None:
        sign, exponent, significand = (
            field_at(emitter, result, slot, at) for at in (SIGN, EXPONENT, SIGNIFICAND)
        )
        fields = (sign, exponent, significand)
        store_fields(emitter, reg_operand(statement, index), layout, fields)
        after(emitter, fields)

    return deliver
