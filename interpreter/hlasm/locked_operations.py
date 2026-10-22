# pyright: standard
"""PLO function codes 0-61 (PoO Figure 7-380): one row per code, built from the operand width and the offsets of its registers, parameter-list fields and parameter-list addresses."""

from collections.abc import Mapping

from interpreter.hlasm.compare_chain import emit_cc
from interpreter.hlasm.hlasm_constants import DOUBLEWORD_BYTES, ONE_BYTE, WORD_BYTES
from interpreter.hlasm.locked_operation import Address, LockedOperation, Spot
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.places import (
    at_offset,
    in_storage,
    low_word,
    pointed_to,
    whole_register,
)
from interpreter.hlasm.plo_frame import PloFrame
from interpreter.register import Register

QUADWORD_BYTES = 16
OCTOWORD_BYTES = 32
FIRST_REGISTER = 0
THIRD_REGISTER = 2
UNEQUAL_RESULTS_OFFSET = 48
ANY_UNEQUAL_CC = 2
LIST_DATA_OFFSET = 64
OPERAND_ADDRESS_BYTES = 8
FIRST_STORE_ADDRESS = 72
STORE_ADDRESS_STRIDE = 32
REPLACEMENT = 1
COMPARE_VALUE = 0

type Comparisons = tuple[tuple[Spot, Spot], ...]
type Stores = tuple[tuple[Spot, Spot], ...]


def _second_address(frame: PloFrame) -> Register:
    return frame.second


def _fourth_address(frame: PloFrame) -> Register:
    return frame.fourth


def _register(index: int, offset: int, width: int) -> Spot:
    place = low_word if width == WORD_BYTES else whole_register
    return lambda frame: place(
        frame.emitter, reg_operand(frame.statement, index) + offset
    )


def _second(width: int) -> Spot:
    return lambda frame: in_storage(frame.emitter, frame.second, width)


def _fourth(width: int) -> Spot:
    return lambda frame: in_storage(frame.emitter, frame.fourth, width)


def _field(offset: int, width: int) -> Spot:
    return lambda frame: at_offset(frame.emitter, frame.fourth, offset, width)


def _pointed(offset: int, width: int) -> Spot:
    return lambda frame: pointed_to(frame.emitter, frame.fourth, offset, width)


def _numbered_cc(frame: PloFrame, compare: int) -> None:
    emit_cc(frame.emitter, compare + 1)


def _recorded(frame: PloFrame, compare: int) -> None:
    emitter = frame.emitter
    emit_cc(emitter, ANY_UNEQUAL_CC)
    emitter.store_storage(
        frame.fourth, UNEQUAL_RESULTS_OFFSET, ONE_BYTE, emitter.int_(compare + 1)
    )


def _checks(*checks: tuple[Address, int]) -> tuple[tuple[Address, int], ...]:
    return checks


def _row(
    width: int,
    shape: tuple[Comparisons, Stores],
    checks: tuple[tuple[Address, int], ...],
    even_registers: tuple[int, ...],
) -> LockedOperation:
    compares, stores = shape
    return LockedOperation(
        width, compares, stores, checks, even_registers, _numbered_cc
    )


def _in_registers(
    width: int, shape: tuple[Comparisons, Stores], fourth_boundary: int
) -> LockedOperation:
    checks = _checks((_second_address, width), (_fourth_address, fourth_boundary))
    return _row(width, shape, checks, (FIRST_REGISTER,))


def _in_list(width: int, shape: tuple[Comparisons, Stores]) -> LockedOperation:
    checks = _checks((_second_address, width), (_fourth_address, DOUBLEWORD_BYTES))
    return _row(width, shape, checks, ())


def _r1(width: int) -> Spot:
    return _register(FIRST_REGISTER, COMPARE_VALUE, width)


def _r1_replacement(width: int) -> Spot:
    return _register(FIRST_REGISTER, REPLACEMENT, width)


def _r3(width: int) -> Spot:
    return _register(THIRD_REGISTER, COMPARE_VALUE, width)


def _r3_replacement(width: int) -> Spot:
    return _register(THIRD_REGISTER, REPLACEMENT, width)


