# pyright: standard
"""Vector support register manipulation: generated masks, elements to and from general registers, merges, permutes, packs with and without saturation, replication, selection, sign extension and unpacks, as shifts and masks over 128-bit registers and the 256-bit V2 || V3."""

from collections.abc import Callable, Mapping, Sequence
from functools import reduce

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bit_fields import combined_bits, placed_bits
from interpreter.hlasm.conditional import pick
from interpreter.hlasm.data_movement import (
    Transform,
    gather_bytes,
    keep,
    move,
    signed,
    signed_immediate,
    storage_address_at,
)
from interpreter.hlasm.element_return_field import (
    CC_FIELD,
    RESULT_BITS,
    RESULT_FIELD,
)
from interpreter.hlasm.element_size import ElementSize
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    BYTE_MASK,
    DOUBLEWORD_BITS,
    DOUBLEWORD_BYTES,
    HALFWORD_BITS,
    VECTOR_REGISTER_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import Body, IrFunction
from interpreter.hlasm.opcodes.vector_fields import (
    V1,
    element_index_checked,
    m_field,
    per_size,
    replicated,
    replication,
    to_v1,
    vr_at,
)
from interpreter.hlasm.operands import imm_operand, reg_operand, vec_reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.vector_elements import (
    load_element,
    load_element_at,
    store_element_at,
)
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

SECOND = 1
THIRD = 2
FOURTH = 3
FIFTH = 4
PAIR_BITS = 2 * RESULT_BITS
PAIR_BYTES = 2 * VECTOR_REGISTER_BYTES
HALF_BYTES = VECTOR_REGISTER_BYTES // 2
LAST_BYTE = VECTOR_REGISTER_BYTES - 1
BYTE_MASK_BITS = VECTOR_REGISTER_BYTES
PERMUTE_INDEX_MASK = PAIR_BYTES - 1
BIT_PERMUTE_FIRST = 48
SECOND_DOUBLEWORD_BIT = 0b0100
THIRD_DOUBLEWORD_BIT = 0b0001
CONDITION_CODE_SET = 0b0001

B, H, F, G, Q = (
    ElementSize.BYTE,
    ElementSize.HALFWORD,
    ElementSize.WORD,
    ElementSize.DOUBLEWORD,
    ElementSize.QUADWORD,
)
UP_TO_DOUBLEWORD = frozenset({B, H, F, G})
EVERY_SIZE = frozenset({B, H, F, G, Q})
PACKED_SIZES = frozenset({H, F, G})
SIGN_EXTENDED_SIZES = frozenset({B, H, F})

type ByteMap = Mapping[int, int]
type Clamp = Callable[[HlasmEmitter, Register, int], tuple[Register, Register]]


def _ones(bits: int) -> int:
    return (1 << bits) - 1


def _bits(size: ElementSize) -> int:
    return BITS_PER_BYTE * size.width


def _concatenated(
    emitter: HlasmEmitter, high: Register, low: Register, low_bits: int
) -> Register:
    moved = emitter.binop(BinopKind.LSHIFT, high, emitter.int_(low_bits))
    return emitter.binop(BinopKind.BIT_OR, moved, low)


