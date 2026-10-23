# pyright: standard
"""The decimal instructions' program checks: a raised data condition stores DXC 00 in the FPC and abends S0C7 (PoO 6-17, 6-18), a divide condition S0CB, both suppressed; an overflow abends S0CA after completion when program-mask bit 0100 is on."""

from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.conditional import emit_when
from interpreter.hlasm.hlasm_constants import (
    DECIMAL_DIVIDE_ABEND,
    DECIMAL_OVERFLOW_ABEND,
    DECIMAL_OVERFLOW_MASK,
    PROGRAM_MASK_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.floating_point_support import (
    GENERAL_OPERAND_DXC,
    emit_coded_data_exception,
)
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def _abend_on(emitter: HlasmEmitter, raised: Register, code: str) -> None:
    emit_when(emitter, raised, lambda: emit_abend(emitter, code))


def _set(emitter: HlasmEmitter, bit: Register) -> Register:
    return emitter.binop(BinopKind.NE, bit, emitter.int_(0))


def emit_data_check(emitter: HlasmEmitter, invalid: Register) -> None:
    emit_when(
        emitter,
        _set(emitter, invalid),
        lambda: emit_coded_data_exception(emitter, GENERAL_OPERAND_DXC),
    )


def emit_decimal_divide_check(emitter: HlasmEmitter, raised: Register) -> None:
    _abend_on(emitter, raised, DECIMAL_DIVIDE_ABEND)


def emit_decimal_overflow_check(emitter: HlasmEmitter, overflow: Register) -> None:
    enabled = emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_var(PROGRAM_MASK_VAR),
        emitter.int_(DECIMAL_OVERFLOW_MASK),
    )
    trapped = emitter.binop(BinopKind.MUL, overflow, enabled)
    _abend_on(emitter, _set(emitter, trapped), DECIMAL_OVERFLOW_ABEND)
