# pyright: standard
"""SVC 13 in IR: R1's completion code as U<4 decimal digits> or S<3 hex digits>, then the abend."""

from functools import reduce

from interpreter.hlasm.hlasm_constants import (
    ABEND_VAR,
    COMPLETION_CODE_BITS,
    COMPLETION_CODE_MASK,
    HEX_DIGITS,
    NIBBLE_BITS,
    NIBBLE_MASK,
    STRING_CONCAT_PAIR,
    STRING_SLICE,
    STRING_ZFILL,
    SVC_PARAMETER_REGISTER,
    SYSTEM_ABEND_DIGITS,
    SYSTEM_ABEND_PREFIX,
    TO_STRING,
    USER_ABEND_DIGITS,
    USER_ABEND_PREFIX,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import BranchIf, Halt_, Label_, StoreVar
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def _field(emitter: HlasmEmitter, value: Register, shift: int, mask: int) -> Register:
    shifted = emitter.binop(BinopKind.RSHIFT, value, emitter.int_(shift))
    return emitter.binop(BinopKind.BIT_AND, shifted, emitter.int_(mask))


def _concat(emitter: HlasmEmitter, parts: tuple[Register, ...]) -> Register:
    return reduce(
        lambda left, right: emitter.call(STRING_CONCAT_PAIR, (left, right)), parts
    )


def _end(emitter: HlasmEmitter, prefix: str, digits: Register) -> None:
    code = _concat(emitter, (emitter.str_(prefix), digits))
    emitter.emit_inst(StoreVar(name=ABEND_VAR, value_reg=code))
    emitter.emit_inst(Halt_())


def _hex_digit(emitter: HlasmEmitter, code: Register, nibble: int) -> Register:
    value = _field(emitter, code, NIBBLE_BITS * nibble, NIBBLE_MASK)
    return emitter.call(
        STRING_SLICE, (emitter.str_(HEX_DIGITS), value, emitter.int_(1))
    )


def _system(emitter: HlasmEmitter, code: Register) -> None:
    digits = tuple(
        _hex_digit(emitter, code, nibble)
        for nibble in reversed(range(SYSTEM_ABEND_DIGITS))
    )
    _end(emitter, SYSTEM_ABEND_PREFIX, _concat(emitter, digits))


def _user(emitter: HlasmEmitter, code: Register) -> None:
    decimal = emitter.call(TO_STRING, (code,))
    padded = emitter.call(STRING_ZFILL, (decimal, emitter.int_(USER_ABEND_DIGITS)))
    _end(emitter, USER_ABEND_PREFIX, padded)


def _branch_on_system(
    emitter: HlasmEmitter, system: Register
) -> tuple[CodeLabel, CodeLabel]:
    is_system = emitter.binop(BinopKind.NE, system, emitter.int_(0))
    system_label = emitter.fresh_label("hl_abend_system")
    user_label = emitter.fresh_label("hl_abend_user")
    emitter.emit_inst(
        BranchIf(cond_reg=is_system, branch_targets=(system_label, user_label))
    )
    return system_label, user_label


def emit_abend_completion(emitter: HlasmEmitter) -> None:
    r1 = emitter.load_gr32(SVC_PARAMETER_REGISTER)
    system = _field(emitter, r1, COMPLETION_CODE_BITS, COMPLETION_CODE_MASK)
    user = _field(emitter, r1, 0, COMPLETION_CODE_MASK)
    system_label, user_label = _branch_on_system(emitter, system)
    emitter.emit_inst(Label_(label=system_label))
    _system(emitter, system)
    emitter.emit_inst(Label_(label=user_label))
    _user(emitter, user)
