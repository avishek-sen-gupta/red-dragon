# pyright: standard
"""Branch on count and branch on index: R1 is stepped and replaced, the branch address generated first; the CC is unchanged."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.branch_dispatch import emit_branch
from interpreter.hlasm.data_movement import (
    from_gr32,
    relative_target,
    relative_target_at,
    signed,
    storage_address,
    storage_address_at,
    wrapped,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.register_part import RegisterPart
from interpreter.hlasm.register_parts import LOW_WORD_PART, WHOLE_REGISTER_PART
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import BranchIf, Label_
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Target = Callable[[HlasmEmitter, MachineStatement], Register]

FIRST_OPERAND = 0
SECOND_OPERAND = 1
INDEX_TARGET_OPERAND = 2
NO_BRANCH_REGISTER = 0
COMPARE_VALUE_BIT = 1


def _branch_when(emitter: HlasmEmitter, condition: Register, target: Register) -> None:
    taken = emitter.fresh_label("hl_loop_taken")
    fall = emitter.fresh_label("hl_loop_fall")
    emitter.emit_inst(BranchIf(cond_reg=condition, branch_targets=(taken, fall)))
    emitter.emit_inst(Label_(label=taken))
    emit_branch(emitter, target)
    emitter.emit_inst(Label_(label=fall))


def _count(
    emitter: HlasmEmitter, statement: MachineStatement, part: RegisterPart
) -> Register:
    r1 = reg_operand(statement, FIRST_OPERAND)
    less_one = emitter.binop(BinopKind.SUB, part.load(emitter, r1), emitter.int_(1))
    result = wrapped(emitter, less_one, part.bits)
    part.store(emitter, r1, result)
    return result


def on_count(part: RegisterPart, target: Target) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        to = target(emitter, statement)
        result = _count(emitter, statement, part)
        nonzero = emitter.binop(BinopKind.NE, result, emitter.int_(0))
        _branch_when(emitter, nonzero, to)

    return lower


def _on_register_count(part: RegisterPart) -> StatementLowering:
    branching = on_count(part, from_gr32(SECOND_OPERAND))

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        if reg_operand(statement, SECOND_OPERAND) == NO_BRANCH_REGISTER:
            _count(emitter, statement, part)
            return
        branching(emitter, statement)

    return lower


INDEX_STORAGE_TARGET = storage_address_at(INDEX_TARGET_OPERAND)
INDEX_RELATIVE_TARGET = relative_target_at(INDEX_TARGET_OPERAND)


def _step_index(
    emitter: HlasmEmitter, statement: MachineStatement, part: RegisterPart
) -> tuple[Register, Register]:
    r1 = reg_operand(statement, FIRST_OPERAND)
    r3 = reg_operand(statement, SECOND_OPERAND)
    increment = part.load(emitter, r3)
    compare_value = part.load(emitter, r3 | COMPARE_VALUE_BIT)
    total = emitter.binop(BinopKind.ADD, part.load(emitter, r1), increment)
    result = wrapped(emitter, total, part.bits)
    part.store(emitter, r1, result)
    return result, compare_value


def _on_index(
    part: RegisterPart, comparison: BinopKind, target: Target
) -> StatementLowering:
    to_signed = signed(part.bits)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        to = target(emitter, statement)
        result, compare_value = _step_index(emitter, statement, part)
        compared = emitter.binop(
            comparison, to_signed(emitter, result), to_signed(emitter, compare_value)
        )
        _branch_when(emitter, compared, to)

    return lower


LOOP_BRANCH_LOWERINGS: Mapping[str, StatementLowering] = {
    "BCT": on_count(LOW_WORD_PART, storage_address),
    "BCTR": _on_register_count(LOW_WORD_PART),
    "BCTG": on_count(WHOLE_REGISTER_PART, storage_address),
    "BCTGR": _on_register_count(WHOLE_REGISTER_PART),
    "BRCT": on_count(LOW_WORD_PART, relative_target),
    "BRCTG": on_count(WHOLE_REGISTER_PART, relative_target),
    "BXH": _on_index(LOW_WORD_PART, BinopKind.GT, INDEX_STORAGE_TARGET),
    "BXHG": _on_index(WHOLE_REGISTER_PART, BinopKind.GT, INDEX_STORAGE_TARGET),
    "BXLE": _on_index(LOW_WORD_PART, BinopKind.LE, INDEX_STORAGE_TARGET),
    "BXLEG": _on_index(WHOLE_REGISTER_PART, BinopKind.LE, INDEX_STORAGE_TARGET),
    "BRXH": _on_index(LOW_WORD_PART, BinopKind.GT, INDEX_RELATIVE_TARGET),
    "BRXHG": _on_index(WHOLE_REGISTER_PART, BinopKind.GT, INDEX_RELATIVE_TARGET),
    "BRXLE": _on_index(LOW_WORD_PART, BinopKind.LE, INDEX_RELATIVE_TARGET),
    "BRXLG": _on_index(WHOLE_REGISTER_PART, BinopKind.LE, INDEX_RELATIVE_TARGET),
}