def _pair(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    high, low = vr_at(SECOND)(emitter, statement), vr_at(THIRD)(emitter, statement)
    return _concatenated(emitter, high, low, RESULT_BITS)


def _gathered(source_bytes: int, targets: ByteMap) -> Transform:
    moves = tuple(
        (source_bytes - 1 - at, LAST_BYTE - target) for target, at in targets.items()
    )
    return lambda emitter, value: gather_bytes(emitter, value, moves)


def _from_pair(targets: ByteMap) -> StatementLowering:
    return move(_pair, (_gathered(PAIR_BYTES, targets),), to_v1)


def _merged(first: int) -> Callable[[ElementSize], StatementLowering]:
    def build(size: ElementSize) -> StatementLowering:
        w = size.width
        return _from_pair(
            {
                j * w + b: (j % 2) * VECTOR_REGISTER_BYTES + first + (j // 2) * w + b
                for j in range(size.count)
                for b in range(w)
            },
        )

    return build


def _packed(size: ElementSize) -> StatementLowering:
    half = size.width // 2
    return _from_pair(
        {
            j * half + b: j * size.width + half + b
            for j in range(2 * size.count)
            for b in range(half)
        },
    )


def _zero_extended(first: int, size: ElementSize) -> Transform:
    w = size.width
    return _gathered(
        VECTOR_REGISTER_BYTES,
        {
            2 * w * j + w + b: first + w * j + b
            for j in range(HALF_BYTES // w)
            for b in range(w)
        },
    )


def _sign_spread(
    emitter: HlasmEmitter, value: Register, element_bits: int, sign_bit: int
) -> Register:
    signs = sum(
        1 << (element_bits * i + sign_bit) for i in range(RESULT_BITS // element_bits)
    )
    sign = emitter.binop(BinopKind.BIT_AND, value, emitter.int_(signs))
    return emitter.binop(BinopKind.RSHIFT, sign, emitter.int_(sign_bit))


def _sign_filled(element_bits: int, value_bits: int) -> Transform:
    fill = _ones(element_bits) ^ _ones(value_bits)

    def extend(emitter: HlasmEmitter, value: Register) -> Register:
        spread = _sign_spread(emitter, value, element_bits, value_bits - 1)
        ones = emitter.binop(BinopKind.MUL, spread, emitter.int_(fill))
        return emitter.binop(BinopKind.BIT_OR, value, ones)

    return extend


def _unpacked(first: int) -> Callable[[ElementSize], StatementLowering]:
    return lambda size: move(
        vr_at(SECOND),
        (_zero_extended(first, size), _sign_filled(2 * _bits(size), _bits(size))),
        to_v1,
    )


def _logically_unpacked(first: int) -> Callable[[ElementSize], StatementLowering]:
    return lambda size: move(vr_at(SECOND), (_zero_extended(first, size),), to_v1)


def _sign_extended_to_doubleword(size: ElementSize) -> StatementLowering:
    low = _ones(_bits(size)) * (1 | 1 << DOUBLEWORD_BITS)
    return move(
        vr_at(SECOND), (keep(low), _sign_filled(DOUBLEWORD_BITS, _bits(size))), to_v1
    )


def _selected(
    emitter: HlasmEmitter, mask: Register, chosen: Register, otherwise: Register
) -> Register:
    inverse = emitter.binop(BinopKind.BIT_XOR, mask, emitter.int_(_ones(RESULT_BITS)))
    taken = emitter.binop(BinopKind.BIT_AND, chosen, mask)
    left = emitter.binop(BinopKind.BIT_AND, otherwise, inverse)
    return emitter.binop(BinopKind.BIT_OR, taken, left)


def _selection(selector: Transform) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        chosen = vr_at(SECOND)(emitter, statement)
        otherwise = vr_at(THIRD)(emitter, statement)
        mask = selector(emitter, vr_at(FOURTH)(emitter, statement))
        to_v1(emitter, statement, _selected(emitter, mask, chosen, otherwise))

    return lower


def _element_selector(size: ElementSize) -> Transform:
    bits = _bits(size)

    def mask(emitter: HlasmEmitter, value: Register) -> Register:
        spread = _sign_spread(emitter, value, bits, bits - 1)
        return emitter.binop(BinopKind.MUL, spread, emitter.int_(_ones(bits)))

    return mask


def _byte_of(emitter: HlasmEmitter, value: Register, index: int) -> Register:
    moved = emitter.binop(
        BinopKind.RSHIFT, value, emitter.int_(BITS_PER_BYTE * (LAST_BYTE - index))
    )
    return emitter.binop(BinopKind.BIT_AND, moved, emitter.int_(BYTE_MASK))


def _picked(
    emitter: HlasmEmitter, source: Register, index: Register, bits: int
) -> Register:
    last = emitter.int_(PAIR_BITS // bits - 1)
    units = emitter.binop(BinopKind.SUB, last, index)
    shift = emitter.binop(BinopKind.MUL, units, emitter.int_(bits))
    moved = emitter.binop(BinopKind.RSHIFT, source, shift)
    return emitter.binop(BinopKind.BIT_AND, moved, emitter.int_(_ones(bits)))


def _permute(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    pair = _pair(emitter, statement)
    indexes = vr_at(FOURTH)(emitter, statement)

    def byte(at: int) -> Register:
        index = emitter.binop(
            BinopKind.BIT_AND,
            _byte_of(emitter, indexes, at),
            emitter.int_(PERMUTE_INDEX_MASK),
        )
        picked = _picked(emitter, pair, index, BITS_PER_BYTE)
        return placed_bits(emitter, picked, BYTE_MASK, BITS_PER_BYTE * (LAST_BYTE - at))

    to_v1(
        emitter,
        statement,
        combined_bits(emitter, [byte(at) for at in range(VECTOR_REGISTER_BYTES)]),
    )


def _bit_permute(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    source = emitter.binop(
        BinopKind.LSHIFT, vr_at(SECOND)(emitter, statement), emitter.int_(RESULT_BITS)
    )
    indexes = vr_at(THIRD)(emitter, statement)

    def bit(at: int) -> Register:
        picked = _picked(emitter, source, _byte_of(emitter, indexes, at), 1)
        return placed_bits(emitter, picked, 1, RESULT_BITS - 1 - BIT_PERMUTE_FIRST - at)

    to_v1(
        emitter,
        statement,
        combined_bits(emitter, [bit(at) for at in range(VECTOR_REGISTER_BYTES)]),
    )


def _element_masks(size: ElementSize) -> StatementLowering:
    bits = _bits(size)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        source = vr_at(SECOND)(emitter, statement)

        def element(at: int) -> Register:
            moved = emitter.binop(
                BinopKind.RSHIFT, source, emitter.int_(RESULT_BITS - 1 - at)
            )
            bit = emitter.binop(BinopKind.BIT_AND, moved, emitter.int_(1))
            ones = _ones(bits) << (RESULT_BITS - bits * (at + 1))
            return emitter.binop(BinopKind.MUL, bit, emitter.int_(ones))

        pieces = [element(at) for at in range(size.count)]
        to_v1(emitter, statement, combined_bits(emitter, pieces))

    return lower


def _byte_mask(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    mask = imm_operand(statement, SECOND)
    image = sum(
        BYTE_MASK << (BITS_PER_BYTE * (LAST_BYTE - k))
        for k in range(BYTE_MASK_BITS)
        if mask >> (BYTE_MASK_BITS - 1 - k) & 1
    )
    to_v1(emitter, statement, emitter.int_(image))


def _bit_range(bits: int, start: int, end: int) -> int:
    first, last = start % bits, end % bits
    positions = (
        range(first, last + 1)
        if first <= last
        else (*range(first, bits), *range(last + 1))
    )
    return sum(1 << (bits - 1 - p) for p in positions)


def _generated_mask(size: ElementSize) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        element = _bit_range(
            _bits(size), imm_operand(statement, SECOND), imm_operand(statement, THIRD)
        )
        to_v1(emitter, statement, emitter.int_(element * replication(size)))

    return lower


def _element_to_gpr(size: ElementSize) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        index = storage_address_at(THIRD)(emitter, statement)
        v = vec_reg_operand(statement, SECOND)
        value = load_element_at(emitter, v, size, index)
        emitter.store_gr64(reg_operand(statement, V1), value)

    return lower


def _gpr_to_element(size: ElementSize) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        index = storage_address_at(THIRD)(emitter, statement)
        value = emitter.load_gr64(reg_operand(statement, SECOND))
        store_element_at(emitter, vec_reg_operand(statement, V1), size, index, value)

    return lower


def _gprs_to_vr(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    high = emitter.load_gr64(reg_operand(statement, SECOND))
    low = emitter.load_gr64(reg_operand(statement, THIRD))
    to_v1(emitter, statement, _concatenated(emitter, high, low, DOUBLEWORD_BITS))


def _doubleword_permute(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    m4 = m_field(statement, FOURTH)
    second = DOUBLEWORD_BYTES * int(m4 & SECOND_DOUBLEWORD_BIT != 0)
    third = VECTOR_REGISTER_BYTES + DOUBLEWORD_BYTES * int(
        m4 & THIRD_DOUBLEWORD_BIT != 0
    )
    targets = {
        **{b: second + b for b in range(DOUBLEWORD_BYTES)},
        **{DOUBLEWORD_BYTES + b: third + b for b in range(DOUBLEWORD_BYTES)},
    }
    _from_pair(targets)(emitter, statement)


def _replicated_element(size: ElementSize) -> StatementLowering:
    def element(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
        index = imm_operand(statement, THIRD)
        return load_element(emitter, vec_reg_operand(statement, SECOND), size, index)

    return element_index_checked(THIRD, size, move(element, (replicated(size),), to_v1))


def _replicated_immediate(size: ElementSize) -> StatementLowering:
    return move(
        signed_immediate(SECOND, HALFWORD_BITS),
        (keep(_ones(_bits(size))), replicated(size)),
        to_v1,
    )


def _below(emitter: HlasmEmitter, left: Register, right: Register) -> Register:
    difference = emitter.binop(BinopKind.SUB, left, right)
    borrow = emitter.binop(BinopKind.RSHIFT, difference, emitter.int_(RESULT_BITS))
    return emitter.binop(BinopKind.BIT_AND, borrow, emitter.int_(1))


def _signed_clamp(
    emitter: HlasmEmitter, element: Register, bits: int
) -> tuple[Register, Register]:
    highest = emitter.int_(_ones(bits // 2 - 1))
    lowest = emitter.int_(-(1 << (bits // 2 - 1)))
    value = signed(bits)(emitter, element)
    over, under = _below(emitter, highest, value), _below(emitter, value, lowest)
    clamped = pick(emitter, over, highest, pick(emitter, under, lowest, value))
    return clamped, emitter.binop(BinopKind.ADD, over, under)


def _logical_clamp(
    emitter: HlasmEmitter, element: Register, bits: int
) -> tuple[Register, Register]:
    highest = emitter.int_(_ones(bits // 2))
    over = _below(emitter, highest, element)
    return pick(emitter, over, highest, element), over


def _saturation_cc(
    emitter: HlasmEmitter, saturated: Register, elements: int
) -> Register:
    some = _below(emitter, emitter.int_(0), saturated)
    short = _below(emitter, saturated, emitter.int_(elements))
    every = emitter.binop(BinopKind.SUB, emitter.int_(1), short)
    doubled = emitter.binop(BinopKind.MUL, every, emitter.int_(2))
    return emitter.binop(BinopKind.ADD, some, doubled)


def _pack_body(clamp: Clamp, size: ElementSize) -> Body:
    bits, elements = _bits(size), 2 * size.count
    half = bits // 2

    def body(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
        high, low = parameters
        pair = _concatenated(emitter, high, low, RESULT_BITS)

        def element(at: int) -> tuple[Register, Register]:
            moved = emitter.binop(
                BinopKind.RSHIFT, pair, emitter.int_(PAIR_BITS - bits * (at + 1))
            )
            source = emitter.binop(BinopKind.BIT_AND, moved, emitter.int_(_ones(bits)))
            value, saturated = clamp(emitter, source, bits)
            placed = placed_bits(
                emitter, value, _ones(half), RESULT_BITS - half * (at + 1)
            )
            return placed, saturated

        packed = [element(at) for at in range(elements)]
        result = combined_bits(emitter, [placed for placed, _ in packed])
        saturated = reduce(
            lambda left, right: emitter.binop(BinopKind.ADD, left, right),
            [count for _, count in packed],
        )
        cc = CC_FIELD.placed(emitter, _saturation_cc(emitter, saturated, elements))
        return emitter.binop(BinopKind.BIT_OR, result, cc)

    return body


def _pack_functions(kind: str, clamp: Clamp) -> Mapping[ElementSize, IrFunction]:
    return {
        size: IrFunction(
            f"__hlasm_vector_pack_{kind}_{size.name.lower()}",
            2,
            _pack_body(clamp, size),
        )
        for size in PACKED_SIZES
    }


def _packed_saturating(
    function: IrFunction, emitter: HlasmEmitter, statement: MachineStatement
) -> None:
    sources = (vr_at(SECOND)(emitter, statement), vr_at(THIRD)(emitter, statement))
    returned = function.call(emitter, sources)
    to_v1(emitter, statement, RESULT_FIELD.of(emitter, returned))
    if m_field(statement, FIFTH) & CONDITION_CODE_SET:
        emitter.set_cc(CC_FIELD.of(emitter, returned))


def _saturating_pack(
    functions: Mapping[ElementSize, IrFunction],
) -> Callable[[ElementSize], StatementLowering]:
    return lambda size: lambda emitter, statement: _packed_saturating(
        functions[size], emitter, statement
    )


SIGNED_PACKS = _pack_functions("saturate", _signed_clamp)
LOGICAL_PACKS = _pack_functions("logical_saturate", _logical_clamp)

VECTOR_REGISTER_LOWERINGS: Mapping[str, StatementLowering] = {
    "VGBM": _byte_mask,
    "VGM": per_size(FOURTH, UP_TO_DOUBLEWORD, _generated_mask),
    "VGEM": per_size(THIRD, EVERY_SIZE, _element_masks),
    "VLGV": per_size(FOURTH, UP_TO_DOUBLEWORD, _element_to_gpr),
    "VLVG": per_size(FOURTH, UP_TO_DOUBLEWORD, _gpr_to_element),
    "VLVGP": _gprs_to_vr,
    "VMRH": per_size(FOURTH, UP_TO_DOUBLEWORD, _merged(0)),
    "VMRL": per_size(FOURTH, UP_TO_DOUBLEWORD, _merged(HALF_BYTES)),
    "VPDI": _doubleword_permute,
    "VPERM": _permute,
    "VBPERM": _bit_permute,
    "VPK": per_size(FOURTH, PACKED_SIZES, _packed),
    "VPKS": per_size(FOURTH, PACKED_SIZES, _saturating_pack(SIGNED_PACKS)),
    "VPKLS": per_size(FOURTH, PACKED_SIZES, _saturating_pack(LOGICAL_PACKS)),
    "VREP": per_size(FOURTH, UP_TO_DOUBLEWORD, _replicated_element),
    "VREPI": per_size(THIRD, UP_TO_DOUBLEWORD, _replicated_immediate),
    "VSEG": per_size(THIRD, SIGN_EXTENDED_SIZES, _sign_extended_to_doubleword),
    "VSEL": _selection(lambda emitter, value: value),
    "VBLEND": per_size(
        FIFTH, EVERY_SIZE, lambda size: _selection(_element_selector(size))
    ),
    "VUPH": per_size(THIRD, UP_TO_DOUBLEWORD, _unpacked(0)),
    "VUPL": per_size(THIRD, UP_TO_DOUBLEWORD, _unpacked(HALF_BYTES)),
    "VUPLH": per_size(THIRD, UP_TO_DOUBLEWORD, _logically_unpacked(0)),
    "VUPLL": per_size(THIRD, UP_TO_DOUBLEWORD, _logically_unpacked(HALF_BYTES)),
}
