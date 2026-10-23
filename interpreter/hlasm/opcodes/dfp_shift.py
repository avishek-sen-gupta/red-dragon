# pyright: standard
"""DFP SHIFT SIGNIFICAND LEFT and RIGHT in IR on the decoded fields (ruling R44, PoO 20-54, 20-55): a finite number shifts all its digits, an infinity or NaN its trailing digits (the encoder keeps only those), and the exponent and kind stay."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import keep, storage_address_at
from interpreter.hlasm.dfp_layout import EXTENDED_DFP, LONG_DFP, DfpLayout
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.dfp_ir import decoded, fields_of, store_fields
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fpr_images import FIRST, SECOND, THIRD, fpr
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Shift = Callable[[HlasmEmitter, Register, Register, Register], Register]

SHIFT_BITS = 0b111111


def _left(
    emitter: HlasmEmitter, digits: Register, scale: Register, modulus: Register
) -> Register:
    shifted = emitter.binop(BinopKind.MUL, digits, scale)
    return emitter.binop(BinopKind.MOD, shifted, modulus)


def _right(
    emitter: HlasmEmitter, digits: Register, scale: Register, modulus: Register
) -> Register:
    return emitter.binop(BinopKind.FLOOR_DIV, digits, scale)


def _shift(layout: DfpLayout, shift: Shift) -> StatementLowering:
    source = decoded(fpr(SECOND, layout), layout)
    address = storage_address_at(THIRD)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        count = keep(SHIFT_BITS)(emitter, address(emitter, statement))
        sign, exponent, digits = fields_of(emitter, source(emitter, statement))
        scale = emitter.binop(BinopKind.POWER, emitter.int_(10), count)
        modulus = emitter.int_(10**layout.format.precision)
        shifted = shift(emitter, digits, scale, modulus)
        fields = (sign, exponent, shifted)
        store_fields(emitter, reg_operand(statement, FIRST), layout, fields)

    return lower


DFP_SHIFT_LOWERINGS: Mapping[str, StatementLowering] = {
    "SLDT": _shift(LONG_DFP, _left),
    "SLXT": pairs((FIRST, SECOND), _shift(EXTENDED_DFP, _left)),
    "SRDT": _shift(LONG_DFP, _right),
    "SRXT": pairs((FIRST, SECOND), _shift(EXTENDED_DFP, _right)),
}
