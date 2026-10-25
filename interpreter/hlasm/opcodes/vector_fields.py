# pyright: standard
"""Vector operand helpers at lowering: M-field checks (an element size outside the instruction's allowed set, a must-be-zero bit that is set, or a static element index past the element count abends S0C6; an omitted M field is 0), whole-register sources and sinks, element replication, the borrow compare, the CC from a count of elements, and the call of an element function that returns a result and a CC set only with CS."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.data_movement import Source, Transform
from interpreter.hlasm.element_return_field import CC_FIELD, RESULT_BITS, RESULT_FIELD
from interpreter.hlasm.element_size import ElementSize
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    SPECIFICATION_EXCEPTION_ABEND,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import IrFunction
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
SECOND = 1
THIRD = 2
CS_FIELD = 4
CONDITION_CODE_SET = 0b0001

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


def ones(bits: int) -> int:
    return (1 << bits) - 1


def element_bits(size: ElementSize) -> int:
    return BITS_PER_BYTE * size.width


def below(emitter: HlasmEmitter, left: Register, right: Register) -> Register:
    difference = emitter.binop(BinopKind.SUB, left, right)
    borrow = emitter.binop(BinopKind.RSHIFT, difference, emitter.int_(RESULT_BITS))
    return emitter.binop(BinopKind.BIT_AND, borrow, emitter.int_(1))


def count_cc(emitter: HlasmEmitter, counted: Register, elements: int) -> Register:
    some = below(emitter, emitter.int_(0), counted)
    short = below(emitter, counted, emitter.int_(elements))
    every = emitter.binop(BinopKind.SUB, emitter.int_(1), short)
    doubled = emitter.binop(BinopKind.MUL, every, emitter.int_(2))
    return emitter.binop(BinopKind.ADD, some, doubled)


def _status_call(
    function: IrFunction, emitter: HlasmEmitter, statement: MachineStatement
) -> None:
    sources = (vr_at(SECOND)(emitter, statement), vr_at(THIRD)(emitter, statement))
    returned = function.call(emitter, sources)
    to_v1(emitter, statement, RESULT_FIELD.of(emitter, returned))
    if m_field(statement, CS_FIELD) & CONDITION_CODE_SET:
        emitter.set_cc(CC_FIELD.of(emitter, returned))


def status_function(
    functions: Mapping[ElementSize, IrFunction],
) -> Callable[[ElementSize], StatementLowering]:
    return lambda size: lambda emitter, statement: _status_call(
        functions[size], emitter, statement
    )
