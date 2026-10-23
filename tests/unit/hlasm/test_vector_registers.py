# pyright: standard
"""Vector registers through the VM: whole 128-bit values over the FPRs, elements by static and run-time index, the element-function return fields, the M-field and element-index checks, the VRV operand's address and the VXC delivery."""

from collections.abc import Sequence

import pytest

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.effective_address import vector_indexed_address
from interpreter.hlasm.element_return_field import (
    CC_FIELD,
    FLAGS_FIELD,
    RESULT_FIELD,
    TRAP_FIELD,
    VXC_FIELD,
)
from interpreter.hlasm.element_size import ElementSize
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.hlasm_lowering_error import HlasmLoweringError
from interpreter.hlasm.machine import floating_point_allocation, machine_allocation
from interpreter.hlasm.opcodes.floating_point_support import emit_vector_exception
from interpreter.hlasm.opcodes.vector_fields import (
    element_index_checked,
    element_size_checked,
    zero_bits_checked,
)
from interpreter.hlasm.operands import vector_indexed_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.vector_elements import (
    load_element,
    load_element_at,
    store_element,
    store_element_at,
)
from interpreter.hlasm.vector_indexed_operand import VectorIndexedOperand
from interpreter.instructions import InstructionBase
from interpreter.register import Register
from interpreter.var_name import VarName
from interpreter.vm.vm_types import SymbolicValue, VMState
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import (
    imm_operand,
    machine_statement,
    mask_operand,
    reg_operand,
)
from tests.unit.hlasm.straight_line_vm import register_value, run_straight_line

ONES = (1 << 128) - 1
MARK_REGISTER = 1
VRV_STATEMENT = machine_statement(
    "VGEF",
    (
        reg_operand(17),
        StorageOperand(
            kind="STORAGE",
            displacement=8,
            index=19,
            base=5,
            written=AbsAddress(kind="ABS", value=8),
        ),
        mask_operand(1),
    ),
)


def _run(instructions: Sequence[InstructionBase]) -> VMState:
    return run_straight_line(
        (*machine_allocation(), *floating_point_allocation(), *instructions), {}
    )


def _vrs(vm: VMState, start: int, length: int) -> list[int] | SymbolicValue:
    base = vm.current_frame.local_vars[VarName("__hlasm_vrs")].value
    return vm.load(base + start, length)


def _values(vm: VMState, registers: Sequence[Register]) -> list[int]:
    return [register_value(vm, reg).value for reg in registers]


def _var(vm: VMState, name: str) -> int | str:
    return vm.current_frame.local_vars[VarName(name)].value


