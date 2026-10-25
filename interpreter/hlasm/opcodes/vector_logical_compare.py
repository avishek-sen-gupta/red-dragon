# pyright: standard
"""Vector integer logical, compare, minimum and maximum, complement and count instructions: bitwise forms and VEVAL over whole registers, element-wise forms unrolled per element, the CC-setting compares as element functions, and bit counts as sums over the whole register."""

from collections.abc import Callable, Mapping, Sequence
from functools import reduce

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bit_fields import combined_bits
from interpreter.hlasm.conditional import pick
from interpreter.hlasm.element_return_field import CC_FIELD, RESULT_BITS
from interpreter.hlasm.element_size import ElementSize
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import Body, IrFunction
from interpreter.hlasm.opcodes.vector_fields import (
    FIFTH,
    FOURTH,
    SECOND,
    THIRD,
    V1,
    assembled,
    below,
    count_cc,
    element_bits,
    element_of,
    element_wise,
    ones,
    per_size,
    replication,
    status_function,
    to_v1,
    vr_at,
)
from interpreter.hlasm.operands import imm_operand, vec_reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.vector_elements import load_element
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

ALL_ONES = ones(RESULT_BITS)
ALTERNATE_BITS = ALL_ONES // 3
ALTERNATE_PAIRS = ALL_ONES // 5
ALTERNATE_NIBBLES = ALL_ONES // 17
EVALUATION_BITS = 8
EVALUATION_INPUTS = 3

B, H, F, G, Q = (
    ElementSize.BYTE,
    ElementSize.HALFWORD,
    ElementSize.WORD,
    ElementSize.DOUBLEWORD,
    ElementSize.QUADWORD,
)
EVERY_SIZE = frozenset({B, H, F, G, Q})
UP_TO_DOUBLEWORD = frozenset({B, H, F, G})
COMPARED_ELEMENT = {B: 7, H: 3, F: 1, G: 0, Q: 0}

type Combine = Callable[[HlasmEmitter, Register, Register], Register]
type Order = Callable[[HlasmEmitter, Register], Register]
type Test = Callable[[HlasmEmitter, Register, Register], Register]
type Counts = Callable[[HlasmEmitter, Register, ElementSize], Register]


def _not(emitter: HlasmEmitter, value: Register) -> Register:
    return emitter.binop(BinopKind.BIT_XOR, value, emitter.int_(ALL_ONES))


def _op(kind: BinopKind) -> Combine:
    return lambda emitter, left, right: emitter.binop(kind, left, right)


def _complemented_right(combine: Combine) -> Combine:
    return lambda emitter, left, right: combine(emitter, left, _not(emitter, right))


def _complemented_result(combine: Combine) -> Combine:
    return lambda emitter, left, right: _not(emitter, combine(emitter, left, right))


def _bitwise(combine: Combine) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        left = vr_at(SECOND)(emitter, statement)
        right = vr_at(THIRD)(emitter, statement)
        to_v1(emitter, statement, combine(emitter, left, right))

    return lower


def _literal(emitter: HlasmEmitter, value: Register, wanted: int) -> Register:
    return value if wanted else _not(emitter, value)


def _minterm(emitter: HlasmEmitter, inputs: Sequence[Register], index: int) -> Register:
    literals = [
        _literal(emitter, value, index >> (EVALUATION_INPUTS - 1 - at) & 1)
        for at, value in enumerate(inputs)
    ]
    return reduce(
        lambda left, right: emitter.binop(BinopKind.BIT_AND, left, right), literals
    )


