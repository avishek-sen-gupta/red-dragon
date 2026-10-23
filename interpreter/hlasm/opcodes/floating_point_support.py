# pyright: standard
"""Floating-point-support opcodes: FPR loads, stores and moves, the sign-bit forms, the FPC with its validity checks and simulated-IEEE trap, and the vector-processing exception's VXC in the DXC byte."""

from collections.abc import Mapping, Sequence
from functools import reduce

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.conditional import emit_when
from interpreter.hlasm.data_movement import (
    REGISTER_OPERAND,
    Sink,
    Source,
    Transform,
    from_gr32,
    from_gr64,
    from_storage,
    from_storage_at,
    keep,
    move,
    storage_address_at,
    to_gr32,
    to_gr64,
    to_storage,
    to_storage_at,
)
from interpreter.hlasm.hlasm_constants import (
    DATA_EXCEPTION_ABEND,
    DOUBLEWORD_BYTES,
    FPC_VAR,
    LOW_WORD_MASK,
    REGISTER_MASK,
    SPECIFICATION_EXCEPTION_ABEND,
    VECTOR_PROCESSING_ABEND,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.specification_check import emit_specification_check
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

SIGN_BIT = 1 << 63
MAGNITUDE_BITS = REGISTER_MASK ^ SIGN_BIT
PAIR_PARTNER = 2
PAIR_OFFSETS = (0, PAIR_PARTNER)
FPC_OPERAND = 0
SIGN_OPERAND = 1
VALUE_OPERAND = 2

FPC_RESERVED_BITS = 0x03030088
SRNMB_RESERVED_BITS = 0xF8
MODE_FIELD = 0b111
SRNM_MODE_BITS = 0b11
BFP_MODE_SHIFT = 0
DFP_MODE_SHIFT = 4
INVALID_BFP_MODES = 0b0111_0000

MASK_SHIFT = 24
FLAG_SHIFT = 16
DXC_SHIFT = 8
DXC_FIELD = 0xFF << DXC_SHIFT
IEEE_BITS = 0xFC
OVERFLOW_UNDERFLOW_BITS = 0x30
INEXACT_BIT = 0x08
SIMULATED_IEEE_DXC = 0b11
GENERAL_OPERAND_DXC = 0x00
COMPARE_AND_TRAP_DXC = 0xFF
SMEAR_SHIFTS = (1, 2, 4)


def _fpr(index: int) -> Source:
    return lambda emitter, statement: emitter.load_fpr(reg_operand(statement, index))


def _fpr_short(index: int) -> Source:
    return lambda emitter, statement: emitter.load_fpr_high32(
        reg_operand(statement, index)
    )


def _to_fpr(
    emitter: HlasmEmitter, statement: MachineStatement, value: Register
) -> None:
    emitter.store_fpr(reg_operand(statement, REGISTER_OPERAND), value)


def _to_fpr_short(
    emitter: HlasmEmitter, statement: MachineStatement, value: Register
) -> None:
    emitter.store_fpr_high32(reg_operand(statement, REGISTER_OPERAND), value)


def _zero(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    return emitter.int_(0)


def _bitwise(operator: BinopKind, mask: int) -> Transform:
    return lambda emitter, value: emitter.binop(operator, value, emitter.int_(mask))


def _copied_sign(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    magnitude = keep(MAGNITUDE_BITS)(emitter, _fpr(VALUE_OPERAND)(emitter, statement))
    sign = keep(SIGN_BIT)(emitter, _fpr(SIGN_OPERAND)(emitter, statement))
    return emitter.binop(BinopKind.BIT_OR, magnitude, sign)


def pairs(operands: Sequence[int], lowering: StatementLowering) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        if any(reg_operand(statement, index) & PAIR_PARTNER for index in operands):
            emit_abend(emitter, SPECIFICATION_EXCEPTION_ABEND)
            return
        lowering(emitter, statement)

    return lower


def _lower_lxr(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    r1, r2 = reg_operand(statement, 0), reg_operand(statement, 1)
    _ = [emitter.store_fpr(r1 + at, emitter.load_fpr(r2 + at)) for at in PAIR_OFFSETS]


def _lower_lzxr(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    r1 = reg_operand(statement, 0)
    _ = [emitter.store_fpr(r1 + at, emitter.int_(0)) for at in PAIR_OFFSETS]


def _fpc(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    return emitter.load_var(FPC_VAR)


def _store_fpc(emitter: HlasmEmitter, value: Register) -> None:
    emitter.emit_inst(StoreVar(name=FPC_VAR, value_reg=value))


def _to_fpc(
    emitter: HlasmEmitter, statement: MachineStatement, value: Register
) -> None:
    _store_fpc(emitter, value)


def _invalid(emitter: HlasmEmitter, value: Register, reserved: int) -> Register:
    mode = emitter.binop(BinopKind.BIT_AND, value, emitter.int_(MODE_FIELD))
    shifted = emitter.binop(BinopKind.RSHIFT, emitter.int_(INVALID_BFP_MODES), mode)
    bad_mode = emitter.binop(BinopKind.BIT_AND, shifted, emitter.int_(1))
    set_reserved = emitter.binop(BinopKind.BIT_AND, value, emitter.int_(reserved))
    raised = emitter.binop(BinopKind.BIT_OR, set_reserved, bad_mode)
    return emitter.binop(BinopKind.NE, raised, emitter.int_(0))


def _checked(reserved: int) -> Transform:
    def check(emitter: HlasmEmitter, value: Register) -> Register:
        emit_specification_check(emitter, _invalid(emitter, value, reserved))
        return value

    return check


def _rounding_mode(source_bits: int, shift: int) -> Sink:
    def place(
        emitter: HlasmEmitter, statement: MachineStatement, address: Register
    ) -> None:
        kept = keep(LOW_WORD_MASK ^ (MODE_FIELD << shift))(
            emitter, emitter.load_var(FPC_VAR)
        )
        mode = keep(source_bits)(emitter, address)
        moved = emitter.binop(BinopKind.LSHIFT, mode, emitter.int_(shift))
        _store_fpc(emitter, emitter.binop(BinopKind.BIT_OR, kept, moved))

    return place


def _leading_bit(emitter: HlasmEmitter, value: Register) -> Register:
    smeared = reduce(
        lambda v, k: emitter.binop(
            BinopKind.BIT_OR, v, emitter.binop(BinopKind.RSHIFT, v, emitter.int_(k))
        ),
        SMEAR_SHIFTS,
        value,
    )
    below = emitter.binop(BinopKind.RSHIFT, smeared, emitter.int_(1))
    return emitter.binop(BinopKind.BIT_XOR, smeared, below)


def _simulated_dxc(
    emitter: HlasmEmitter, enabled: Register, signaling: Register
) -> Register:
    leading = _leading_bit(emitter, enabled)
    takes_inexact = emitter.binop(
        BinopKind.NE,
        keep(OVERFLOW_UNDERFLOW_BITS)(emitter, leading),
        emitter.int_(0),
    )
    inexact = emitter.binop(
        BinopKind.MUL, takes_inexact, keep(INEXACT_BIT)(emitter, signaling)
    )
    marked = emitter.binop(BinopKind.BIT_OR, leading, emitter.int_(SIMULATED_IEEE_DXC))
    return emitter.binop(BinopKind.BIT_OR, marked, inexact)


def store_dxc(emitter: HlasmEmitter, fpc: Register, dxc: Register) -> None:
    shifted = emitter.binop(BinopKind.LSHIFT, dxc, emitter.int_(DXC_SHIFT))
    cleared = keep(LOW_WORD_MASK ^ DXC_FIELD)(emitter, fpc)
    _store_fpc(emitter, emitter.binop(BinopKind.BIT_OR, cleared, shifted))


def emit_data_exception(emitter: HlasmEmitter, fpc: Register, dxc: Register) -> None:
    store_dxc(emitter, fpc, dxc)
    emit_abend(emitter, DATA_EXCEPTION_ABEND)


def emit_vector_exception(emitter: HlasmEmitter, vxc: Register) -> None:
    store_dxc(emitter, emitter.load_var(FPC_VAR), vxc)
    emit_abend(emitter, VECTOR_PROCESSING_ABEND)


def emit_coded_data_exception(emitter: HlasmEmitter, dxc: int) -> None:
    emit_data_exception(emitter, emitter.load_var(FPC_VAR), emitter.int_(dxc))


def _trap(
    emitter: HlasmEmitter, loaded: Register, enabled: Register, signaling: Register
) -> None:
    emit_data_exception(emitter, loaded, _simulated_dxc(emitter, enabled, signaling))


def _byte(emitter: HlasmEmitter, value: Register, shift: int) -> Register:
    moved = emitter.binop(BinopKind.RSHIFT, value, emitter.int_(shift))
    return keep(IEEE_BITS)(emitter, moved)


def _signal(
    emitter: HlasmEmitter, statement: MachineStatement, source: Register
) -> None:
    signaling = _byte(emitter, emitter.load_var(FPC_VAR), FLAG_SHIFT)
    emit_specification_check(emitter, _invalid(emitter, source, FPC_RESERVED_BITS))
    flags = emitter.binop(BinopKind.LSHIFT, signaling, emitter.int_(FLAG_SHIFT))
    loaded = emitter.binop(BinopKind.BIT_OR, source, flags)
    _store_fpc(emitter, loaded)
    enabled = emitter.binop(
        BinopKind.BIT_AND, signaling, _byte(emitter, source, MASK_SHIFT)
    )
    emit_when(
        emitter,
        emitter.binop(BinopKind.NE, enabled, emitter.int_(0)),
        lambda: _trap(emitter, loaded, enabled, signaling),
    )


FPC_WORD = from_storage_at(FPC_OPERAND, WORD_BYTES)
ROUNDING_ADDRESS = storage_address_at(FPC_OPERAND)

REGISTER_MOVES: Mapping[str, StatementLowering] = {
    "LER": move(_fpr_short(1), (), _to_fpr_short),
    "LDR": move(_fpr(1), (), _to_fpr),
    "LXR": pairs((0, 1), _lower_lxr),
    "LDGR": move(from_gr64(1), (), _to_fpr),
    "LGDR": move(_fpr(1), (), to_gr64),
    "LZER": move(_zero, (), _to_fpr_short),
    "LZDR": move(_zero, (), _to_fpr),
    "LZXR": pairs((0,), _lower_lzxr),
}

LOADS_AND_STORES: Mapping[str, StatementLowering] = {
    "LE": move(from_storage(WORD_BYTES), (), _to_fpr_short),
    "LEY": move(from_storage(WORD_BYTES), (), _to_fpr_short),
    "LD": move(from_storage(DOUBLEWORD_BYTES), (), _to_fpr),
    "LDY": move(from_storage(DOUBLEWORD_BYTES), (), _to_fpr),
    "STE": move(_fpr_short(0), (), to_storage(WORD_BYTES)),
    "STEY": move(_fpr_short(0), (), to_storage(WORD_BYTES)),
    "STD": move(_fpr(0), (), to_storage(DOUBLEWORD_BYTES)),
    "STDY": move(_fpr(0), (), to_storage(DOUBLEWORD_BYTES)),
}

SIGN_FORMS: Mapping[str, StatementLowering] = {
    "LCDFR": move(_fpr(1), (_bitwise(BinopKind.BIT_XOR, SIGN_BIT),), _to_fpr),
    "LNDFR": move(_fpr(1), (_bitwise(BinopKind.BIT_OR, SIGN_BIT),), _to_fpr),
    "LPDFR": move(_fpr(1), (keep(MAGNITUDE_BITS),), _to_fpr),
    "CPSDR": move(_copied_sign, (), _to_fpr),
}

FPC_FORMS: Mapping[str, StatementLowering] = {
    "EFPC": move(_fpc, (), to_gr32),
    "STFPC": move(_fpc, (), to_storage_at(FPC_OPERAND, WORD_BYTES)),
    "SFPC": move(from_gr32(0), (_checked(FPC_RESERVED_BITS),), _to_fpc),
    "LFPC": move(FPC_WORD, (_checked(FPC_RESERVED_BITS),), _to_fpc),
    "SFASR": move(from_gr32(0), (), _signal),
    "LFAS": move(FPC_WORD, (), _signal),
    "SRNM": move(ROUNDING_ADDRESS, (), _rounding_mode(SRNM_MODE_BITS, BFP_MODE_SHIFT)),
    "SRNMB": move(
        ROUNDING_ADDRESS,
        (_checked(SRNMB_RESERVED_BITS),),
        _rounding_mode(MODE_FIELD, BFP_MODE_SHIFT),
    ),
    "SRNMT": move(ROUNDING_ADDRESS, (), _rounding_mode(MODE_FIELD, DFP_MODE_SHIFT)),
}

FLOATING_POINT_SUPPORT_LOWERINGS: Mapping[str, StatementLowering] = {
    **REGISTER_MOVES,
    **LOADS_AND_STORES,
    **SIGN_FORMS,
    **FPC_FORMS,
}
