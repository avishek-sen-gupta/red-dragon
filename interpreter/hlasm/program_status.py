# pyright: standard
"""SPM, IPM and EPSW: the CC and program mask set from or inserted into a register, and the fixed problem-state PSW image (ruling R37)."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.hlasm_constants import CC_VAR, PROGRAM_MASK_VAR
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import reg_operand
from interpreter.instructions import StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

CC_FIELD_SHIFT = 28
MASK_FIELD_SHIFT = 24
CC_BITS = 0b11
MASK_BITS = 0b1111
STATUS_CC_SHIFT = 4
BELOW_STATUS_BYTE = 0x00FFFFFF
PSW_STATUS_SHIFT = 8
PROBLEM_STATE_PSW_HIGH = 0x07850000
AMODE_31_PSW_LOW = 0x80000000
NO_REGISTER = 0


def _field(emitter: HlasmEmitter, word: Register, shift: int, bits: int) -> Register:
    moved = emitter.binop(BinopKind.RSHIFT, word, emitter.int_(shift))
    return emitter.binop(BinopKind.BIT_AND, moved, emitter.int_(bits))


def _status(emitter: HlasmEmitter) -> Register:
    cc = emitter.binop(
        BinopKind.LSHIFT, emitter.load_var(CC_VAR), emitter.int_(STATUS_CC_SHIFT)
    )
    return emitter.binop(BinopKind.BIT_OR, cc, emitter.load_var(PROGRAM_MASK_VAR))


def lower_spm(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    word = emitter.load_gr32(reg_operand(statement, 0))
    emitter.set_cc(_field(emitter, word, CC_FIELD_SHIFT, CC_BITS))
    mask = _field(emitter, word, MASK_FIELD_SHIFT, MASK_BITS)
    emitter.emit_inst(StoreVar(name=PROGRAM_MASK_VAR, value_reg=mask))


def lower_ipm(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    r1 = reg_operand(statement, 0)
    kept = emitter.binop(
        BinopKind.BIT_AND, emitter.load_gr32(r1), emitter.int_(BELOW_STATUS_BYTE)
    )
    status = emitter.binop(
        BinopKind.LSHIFT, _status(emitter), emitter.int_(MASK_FIELD_SHIFT)
    )
    emitter.store_gr32(r1, emitter.binop(BinopKind.BIT_OR, kept, status))


def lower_epsw(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    status = emitter.binop(
        BinopKind.LSHIFT, _status(emitter), emitter.int_(PSW_STATUS_SHIFT)
    )
    image = emitter.binop(
        BinopKind.BIT_OR, emitter.int_(PROBLEM_STATE_PSW_HIGH), status
    )
    emitter.store_gr32(reg_operand(statement, 0), image)
    r2 = reg_operand(statement, 1)
    if r2 == NO_REGISTER:
        return
    emitter.store_gr32(r2, emitter.int_(AMODE_31_PSW_LOW))
