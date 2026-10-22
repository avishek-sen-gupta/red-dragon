# pyright: standard
"""Compare and branch, compare and trap, load and trap: M3 picks the comparison results that branch or raise the compare-and-trap data exception (S0C7); the CC is unchanged."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.branch_dispatch import emit_branch
from interpreter.hlasm.conditional import emit_when
from interpreter.hlasm.data_movement import (
    Sink,
    Source,
    from_gr32,
    from_gr64,
    from_storage,
    from_storage_at,
    immediate,
    keep,
    move,
    relative_target_at,
    signed_immediate,
    storage_address_at,
    to_gr32,
    to_gr64,
)
from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    BITS_PER_BYTE,
    DATA_EXCEPTION_ABEND,
    DOUBLEWORD_BYTES,
    PARAM_LEFT,
    PARAM_RIGHT,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_ir
from interpreter.hlasm.opcodes.branch_on_condition import mask_selects
from interpreter.hlasm.opcodes.compare import (
    LOGICAL_32,
    LOGICAL_64,
    SIGNED_32,
    SIGNED_64,
    Comparison,
)
from interpreter.hlasm.opcodes.operand_sources import (
    HALFWORD_IMMEDIATE,
    LOGICAL_HALFWORD_IMMEDIATE,
)
from interpreter.hlasm.operands import mask_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Outcome = Callable[[HlasmEmitter, MachineStatement], None]

RESULT_BITS = 0b1110
NEVER = 0
ALWAYS = RESULT_BITS
MASK_OPERAND = 2
STORAGE_MASK_OPERAND = 1
TARGET_OPERAND = 3
STORAGE_OPERAND = 2

BYTE_IMMEDIATE = signed_immediate(1, BITS_PER_BYTE)
LOGICAL_BYTE_IMMEDIATE = immediate(BITS_PER_BYTE)


def _branch_to(target: Source) -> Outcome:
    return lambda emitter, statement: emit_branch(emitter, target(emitter, statement))


def _trap(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    emit_abend(emitter, DATA_EXCEPTION_ABEND)


BRANCH = _branch_to(storage_address_at(TARGET_OPERAND))
BRANCH_RELATIVE = _branch_to(relative_target_at(TARGET_OPERAND))


def _compared(comparison: Comparison, operands: tuple[Source, Source]) -> Source:
    left, right = operands

    def cc(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
        arguments = {
            PARAM_LEFT: left(emitter, statement),
            PARAM_RIGHT: right(emitter, statement),
        }
        return inline_ir(emitter, comparison, arguments)

    return cc


def _on_comparison(
    comparison: Comparison,
    operands: tuple[Source, Source],
    outcome: Outcome,
    mask_at: int = MASK_OPERAND,
) -> StatementLowering:
    cc_of = _compared(comparison, operands)

    def conditional(
        emitter: HlasmEmitter, statement: MachineStatement, mask: int
    ) -> None:
        selected = mask_selects(emitter, cc_of(emitter, statement), mask)
        emit_when(emitter, selected, lambda: outcome(emitter, statement))

    untested: Mapping[int, Callable[[HlasmEmitter, MachineStatement, int], None]] = {
        NEVER: lambda emitter, statement, mask: None,
        ALWAYS: lambda emitter, statement, mask: outcome(emitter, statement),
    }

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        mask = mask_operand(statement, mask_at) & RESULT_BITS
        untested.get(mask, conditional)(emitter, statement, mask)

    return lower


def trapping_on_zero(sink: Sink) -> Sink:
    def store_then_test(
        emitter: HlasmEmitter, statement: MachineStatement, value: Register
    ) -> None:
        sink(emitter, statement, value)
        zero = emitter.binop(BinopKind.EQ, value, emitter.int_(0))
        emit_when(emitter, zero, lambda: _trap(emitter, statement))

    return store_then_test


REGISTERS_32 = (from_gr32(0), from_gr32(1))
REGISTERS_64 = (from_gr64(0), from_gr64(1))
STORAGE_WORD = (from_gr32(0), from_storage_at(STORAGE_OPERAND, WORD_BYTES))
STORAGE_DOUBLEWORD = (from_gr64(0), from_storage_at(STORAGE_OPERAND, DOUBLEWORD_BYTES))

COMPARE_AND_BRANCH: Mapping[str, StatementLowering] = {
    "CRB": _on_comparison(SIGNED_32, REGISTERS_32, BRANCH),
    "CGRB": _on_comparison(SIGNED_64, REGISTERS_64, BRANCH),
    "CLRB": _on_comparison(LOGICAL_32, REGISTERS_32, BRANCH),
    "CLGRB": _on_comparison(LOGICAL_64, REGISTERS_64, BRANCH),
    "CIB": _on_comparison(SIGNED_32, (from_gr32(0), BYTE_IMMEDIATE), BRANCH),
    "CGIB": _on_comparison(SIGNED_64, (from_gr64(0), BYTE_IMMEDIATE), BRANCH),
    "CLIB": _on_comparison(LOGICAL_32, (from_gr32(0), LOGICAL_BYTE_IMMEDIATE), BRANCH),
    "CLGIB": _on_comparison(LOGICAL_64, (from_gr64(0), LOGICAL_BYTE_IMMEDIATE), BRANCH),
    "CRJ": _on_comparison(SIGNED_32, REGISTERS_32, BRANCH_RELATIVE),
    "CGRJ": _on_comparison(SIGNED_64, REGISTERS_64, BRANCH_RELATIVE),
    "CLRJ": _on_comparison(LOGICAL_32, REGISTERS_32, BRANCH_RELATIVE),
    "CLGRJ": _on_comparison(LOGICAL_64, REGISTERS_64, BRANCH_RELATIVE),
    "CIJ": _on_comparison(SIGNED_32, (from_gr32(0), BYTE_IMMEDIATE), BRANCH_RELATIVE),
    "CGIJ": _on_comparison(SIGNED_64, (from_gr64(0), BYTE_IMMEDIATE), BRANCH_RELATIVE),
    "CLIJ": _on_comparison(
        LOGICAL_32, (from_gr32(0), LOGICAL_BYTE_IMMEDIATE), BRANCH_RELATIVE
    ),
    "CLGIJ": _on_comparison(
        LOGICAL_64, (from_gr64(0), LOGICAL_BYTE_IMMEDIATE), BRANCH_RELATIVE
    ),
}

COMPARE_AND_TRAP: Mapping[str, StatementLowering] = {
    "CRT": _on_comparison(SIGNED_32, REGISTERS_32, _trap),
    "CGRT": _on_comparison(SIGNED_64, REGISTERS_64, _trap),
    "CLRT": _on_comparison(LOGICAL_32, REGISTERS_32, _trap),
    "CLGRT": _on_comparison(LOGICAL_64, REGISTERS_64, _trap),
    "CIT": _on_comparison(SIGNED_32, (from_gr32(0), HALFWORD_IMMEDIATE), _trap),
    "CGIT": _on_comparison(SIGNED_64, (from_gr64(0), HALFWORD_IMMEDIATE), _trap),
    "CLFIT": _on_comparison(
        LOGICAL_32, (from_gr32(0), LOGICAL_HALFWORD_IMMEDIATE), _trap
    ),
    "CLGIT": _on_comparison(
        LOGICAL_64, (from_gr64(0), LOGICAL_HALFWORD_IMMEDIATE), _trap
    ),
    "CLT": _on_comparison(LOGICAL_32, STORAGE_WORD, _trap, STORAGE_MASK_OPERAND),
    "CLGT": _on_comparison(LOGICAL_64, STORAGE_DOUBLEWORD, _trap, STORAGE_MASK_OPERAND),
}

LOAD_AND_TRAP: Mapping[str, StatementLowering] = {
    "LAT": move(from_storage(WORD_BYTES), (), trapping_on_zero(to_gr32)),
    "LGAT": move(from_storage(DOUBLEWORD_BYTES), (), trapping_on_zero(to_gr64)),
    "LLGFAT": move(from_storage(WORD_BYTES), (), trapping_on_zero(to_gr64)),
    "LLGTAT": move(
        from_storage(WORD_BYTES),
        (keep(ADDRESS_MASK_31),),
        trapping_on_zero(to_gr64),
    ),
}

COMPARE_BRANCH_TRAP_LOWERINGS: Mapping[str, StatementLowering] = {
    **COMPARE_AND_BRANCH,
    **COMPARE_AND_TRAP,
    **LOAD_AND_TRAP,
}
