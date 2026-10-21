# pyright: standard
"""Shift and rotate opcodes: single and double, logical and signed shifts, rotates, and the ROTATE THEN ... SELECTED BITS family."""

from collections.abc import Callable, Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.data_movement import (
    REGISTER_OPERAND,
    Sink,
    Source,
    from_even_odd_pair,
    from_gr32,
    from_gr64,
    to_even_odd_pair,
    to_gr32,
    to_gr64,
)
from interpreter.hlasm.effective_address import effective_address
from interpreter.hlasm.fixed_point_overflow import emit_fixed_point_overflow_check
from interpreter.hlasm.fixed_width_ir import (
    build_nonzero_ir,
    build_rotate_left_ir,
    build_shift_left_logical_ir,
    build_shift_left_signed_cc_ir,
    build_shift_right_logical_ir,
    build_shift_right_signed_cc_ir,
    build_sign_cc_ir,
)
from interpreter.hlasm.hlasm_constants import (
    CC_VAR,
    DOUBLEWORD_BITS,
    PARAM_LEFT,
    PARAM_RIGHT,
    PARAM_VALUE,
    REGISTER_MASK,
    SPECIFICATION_EXCEPTION_ABEND,
    WORD_BITS,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_ir
from interpreter.hlasm.opcodes.result_and_cc import result_and_cc
from interpreter.hlasm.operands import (
    imm_operand,
    optional_imm_operand,
    reg_operand,
    storage_operand,
)
from interpreter.hlasm.register_span import (
    HIGH_WORD,
    LOW_WORD,
    WHOLE_REGISTER,
    RegisterSpan,
)
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import InstructionBase
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Operation = Sequence[InstructionBase]
type SetCc = Callable[[HlasmEmitter, Register], None]

SHIFT_AMOUNT_MASK = 0x3F
CONTROL_BIT = 0x80
SECOND_REGISTER = 1
START_FIELD = 2
END_FIELD = 3
ROTATE_FIELD = 4
NO_ROTATION = 0

ROTATE_64 = build_rotate_left_ir("hlasm.rll64", DOUBLEWORD_BITS)
SIGN_CC_64 = build_sign_cc_ir("hlasm.sign64", DOUBLEWORD_BITS)
NONZERO_64 = build_nonzero_ir("hlasm.nonzero64", DOUBLEWORD_BITS)


def _shift_amount(index: int) -> Source:
    def amount(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
        address = effective_address(emitter, storage_operand(statement, index))
        return emitter.binop(
            BinopKind.BIT_AND, address, emitter.int_(SHIFT_AMOUNT_MASK)
        )

    return amount


def _logical(
    operation: Operation, value: Source, amount: Source, sink: Sink
) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        arguments = {
            PARAM_LEFT: value(emitter, statement),
            PARAM_RIGHT: amount(emitter, statement),
        }
        sink(emitter, statement, inline_ir(emitter, operation, arguments))

    return lower


def _signed(
    operation: Operation, value: Source, amount: Source, sink: Sink
) -> StatementLowering:
    return result_and_cc(operation, ((PARAM_LEFT, value), (PARAM_RIGHT, amount)), sink)


def _overflowing(lowering: StatementLowering) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        lowering(emitter, statement)
        emit_fixed_point_overflow_check(emitter, emitter.load_var(CC_VAR))

    return lower


def _even_odd(lowering: StatementLowering) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        if reg_operand(statement, REGISTER_OPERAND) % 2:
            emit_abend(emitter, SPECIFICATION_EXCEPTION_ABEND)
            return
        lowering(emitter, statement)

    return lower


def _rotated(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    amount = optional_imm_operand(statement, ROTATE_FIELD, NO_ROTATION)
    return inline_ir(
        emitter,
        ROTATE_64,
        {
            PARAM_LEFT: emitter.load_gr64(reg_operand(statement, SECOND_REGISTER)),
            PARAM_RIGHT: emitter.int_(amount & SHIFT_AMOUNT_MASK),
        },
    )


def _masked(emitter: HlasmEmitter, value: Register, mask: int) -> Register:
    return emitter.binop(BinopKind.BIT_AND, value, emitter.int_(mask))


def _sign_cc(emitter: HlasmEmitter, result: Register) -> None:
    emitter.set_cc(inline_ir(emitter, SIGN_CC_64, {PARAM_VALUE: result}))


def _cc_unchanged(emitter: HlasmEmitter, result: Register) -> None:
    return


def _insert(span: RegisterSpan, set_cc: SetCc) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        end = imm_operand(statement, END_FIELD)
        selected = span.selected(imm_operand(statement, START_FIELD), end)
        cleared = span.word() if end & CONTROL_BIT else selected
        rotated = _rotated(emitter, statement)
        r1 = reg_operand(statement, REGISTER_OPERAND)
        kept = _masked(emitter, emitter.load_gr64(r1), REGISTER_MASK & ~cleared)
        result = emitter.binop(
            BinopKind.BIT_OR, kept, _masked(emitter, rotated, selected)
        )
        emitter.store_gr64(r1, result)
        set_cc(emitter, result)

    return lower


def _selected_bits(operator: BinopKind) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        start = imm_operand(statement, START_FIELD)
        selected = WHOLE_REGISTER.selected(start, imm_operand(statement, END_FIELD))
        rotated = _rotated(emitter, statement)
        r1 = reg_operand(statement, REGISTER_OPERAND)
        first = emitter.load_gr64(r1)
        combined = _masked(emitter, emitter.binop(operator, first, rotated), selected)
        emitter.set_cc(inline_ir(emitter, NONZERO_64, {PARAM_VALUE: combined}))
        if start & CONTROL_BIT:
            return
        _replace_selected(emitter, r1, (first, combined), selected)

    return lower


def _replace_selected(
    emitter: HlasmEmitter, r1: int, values: tuple[Register, Register], selected: int
) -> None:
    first, combined = values
    kept = _masked(emitter, first, REGISTER_MASK & ~selected)
    emitter.store_gr64(r1, emitter.binop(BinopKind.BIT_OR, kept, combined))


def _word(build: Callable[[str, int], Operation], name: str) -> Operation:
    return build(f"hlasm.{name}32", WORD_BITS)


def _doubleword(build: Callable[[str, int], Operation], name: str) -> Operation:
    return build(f"hlasm.{name}64", DOUBLEWORD_BITS)


SLL_32 = _word(build_shift_left_logical_ir, "sll")
SLL_64 = _doubleword(build_shift_left_logical_ir, "sll")
SRL_32 = _word(build_shift_right_logical_ir, "srl")
SRL_64 = _doubleword(build_shift_right_logical_ir, "srl")
RLL_32 = _word(build_rotate_left_ir, "rll")
SLA_32 = _word(build_shift_left_signed_cc_ir, "sla")
SLA_64 = _doubleword(build_shift_left_signed_cc_ir, "sla")
SRA_32 = _word(build_shift_right_signed_cc_ir, "sra")
SRA_64 = _doubleword(build_shift_right_signed_cc_ir, "sra")

AMOUNT_SECOND = _shift_amount(1)
AMOUNT_THIRD = _shift_amount(2)
OWN_WORD = from_gr32(0)
THIRD_WORD = from_gr32(1)
THIRD_DOUBLEWORD = from_gr64(1)

SINGLE_SHIFTS: Mapping[str, StatementLowering] = {
    "SLL": _logical(SLL_32, OWN_WORD, AMOUNT_SECOND, to_gr32),
    "SLLK": _logical(SLL_32, THIRD_WORD, AMOUNT_THIRD, to_gr32),
    "SLLG": _logical(SLL_64, THIRD_DOUBLEWORD, AMOUNT_THIRD, to_gr64),
    "SRL": _logical(SRL_32, OWN_WORD, AMOUNT_SECOND, to_gr32),
    "SRLK": _logical(SRL_32, THIRD_WORD, AMOUNT_THIRD, to_gr32),
    "SRLG": _logical(SRL_64, THIRD_DOUBLEWORD, AMOUNT_THIRD, to_gr64),
    "RLL": _logical(RLL_32, THIRD_WORD, AMOUNT_THIRD, to_gr32),
    "RLLG": _logical(ROTATE_64, THIRD_DOUBLEWORD, AMOUNT_THIRD, to_gr64),
    "SLA": _overflowing(_signed(SLA_32, OWN_WORD, AMOUNT_SECOND, to_gr32)),
    "SLAK": _overflowing(_signed(SLA_32, THIRD_WORD, AMOUNT_THIRD, to_gr32)),
    "SLAG": _overflowing(_signed(SLA_64, THIRD_DOUBLEWORD, AMOUNT_THIRD, to_gr64)),
    "SRA": _signed(SRA_32, OWN_WORD, AMOUNT_SECOND, to_gr32),
    "SRAK": _signed(SRA_32, THIRD_WORD, AMOUNT_THIRD, to_gr32),
    "SRAG": _signed(SRA_64, THIRD_DOUBLEWORD, AMOUNT_THIRD, to_gr64),
}

DOUBLE_SHIFTS: Mapping[str, StatementLowering] = {
    "SLDL": _even_odd(
        _logical(SLL_64, from_even_odd_pair, AMOUNT_SECOND, to_even_odd_pair)
    ),
    "SRDL": _even_odd(
        _logical(SRL_64, from_even_odd_pair, AMOUNT_SECOND, to_even_odd_pair)
    ),
    "SLDA": _even_odd(
        _overflowing(
            _signed(SLA_64, from_even_odd_pair, AMOUNT_SECOND, to_even_odd_pair)
        )
    ),
    "SRDA": _even_odd(
        _signed(SRA_64, from_even_odd_pair, AMOUNT_SECOND, to_even_odd_pair)
    ),
}

SELECTED_BITS: Mapping[str, StatementLowering] = {
    "RISBG": _insert(WHOLE_REGISTER, _sign_cc),
    "RISBGN": _insert(WHOLE_REGISTER, _cc_unchanged),
    "RISBHG": _insert(HIGH_WORD, _cc_unchanged),
    "RISBLG": _insert(LOW_WORD, _cc_unchanged),
    "RNSBG": _selected_bits(BinopKind.BIT_AND),
    "ROSBG": _selected_bits(BinopKind.BIT_OR),
    "RXSBG": _selected_bits(BinopKind.BIT_XOR),
}

SHIFT_ROTATE_LOWERINGS: Mapping[str, StatementLowering] = {
    **SINGLE_SHIFTS,
    **DOUBLE_SHIFTS,
    **SELECTED_BITS,
}
