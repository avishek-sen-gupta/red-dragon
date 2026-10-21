# pyright: standard
"""Branch on count and branch on index: R1 is stepped and replaced, the branch address generated first; the CC is unchanged."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.branch_dispatch import emit_branch
from interpreter.hlasm.data_movement import relative_target, signed, storage_address
from interpreter.hlasm.effective_address import effective_address, relative_address
from interpreter.hlasm.hlasm_constants import DOUBLEWORD_BITS, WORD_BITS
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import reg_operand, reloc_operand, storage_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import BranchIf, Label_
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Target = Callable[[HlasmEmitter, MachineStatement], Register]
type Load = Callable[[HlasmEmitter, int], Register]
type Store = Callable[[HlasmEmitter, int, Register], None]

FIRST_OPERAND = 0
SECOND_OPERAND = 1
INDEX_TARGET_OPERAND = 2
NO_BRANCH_REGISTER = 0
COMPARE_VALUE_BIT = 1


LOADS: Mapping[int, Load] = {
    WORD_BITS: HlasmEmitter.load_gr32,
    DOUBLEWORD_BITS: HlasmEmitter.load_gr64,
}
STORES: Mapping[int, Store] = {
    WORD_BITS: HlasmEmitter.store_gr32,
    DOUBLEWORD_BITS: HlasmEmitter.store_gr64,
}


def _branch_when(emitter: HlasmEmitter, condition: Register, target: Register) -> None:
    taken = emitter.fresh_label("hl_loop_taken")
    fall = emitter.fresh_label("hl_loop_fall")
    emitter.emit_inst(BranchIf(cond_reg=condition, branch_targets=(taken, fall)))
    emitter.emit_inst(Label_(label=taken))
    emit_branch(emitter, target)
    emitter.emit_inst(Label_(label=fall))


def _wrapped(emitter: HlasmEmitter, value: Register, bits: int) -> Register:
    return emitter.binop(BinopKind.MOD, value, emitter.int_(1 << bits))


def _count(emitter: HlasmEmitter, statement: MachineStatement, bits: int) -> Register:
    r1 = reg_operand(statement, FIRST_OPERAND)
    less_one = emitter.binop(BinopKind.SUB, LOADS[bits](emitter, r1), emitter.int_(1))
    result = _wrapped(emitter, less_one, bits)
    STORES[bits](emitter, r1, result)
    return result


def _on_count(bits: int, target: Target) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        to = target(emitter, statement)
        result = _count(emitter, statement, bits)
        nonzero = emitter.binop(BinopKind.NE, result, emitter.int_(0))
        _branch_when(emitter, nonzero, to)

    return lower


def _on_register_count(bits: int) -> StatementLowering:
    branching = _on_count(
        bits,
        lambda emitter, statement: emitter.load_gr32(
            reg_operand(statement, SECOND_OPERAND)
        ),
    )

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        if reg_operand(statement, SECOND_OPERAND) == NO_BRANCH_REGISTER:
            _count(emitter, statement, bits)
            return
        branching(emitter, statement)

    return lower


def _index_storage_target(
    emitter: HlasmEmitter, statement: MachineStatement
) -> Register:
    return effective_address(emitter, storage_operand(statement, INDEX_TARGET_OPERAND))


def _index_relative_target(
    emitter: HlasmEmitter, statement: MachineStatement
) -> Register:
    return relative_address(emitter, reloc_operand(statement, INDEX_TARGET_OPERAND))


def _step_index(
    emitter: HlasmEmitter, statement: MachineStatement, bits: int
) -> tuple[Register, Register]:
    r1 = reg_operand(statement, FIRST_OPERAND)
    r3 = reg_operand(statement, SECOND_OPERAND)
    increment = LOADS[bits](emitter, r3)
    compare_value = LOADS[bits](emitter, r3 | COMPARE_VALUE_BIT)
    total = emitter.binop(BinopKind.ADD, LOADS[bits](emitter, r1), increment)
    result = _wrapped(emitter, total, bits)
    STORES[bits](emitter, r1, result)
    return result, compare_value


def _on_index(bits: int, comparison: BinopKind, target: Target) -> StatementLowering:
    to_signed = signed(bits)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        to = target(emitter, statement)
        result, compare_value = _step_index(emitter, statement, bits)
        compared = emitter.binop(
            comparison, to_signed(emitter, result), to_signed(emitter, compare_value)
        )
        _branch_when(emitter, compared, to)

    return lower


LOOP_BRANCH_LOWERINGS: Mapping[str, StatementLowering] = {
    "BCT": _on_count(WORD_BITS, storage_address),
    "BCTR": _on_register_count(WORD_BITS),
    "BCTG": _on_count(DOUBLEWORD_BITS, storage_address),
    "BCTGR": _on_register_count(DOUBLEWORD_BITS),
    "BRCT": _on_count(WORD_BITS, relative_target),
    "BRCTG": _on_count(DOUBLEWORD_BITS, relative_target),
    "BXH": _on_index(WORD_BITS, BinopKind.GT, _index_storage_target),
    "BXHG": _on_index(DOUBLEWORD_BITS, BinopKind.GT, _index_storage_target),
    "BXLE": _on_index(WORD_BITS, BinopKind.LE, _index_storage_target),
    "BXLEG": _on_index(DOUBLEWORD_BITS, BinopKind.LE, _index_storage_target),
    "BRXH": _on_index(WORD_BITS, BinopKind.GT, _index_relative_target),
    "BRXHG": _on_index(DOUBLEWORD_BITS, BinopKind.GT, _index_relative_target),
    "BRXLE": _on_index(WORD_BITS, BinopKind.LE, _index_relative_target),
    "BRXLG": _on_index(DOUBLEWORD_BITS, BinopKind.LE, _index_relative_target),
}