def _store_address(store: int) -> int:
    return FIRST_STORE_ADDRESS + STORE_ADDRESS_STRIDE * store


def _list_stores(width: int, operands: tuple[int, ...]) -> Stores:
    return tuple(
        (_field(at, width), _pointed(_store_address(k), width))
        for k, at in enumerate(operands)
    )


def compare_and_load_in_registers(width: int) -> LockedOperation:
    shape = (((_r1(width), _second(width)),), ((_fourth(width), _r3(width)),))
    checks = _checks((_second_address, width), (_fourth_address, width))
    return _row(width, shape, checks, ())


def compare_and_load_in_list(width: int, value: int, loaded: int) -> LockedOperation:
    compares = ((_field(value, width), _second(width)),)
    stores = ((_pointed(FIRST_STORE_ADDRESS, width), _field(loaded, width)),)
    return _in_list(width, (compares, stores))


def compare_and_swap_in_registers(width: int) -> LockedOperation:
    compares = ((_r1(width), _second(width)),)
    stores = ((_r1_replacement(width), _second(width)),)
    checks = _checks((_second_address, width))
    return _row(width, (compares, stores), checks, (FIRST_REGISTER,))


def compare_and_swap_in_list(
    width: int, value: int, replacement: int
) -> LockedOperation:
    compares = ((_field(value, width), _second(width)),)
    stores = ((_field(replacement, width), _second(width)),)
    return _in_list(width, (compares, stores))


def double_compare_and_swap_in_registers(width: int) -> LockedOperation:
    compares = ((_r1(width), _second(width)), (_r3(width), _fourth(width)))
    stores = (
        (_r3_replacement(width), _fourth(width)),
        (_r1_replacement(width), _second(width)),
    )
    checks = _checks((_second_address, width), (_fourth_address, width))
    return _row(width, (compares, stores), checks, (FIRST_REGISTER, THIRD_REGISTER))


def double_compare_and_swap_in_list(
    width: int, offsets: tuple[int, int, int, int]
) -> LockedOperation:
    value, replacement, third_value, third_replacement = offsets
    third = _pointed(FIRST_STORE_ADDRESS, width)
    compares = (
        (_field(value, width), _second(width)),
        (_field(third_value, width), third),
    )
    stores = (
        (_field(third_replacement, width), third),
        (_field(replacement, width), _second(width)),
    )
    return _in_list(width, (compares, stores))


def compare_and_swap_and_store_in_registers(width: int) -> LockedOperation:
    compares = ((_r1(width), _second(width)),)
    stores = (
        (_r3(width), _fourth(width)),
        (_r1_replacement(width), _second(width)),
    )
    return _in_registers(width, (compares, stores), width)


def compare_and_swap_and_stores_in_registers(
    width: int, operands: tuple[int, ...]
) -> LockedOperation:
    compares = ((_r1(width), _second(width)),)
    stores = (
        *_list_stores(width, operands),
        (_r1_replacement(width), _second(width)),
    )
    return _in_registers(width, (compares, stores), DOUBLEWORD_BYTES)


def compare_and_swap_and_stores_in_list(
    width: int, swap: tuple[int, int], operands: tuple[int, ...]
) -> LockedOperation:
    value, replacement = swap
    compares = ((_field(value, width), _second(width)),)
    stores = (
        *_list_stores(width, operands),
        (_field(replacement, width), _second(width)),
    )
    return _in_list(width, (compares, stores))


def _stride(width: int) -> int:
    return max(width, DOUBLEWORD_BYTES)


def _list_data(width: int, k: int) -> Spot:
    return _field(LIST_DATA_OFFSET + _stride(width) * k, width)


def _operand(width: int, k: int) -> Spot:
    return _pointed(OPERAND_ADDRESS_BYTES * k, width)


def multiple_compare_and_swap(operands: int, width: int) -> LockedOperation:
    compares = tuple(
        (_list_data(width, k), _operand(width, k)) for k in range(operands)
    )
    order = (*range(1, operands), 0)
    stores = tuple((_list_data(width, operands + k), _operand(width, k)) for k in order)
    checks = _checks((_fourth_address, DOUBLEWORD_BYTES))
    return LockedOperation(width, compares, stores, checks, (), _recorded)


