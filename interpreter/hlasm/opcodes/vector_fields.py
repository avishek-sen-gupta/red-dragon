# pyright: standard
"""Vector operand helpers at lowering: M-field checks (an element size outside the instruction's allowed set, a must-be-zero bit that is set, or a static element index past the element count abends S0C6; an omitted M field is 0), whole-register sources and sinks, and element replication."""

from collections.abc import Callable

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.data_movement import Source, Transform
from interpreter.hlasm.element_size import ElementSize
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    SPECIFICATION_EXCEPTION_ABEND,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.fp_forms import checked
from interpreter.hlasm.operands import (
    optional_mask_operand,
    value_operand,
    vec_reg_operand,
)
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

OMITTED_M_FIELD = 0
V1 = 0

type SizedLowering = Callable[[HlasmEmitter, MachineStatement, ElementSize], None]


def m_field(statement: MachineStatement, index: int) -> int:
    return optional_mask_operand(statement, index, OMITTED_M_FIELD)


def element_size_checked(
    field: int, allowed: frozenset[ElementSize], lowering: SizedLowering
) -> StatementLowering:
    sizes = {size.value: size for size in allowed}

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        code = m_field(statement, field)
        if code not in sizes:
            emit_abend(emitter, SPECIFICATION_EXCEPTION_ABEND)
            return
        lowering(emitter, statement, sizes[code])

    return lower


def zero_bits_checked(
    field: int, bits: int, lowering: StatementLowering
) -> StatementLowering:
    return checked(lambda statement: m_field(statement, field) & bits != 0, lowering)


def element_index_checked(
    field: int, size: ElementSize, lowering: StatementLowering
) -> StatementLowering:
    return checked(
        lambda statement: not 0 <= value_operand(statement, field).value < size.count,
        lowering,
    )


def per_size(
    field: int,
    allowed: frozenset[ElementSize],
    build: Callable[[ElementSize], StatementLowering],
) -> StatementLowering:
    return element_size_checked(
        field,
        allowed,
        lambda emitter, statement, size: build(size)(emitter, statement),
    )


def vr_at(index: int) -> Source:
    return lambda emitter, statement: emitter.load_vr(vec_reg_operand(statement, index))


def to_v1(emitter: HlasmEmitter, statement: MachineStatement, value: Register) -> None:
    emitter.store_vr(vec_reg_operand(statement, V1), value)


def replication(size: ElementSize) -> int:
    return sum(1 << (BITS_PER_BYTE * size.width * i) for i in range(size.count))


def replicated(size: ElementSize) -> Transform:
    pattern = replication(size)
    return lambda emitter, value: emitter.binop(
        BinopKind.MUL, value, emitter.int_(pattern)
    )