def _marked(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    emitter.store_gr64(MARK_REGISTER, emitter.int_(0xAA))


def _sized(
    emitter: HlasmEmitter, statement: MachineStatement, size: ElementSize
) -> None:
    emitter.store_gr64(MARK_REGISTER, emitter.int_(size.width))


def _outcome(
    lowering: StatementLowering, operands: Sequence[Operand]
) -> tuple[int, int | str]:
    emitter = HlasmEmitter()
    emitter.store_var(VarName("__hlasm_abend"), emitter.str_(""))
    lowering(emitter, machine_statement("V", operands))
    marked = emitter.load_gr64(MARK_REGISTER)
    vm = _run(emitter.instructions())
    return register_value(vm, marked).value, _var(vm, "__hlasm_abend")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_vector_register_is_one_128_bit_value_whose_left_half_is_the_fpr():
    emitter = HlasmEmitter()
    emitter.store_vr(3, emitter.int_(0x0011_2233_4455_6677_8899_AABB_CCDD_EEFF))
    emitter.store_fpr(3, emitter.int_(0xFEDC_BA98_7654_3210))
    emitter.store_vr(31, emitter.int_((1 << 128) | 0x0102))
    loads = (emitter.load_vr(3), emitter.load_fpr(3), emitter.load_vr(31))
    vm = _run(emitter.instructions())

    assert _values(vm, loads) == [
        0xFEDC_BA98_7654_3210_8899_AABB_CCDD_EEFF,
        0xFEDC_BA98_7654_3210,
        0x0102,
    ]
    assert [_vrs(vm, 48, 16), _vrs(vm, 64, 432), _vrs(vm, 496, 16)] == [
        list((0xFEDC_BA98_7654_3210_8899_AABB_CCDD_EEFF).to_bytes(16, "big")),
        [0] * 432,
        [0] * 14 + [0x01, 0x02],
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_static_element_index_addresses_its_bytes_in_the_register():
    emitter = HlasmEmitter()
    store_element(emitter, 2, ElementSize.BYTE, 15, emitter.int_(0x1AB))
    store_element(emitter, 2, ElementSize.HALFWORD, 1, emitter.int_(0x1234))
    store_element(emitter, 2, ElementSize.WORD, 2, emitter.int_(0x89AB_CDEF))
    store_element(emitter, 4, ElementSize.DOUBLEWORD, 1, emitter.int_(7))
    store_element(emitter, 5, ElementSize.QUADWORD, 0, emitter.int_(ONES))
    loads = (
        load_element(emitter, 2, ElementSize.BYTE, 15),
        load_element(emitter, 2, ElementSize.HALFWORD, 1),
        load_element(emitter, 2, ElementSize.WORD, 2),
        load_element(emitter, 4, ElementSize.DOUBLEWORD, 1),
        load_element(emitter, 5, ElementSize.QUADWORD, 0),
    )
    vm = _run(emitter.instructions())

    assert _values(vm, loads) == [0xAB, 0x1234, 0x89AB_CDEF, 7, ONES]
    assert [_vrs(vm, 32, 16), _vrs(vm, 64, 16), _vrs(vm, 80, 16)] == [
        [0, 0, 0x12, 0x34, 0, 0, 0, 0, 0x89, 0xAB, 0xCD, 0xEF, 0, 0, 0, 0xAB],
        [0] * 15 + [7],
        [0xFF] * 16,
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_run_time_element_index_is_taken_modulo_the_element_count():
    emitter = HlasmEmitter()
    store_element_at(
        emitter, 6, ElementSize.WORD, emitter.int_(4097), emitter.int_(0x5566_7788)
    )
    store_element_at(emitter, 6, ElementSize.BYTE, emitter.int_(31), emitter.int_(0x99))
    loads = (
        load_element_at(emitter, 6, ElementSize.WORD, emitter.int_(1)),
        load_element_at(emitter, 6, ElementSize.HALFWORD, emitter.int_(4091)),
        load_element_at(emitter, 6, ElementSize.DOUBLEWORD, emitter.int_(3)),
    )
    vm = _run(emitter.instructions())

    assert _values(vm, loads) == [0x5566_7788, 0x7788, 0x99]
    assert [_vrs(vm, 96, 16), _vrs(vm, 80, 16), _vrs(vm, 112, 16)] == [
        [0, 0, 0, 0, 0x55, 0x66, 0x77, 0x88, 0, 0, 0, 0, 0, 0, 0, 0x99],
        [0] * 16,
        [0] * 16,
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_element_function_returns_its_result_and_status_in_one_value():
    emitter = HlasmEmitter()
    returned = emitter.int_(
        (1 << 152) | (0x31 << 144) | (0xF8 << 136) | (2 << 128) | ONES
    )
    fields = (RESULT_FIELD, CC_FIELD, FLAGS_FIELD, VXC_FIELD, TRAP_FIELD)
    split = tuple(field.of(emitter, returned) for field in fields)
    placed = tuple(
        field.placed(emitter, emitter.int_(value))
        for field, value in zip(fields, (ONES + 2, 7, 0x1F8, 0x123, 3), strict=True)
    )
    vm = _run(emitter.instructions())

    assert _values(vm, split) == [ONES, 2, 0xF8, 0x31, 1]
    assert _values(vm, placed) == [
        1,
        3 << 128,
        0xF8 << 136,
        0x23 << 144,
        1 << 152,
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_m_field_checks_abend_s0c6_at_lowering_and_an_omitted_m_field_is_zero():
    words = frozenset({ElementSize.WORD, ElementSize.DOUBLEWORD})
    every = frozenset(ElementSize)
    vector = reg_operand(1)

    assert [
        _outcome(element_size_checked(1, words, _sized), (vector, mask_operand(3))),
        _outcome(element_size_checked(1, words, _sized), (vector, mask_operand(1))),
        _outcome(element_size_checked(1, words, _sized), (vector, mask_operand(5))),
        _outcome(element_size_checked(1, every, _sized), (vector,)),
        _outcome(element_size_checked(1, every, _sized), (vector, mask_operand(4))),
        _outcome(zero_bits_checked(1, 0b0111, _marked), (vector, mask_operand(8))),
        _outcome(zero_bits_checked(1, 0b0111, _marked), (vector, mask_operand(9))),
        _outcome(zero_bits_checked(1, 0b0111, _marked), (vector,)),
    ] == [
        (8, ""),
        (0, "S0C6"),
        (0, "S0C6"),
        (1, ""),
        (16, ""),
        (0xAA, ""),
        (0, "S0C6"),
        (0xAA, ""),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_static_element_index_past_the_element_count_abends_s0c6_at_lowering():
    vector = reg_operand(1)

    assert [
        _outcome(
            element_index_checked(1, ElementSize.WORD, _marked),
            (vector, mask_operand(3)),
        ),
        _outcome(
            element_index_checked(1, ElementSize.WORD, _marked),
            (vector, mask_operand(4)),
        ),
        _outcome(
            element_index_checked(1, ElementSize.BYTE, _marked),
            (vector, imm_operand(15)),
        ),
        _outcome(
            element_index_checked(1, ElementSize.BYTE, _marked),
            (vector, imm_operand(16)),
        ),
        _outcome(
            element_index_checked(1, ElementSize.QUADWORD, _marked),
            (vector, mask_operand(1)),
        ),
    ] == [(0xAA, ""), (0, "S0C6"), (0xAA, ""), (0, "S0C6"), (0, "S0C6")]


def _mismatch(statement: MachineStatement, index: int) -> str:
    with pytest.raises(HlasmLoweringError) as raised:
        vector_indexed_operand(statement, index)
    return str(raised.value)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_vrv_operand_indexes_by_a_vector_element_and_never_by_a_gpr():
    operand = vector_indexed_operand(VRV_STATEMENT, 1)
    emitter = HlasmEmitter()
    emitter.store_gr64(5, emitter.int_(0xFFFF_FFFF_8000_1000))
    emitter.store_gr64(19, emitter.int_(0x7777))
    emitter.store_vr(19, emitter.int_((0x20 << 64) | 0x300))
    addresses = (
        vector_indexed_address(emitter, operand, ElementSize.WORD, 1),
        vector_indexed_address(emitter, operand, ElementSize.DOUBLEWORD, 1),
    )
    vm = _run(emitter.instructions())

    assert (operand, _values(vm, addresses), _mismatch(VRV_STATEMENT, 0)) == (
        VectorIndexedOperand(displacement=8, vector_index=19, base=5),
        [0x1028, 0x1308],
        "VGEF in T at offset 2 (t.asm:1) operand 0: expected a vector-indexed storage"
        " operand, found RegOperand(kind='REG', value=17)",
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_vector_processing_exception_puts_the_vxc_in_the_dxc_byte_and_abends_s0db():
    emitter = HlasmEmitter()
    emitter.store_var(VarName("__hlasm_fpc"), emitter.int_(0x8812_FF03))
    emit_vector_exception(emitter, emitter.int_((3 << 4) | 2))
    vm = _run(emitter.instructions())

    assert [_var(vm, "__hlasm_fpc"), _var(vm, "__hlasm_abend")] == [
        0x8812_3203,
        "S0DB",
    ]