def multiple_load(operands: int, width: int) -> LockedOperation:
    stores = tuple((_operand(width, k), _list_data(width, k)) for k in range(operands))
    checks = _checks((_fourth_address, DOUBLEWORD_BYTES))
    return LockedOperation(width, (), stores, checks, (), _numbered_cc)


def multiple_store(operands: int, width: int) -> LockedOperation:
    stores = tuple((_list_data(width, k), _operand(width, k)) for k in range(operands))
    checks = _checks((_fourth_address, DOUBLEWORD_BYTES))
    return LockedOperation(width, (), stores, checks, (), _numbered_cc)


FW, DW, QW, OW = WORD_BYTES, DOUBLEWORD_BYTES, QUADWORD_BYTES, OCTOWORD_BYTES

LOCKED_OPERATIONS: Mapping[int, LockedOperation] = {
    0: compare_and_load_in_registers(FW),
    1: compare_and_load_in_list(DW, 8, 40),
    2: compare_and_load_in_registers(DW),
    3: compare_and_load_in_list(QW, 0, 32),
    4: compare_and_swap_in_registers(FW),
    5: compare_and_swap_in_list(DW, 8, 24),
    6: compare_and_swap_in_registers(DW),
    7: compare_and_swap_in_list(QW, 0, 16),
    8: double_compare_and_swap_in_registers(FW),
    9: double_compare_and_swap_in_list(DW, (8, 24, 40, 56)),
    10: double_compare_and_swap_in_registers(DW),
    11: double_compare_and_swap_in_list(QW, (0, 16, 32, 48)),
    12: compare_and_swap_and_store_in_registers(FW),
    13: compare_and_swap_and_stores_in_list(DW, (8, 24), (56,)),
    14: compare_and_swap_and_store_in_registers(DW),
    15: compare_and_swap_and_stores_in_list(QW, (0, 16), (48,)),
    16: compare_and_swap_and_stores_in_registers(FW, (60, 92)),
    17: compare_and_swap_and_stores_in_list(DW, (8, 24), (56, 88)),
    18: compare_and_swap_and_stores_in_registers(DW, (56, 88)),
    19: compare_and_swap_and_stores_in_list(QW, (0, 16), (48, 80)),
    20: compare_and_swap_and_stores_in_registers(FW, (60, 92, 124)),
    21: compare_and_swap_and_stores_in_list(DW, (8, 24), (56, 88, 120)),
    22: compare_and_swap_and_stores_in_registers(DW, (56, 88, 120)),
    23: compare_and_swap_and_stores_in_list(QW, (0, 16), (48, 80, 112)),
    24: compare_and_load_in_list(OW, 0, 32),
    25: compare_and_swap_in_list(OW, 0, 32),
    26: double_compare_and_swap_in_list(OW, (0, 32, 80, 112)),
    27: compare_and_swap_and_stores_in_list(OW, (0, 32), (80,)),
    28: compare_and_swap_and_stores_in_list(OW, (0, 32), (112, 144)),
    29: compare_and_swap_and_stores_in_list(OW, (0, 32), (144, 176, 208)),
    **{
        30 + k: multiple_compare_and_swap(3, width)
        for k, width in enumerate((FW, DW, QW, OW))
    },
    **{
        34 + k: multiple_compare_and_swap(4, width)
        for k, width in enumerate((FW, DW, QW, OW))
    },
    38: multiple_load(1, OW),
    39: multiple_load(2, QW),
    40: multiple_load(2, OW),
    **{41 + k: multiple_load(3, width) for k, width in enumerate((FW, DW, QW, OW))},
    **{45 + k: multiple_load(4, width) for k, width in enumerate((FW, DW, QW, OW))},
    49: multiple_store(1, OW),
    **{50 + k: multiple_store(2, width) for k, width in enumerate((FW, DW, QW, OW))},
    **{54 + k: multiple_store(3, width) for k, width in enumerate((FW, DW, QW, OW))},
    **{58 + k: multiple_store(4, width) for k, width in enumerate((FW, DW, QW, OW))},
}