def _evaluate(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    inputs = [vr_at(at)(emitter, statement) for at in (SECOND, THIRD, FOURTH)]
    table = imm_operand(statement, FIFTH)
    terms = [
        _minterm(emitter, inputs, index)
        for index in range(EVALUATION_BITS)
        if table >> (EVALUATION_BITS - 1 - index) & 1
    ]
    to_v1(emitter, statement, combined_bits(emitter, [emitter.int_(0), *terms]))


def _signed_order(size: ElementSize) -> Order:
    sign = 1 << (element_bits(size) - 1)
    return lambda emitter, value: emitter.binop(
        BinopKind.BIT_XOR, value, emitter.int_(sign)
    )


def _logical_order(size: ElementSize) -> Order:
    return lambda emitter, value: value


def _extreme(
    order_of: Callable[[ElementSize], Order], larger: bool
) -> Callable[[ElementSize], StatementLowering]:
    def build(size: ElementSize) -> StatementLowering:
        order = order_of(size)

        def op(emitter: HlasmEmitter, pair: Sequence[Register]) -> Register:
            left, right = pair
            lower = below(emitter, order(emitter, left), order(emitter, right))
            return (
                pick(emitter, lower, right, left)
                if larger
                else pick(emitter, lower, left, right)
            )

        return element_wise(2, op)(size)

    return build


def _negated(emitter: HlasmEmitter, value: Register) -> Register:
    return emitter.binop(BinopKind.SUB, emitter.int_(0), value)


def _complement(size: ElementSize) -> StatementLowering:
    return element_wise(1, lambda emitter, one: _negated(emitter, one[0]))(size)


def _positive(size: ElementSize) -> StatementLowering:
    sign_bit = element_bits(size) - 1

    def op(emitter: HlasmEmitter, one: Sequence[Register]) -> Register:
        value = one[0]
        sign = emitter.binop(BinopKind.RSHIFT, value, emitter.int_(sign_bit))
        return pick(emitter, sign, _negated(emitter, value), value)

    return element_wise(1, op)(size)


def _equal(size: ElementSize) -> Test:
    def test(emitter: HlasmEmitter, left: Register, right: Register) -> Register:
        difference = emitter.binop(BinopKind.BIT_XOR, left, right)
        differs = below(emitter, emitter.int_(0), difference)
        return emitter.binop(BinopKind.SUB, emitter.int_(1), differs)

    return test


def _high(order_of: Callable[[ElementSize], Order]) -> Callable[[ElementSize], Test]:
    def build(size: ElementSize) -> Test:
        order = order_of(size)
        return lambda emitter, left, right: below(
            emitter, order(emitter, right), order(emitter, left)
        )

    return build


def _compare_body(size: ElementSize, test: Test) -> Body:
    filled = ones(element_bits(size))

    def body(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
        left, right = parameters
        flags = [
            test(
                emitter,
                element_of(emitter, left, size, at),
                element_of(emitter, right, size, at),
            )
            for at in range(size.count)
        ]
        masks = [
            emitter.binop(BinopKind.MUL, flag, emitter.int_(filled)) for flag in flags
        ]
        misses = reduce(
            lambda total, flag: emitter.binop(BinopKind.SUB, total, flag),
            flags,
            emitter.int_(size.count),
        )
        cc = CC_FIELD.placed(emitter, count_cc(emitter, misses, size.count))
        return emitter.binop(BinopKind.BIT_OR, assembled(emitter, size, masks), cc)

    return body


def _compare_functions(
    kind: str, test_of: Callable[[ElementSize], Test]
) -> Mapping[ElementSize, IrFunction]:
    return {
        size: IrFunction(
            f"__hlasm_vector_compare_{kind}_{size.name.lower()}",
            2,
            _compare_body(size, test_of(size)),
        )
        for size in EVERY_SIZE
    }


def _element_compare(
    order_of: Callable[[ElementSize], Order],
) -> Callable[[ElementSize], StatementLowering]:
    def build(size: ElementSize) -> StatementLowering:
        order, index = order_of(size), COMPARED_ELEMENT[size]

        def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
            first, second = (
                order(
                    emitter,
                    load_element(emitter, vec_reg_operand(statement, at), size, index),
                )
                for at in (V1, SECOND)
            )
            low, high = below(emitter, first, second), below(emitter, second, first)
            doubled = emitter.binop(BinopKind.MUL, high, emitter.int_(2))
            emitter.set_cc(emitter.binop(BinopKind.ADD, low, doubled))

        return lower

    return build


def _test_under_mask(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    mask = vr_at(SECOND)(emitter, statement)
    selected = emitter.binop(BinopKind.BIT_AND, vr_at(V1)(emitter, statement), mask)
    some = below(emitter, emitter.int_(0), selected)
    short = below(emitter, selected, mask)
    every = emitter.binop(BinopKind.SUB, emitter.int_(1), short)
    doubled = emitter.binop(BinopKind.MUL, every, emitter.int_(2))
    weight = emitter.binop(BinopKind.ADD, emitter.int_(1), doubled)
    emitter.set_cc(emitter.binop(BinopKind.MUL, some, weight))


def _masked_shift(
    emitter: HlasmEmitter, value: Register, kind: BinopKind, by: int, keep: int
) -> Register:
    moved = emitter.binop(kind, value, emitter.int_(by))
    return emitter.binop(BinopKind.BIT_AND, moved, emitter.int_(keep))


def _folded(emitter: HlasmEmitter, counts: Register, lane: ElementSize) -> Register:
    half = element_bits(lane) // 2
    upper = emitter.binop(BinopKind.RSHIFT, counts, emitter.int_(half))
    total = emitter.binop(BinopKind.ADD, counts, upper)
    return emitter.binop(
        BinopKind.BIT_AND, total, emitter.int_(ones(half) * replication(lane))
    )


def _population(emitter: HlasmEmitter, value: Register, size: ElementSize) -> Register:
    halved = _masked_shift(emitter, value, BinopKind.RSHIFT, 1, ALTERNATE_BITS)
    pairs = emitter.binop(BinopKind.SUB, value, halved)
    low = emitter.binop(BinopKind.BIT_AND, pairs, emitter.int_(ALTERNATE_PAIRS))
    high = _masked_shift(emitter, pairs, BinopKind.RSHIFT, 2, ALTERNATE_PAIRS)
    nibbles = emitter.binop(BinopKind.ADD, low, high)
    upper = emitter.binop(BinopKind.RSHIFT, nibbles, emitter.int_(4))
    summed = emitter.binop(BinopKind.ADD, nibbles, upper)
    counts = emitter.binop(BinopKind.BIT_AND, summed, emitter.int_(ALTERNATE_NIBBLES))
    lanes = [lane for lane in ElementSize if B.value < lane.value <= size.value]
    return reduce(lambda total, lane: _folded(emitter, total, lane), lanes, counts)


def _smeared(kind: BinopKind, keep: Callable[[int, int], int]) -> Counts:
    def smear(emitter: HlasmEmitter, value: Register, size: ElementSize) -> Register:
        bits = element_bits(size)
        steps = [1 << k for k in range(bits.bit_length() - 1)]
        return reduce(
            lambda total, by: emitter.binop(
                BinopKind.BIT_OR,
                total,
                _masked_shift(
                    emitter, total, kind, by, keep(bits, by) * replication(size)
                ),
            ),
            steps,
            value,
        )

    return smear


def _zeros(smear: Counts) -> Callable[[ElementSize], StatementLowering]:
    def build(size: ElementSize) -> StatementLowering:
        def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
            smeared = smear(emitter, vr_at(SECOND)(emitter, statement), size)
            widths = emitter.int_(element_bits(size) * replication(size))
            counted = _population(emitter, smeared, size)
            to_v1(emitter, statement, emitter.binop(BinopKind.SUB, widths, counted))

        return lower

    return build


def _population_count(size: ElementSize) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        source = vr_at(SECOND)(emitter, statement)
        to_v1(emitter, statement, _population(emitter, source, size))

    return lower


LEADING = _smeared(BinopKind.RSHIFT, lambda bits, by: ones(bits - by))
TRAILING = _smeared(BinopKind.LSHIFT, lambda bits, by: ones(bits) ^ ones(by))
EQUAL = _compare_functions("equal", _equal)
HIGH = _compare_functions("high", _high(_signed_order))
HIGH_LOGICAL = _compare_functions("high_logical", _high(_logical_order))

VECTOR_LOGICAL_COMPARE_LOWERINGS: Mapping[str, StatementLowering] = {
    "VN": _bitwise(_op(BinopKind.BIT_AND)),
    "VNC": _bitwise(_complemented_right(_op(BinopKind.BIT_AND))),
    "VNN": _bitwise(_complemented_result(_op(BinopKind.BIT_AND))),
    "VNO": _bitwise(_complemented_result(_op(BinopKind.BIT_OR))),
    "VNX": _bitwise(_complemented_result(_op(BinopKind.BIT_XOR))),
    "VO": _bitwise(_op(BinopKind.BIT_OR)),
    "VOC": _bitwise(_complemented_right(_op(BinopKind.BIT_OR))),
    "VX": _bitwise(_op(BinopKind.BIT_XOR)),
    "VEVAL": _evaluate,
    "VCEQ": per_size(FOURTH, EVERY_SIZE, status_function(EQUAL)),
    "VCH": per_size(FOURTH, EVERY_SIZE, status_function(HIGH)),
    "VCHL": per_size(FOURTH, EVERY_SIZE, status_function(HIGH_LOGICAL)),
    "VEC": per_size(THIRD, EVERY_SIZE, _element_compare(_signed_order)),
    "VECL": per_size(THIRD, EVERY_SIZE, _element_compare(_logical_order)),
    "VMN": per_size(FOURTH, EVERY_SIZE, _extreme(_signed_order, larger=False)),
    "VMNL": per_size(FOURTH, EVERY_SIZE, _extreme(_logical_order, larger=False)),
    "VMX": per_size(FOURTH, EVERY_SIZE, _extreme(_signed_order, larger=True)),
    "VMXL": per_size(FOURTH, EVERY_SIZE, _extreme(_logical_order, larger=True)),
    "VTM": _test_under_mask,
    "VLC": per_size(THIRD, EVERY_SIZE, _complement),
    "VLP": per_size(THIRD, EVERY_SIZE, _positive),
    "VPOPCT": per_size(THIRD, UP_TO_DOUBLEWORD, _population_count),
    "VCLZ": per_size(THIRD, EVERY_SIZE, _zeros(LEADING)),
    "VCTZ": per_size(THIRD, EVERY_SIZE, _zeros(TRAILING)),
}
