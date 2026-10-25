# pyright: standard
"""Vector integer add, subtract, average, multiply, Galois-field multiply, checksum, sum and divide instructions: element-wise forms unrolled per element and masked on assembly, double-wide forms over even and odd element pairs, and the divides as element functions whose integer-divide condition abends S0DB before V1 is written."""

from collections.abc import Callable, Mapping, Sequence
from functools import reduce

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bit_fields import combined_bits
from interpreter.hlasm.conditional import emit_when, pick
from interpreter.hlasm.element_return_field import (
    RESULT_BITS,
    RESULT_FIELD,
    TRAP_FIELD,
    VXC_FIELD,
)
from interpreter.hlasm.element_size import ElementSize
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import Body, IrFunction
from interpreter.hlasm.opcodes.floating_point_support import emit_vector_exception
from interpreter.hlasm.opcodes.vector_fields import (
    FIFTH,
    FOURTH,
    SECOND,
    THIRD,
    ElementOp,
    assembled,
    below,
    element_bits,
    element_of,
    element_wise,
    m_field,
    ones,
    per_size,
    to_v1,
    vr_at,
)
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

SIXTH = 5
INTEGER_DIVIDE_CONTROL = 0b1000
EVEN_SHIFT = 0b1000
ODD_SHIFT = 0b0100
INTEGER_DIVIDE_CODE = 8
INDEX_SHIFT = 4
CARRY_IN = 1
WORD_BITS = 32
CHECKSUM_WORD = 1

B, H, F, G, Q = (
    ElementSize.BYTE,
    ElementSize.HALFWORD,
    ElementSize.WORD,
    ElementSize.DOUBLEWORD,
    ElementSize.QUADWORD,
)
EVERY_SIZE = frozenset({B, H, F, G, Q})
UP_TO_DOUBLEWORD = frozenset({B, H, F, G})
DIVIDE_SIZES = frozenset({F, G, Q})
QUADWORD_ONLY = frozenset({Q})
DOUBLEWORD_ONLY = frozenset({G})

type SizedOp = Callable[[ElementSize], ElementOp]
type Pair = tuple[Register, Register]
type PairOp = Callable[[HlasmEmitter, Pair, Pair, Register], Register]
type Value = Callable[[HlasmEmitter, Register], Register]
type Outcome = tuple[Register, Register]
type Division = Callable[[HlasmEmitter, Pair], Outcome]


def _binop(
    emitter: HlasmEmitter, kind: BinopKind, left: Register, right: int
) -> Register:
    return emitter.binop(kind, left, emitter.int_(right))


def _sum(emitter: HlasmEmitter, values: Sequence[Register]) -> Register:
    return reduce(
        lambda total, value: emitter.binop(BinopKind.ADD, total, value), values
    )


def _signed(bits: int) -> Value:
    def value(emitter: HlasmEmitter, element: Register) -> Register:
        sign = _binop(emitter, BinopKind.RSHIFT, element, bits - 1)
        return emitter.binop(
            BinopKind.SUB, element, _binop(emitter, BinopKind.MUL, sign, 1 << bits)
        )

    return value


def _logical(bits: int) -> Value:
    return lambda emitter, element: element


def _sized(arity: int, op_of: SizedOp) -> Callable[[ElementSize], StatementLowering]:
    return lambda size: element_wise(arity, op_of(size))(size)


def _added(size: ElementSize) -> ElementOp:
    return lambda emitter, pair: emitter.binop(BinopKind.ADD, pair[0], pair[1])


def _subtracted(size: ElementSize) -> ElementOp:
    return lambda emitter, pair: emitter.binop(BinopKind.SUB, pair[0], pair[1])


def _carry(size: ElementSize) -> ElementOp:
    return lambda emitter, pair: _binop(
        emitter,
        BinopKind.RSHIFT,
        emitter.binop(BinopKind.ADD, pair[0], pair[1]),
        element_bits(size),
    )


def _borrow_indication(size: ElementSize) -> ElementOp:
    return lambda emitter, pair: emitter.binop(
        BinopKind.SUB, emitter.int_(1), below(emitter, pair[0], pair[1])
    )


def _with_carry(complemented: bool, carry_out: bool) -> SizedOp:
    def op_of(size: ElementSize) -> ElementOp:
        def op(emitter: HlasmEmitter, triple: Sequence[Register]) -> Register:
            left, right, carry = triple
            addend = (
                _binop(emitter, BinopKind.BIT_XOR, right, ones(RESULT_BITS))
                if complemented
                else right
            )
            carried = _binop(emitter, BinopKind.BIT_AND, carry, CARRY_IN)
            total = _sum(emitter, [left, addend, carried])
            return (
                _binop(emitter, BinopKind.RSHIFT, total, RESULT_BITS)
                if carry_out
                else total
            )

        return op

    return op_of


def _average(signed: bool) -> SizedOp:
    def op_of(size: ElementSize) -> ElementOp:
        flip = 1 << (element_bits(size) - 1) if signed else 0

        def op(emitter: HlasmEmitter, pair: Sequence[Register]) -> Register:
            left, right = (_binop(emitter, BinopKind.BIT_XOR, v, flip) for v in pair)
            total = _binop(
                emitter, BinopKind.ADD, emitter.binop(BinopKind.ADD, left, right), 1
            )
            halved = _binop(emitter, BinopKind.RSHIFT, total, 1)
            return _binop(emitter, BinopKind.BIT_XOR, halved, flip)

        return op

    return op_of


def _product(
    emitter: HlasmEmitter, value: Value, left: Register, right: Register
) -> Register:
    return emitter.binop(BinopKind.MUL, value(emitter, left), value(emitter, right))


def _multiplied(
    value_of: Callable[[int], Value], high: bool, accumulate: bool
) -> SizedOp:
    def op_of(size: ElementSize) -> ElementOp:
        bits = element_bits(size)
        value = value_of(bits)

        def op(emitter: HlasmEmitter, sources: Sequence[Register]) -> Register:
            product = _product(emitter, value, sources[0], sources[1])
            total = (
                emitter.binop(BinopKind.ADD, product, value(emitter, sources[2]))
                if accumulate
                else product
            )
            return _binop(emitter, BinopKind.RSHIFT, total, bits) if high else total

        return op

    return op_of


def _zero(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    return emitter.int_(0)


def _pair(emitter: HlasmEmitter, value: Register, size: ElementSize, at: int) -> Pair:
    return (
        element_of(emitter, value, size, 2 * at),
        element_of(emitter, value, size, 2 * at + 1),
    )


def _double_wide(
    accumulate: bool, op_of: Callable[[ElementSize], PairOp]
) -> Callable[[ElementSize], StatementLowering]:
    addend_of = vr_at(FOURTH) if accumulate else _zero

    def build(size: ElementSize) -> StatementLowering:
        wide = ElementSize(size.value + 1)
        op = op_of(size)

        def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
            left = vr_at(SECOND)(emitter, statement)
            right = vr_at(THIRD)(emitter, statement)
            addend = addend_of(emitter, statement)
            pieces = [
                op(
                    emitter,
                    _pair(emitter, left, size, at),
                    _pair(emitter, right, size, at),
                    element_of(emitter, addend, wide, at),
                )
                for at in range(wide.count)
            ]
            to_v1(emitter, statement, assembled(emitter, wide, pieces))

        return lower

    return build


def _one_side(
    value_of: Callable[[int], Value], odd: int
) -> Callable[[ElementSize], PairOp]:
    def op_of(size: ElementSize) -> PairOp:
        value = value_of(element_bits(size))
        return lambda emitter, left, right, addend: emitter.binop(
            BinopKind.ADD, _product(emitter, value, left[odd], right[odd]), addend
        )

    return op_of


def _shifted(emitter: HlasmEmitter, value: Register, shift: bool) -> Register:
    return _binop(emitter, BinopKind.LSHIFT, value, 1) if shift else value


def _multiply_sum(size: ElementSize) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        flags = m_field(statement, SIXTH)
        logical = _logical(element_bits(size))

        def op(
            emitter: HlasmEmitter, left: Pair, right: Pair, addend: Register
        ) -> Register:
            even = _product(emitter, logical, left[0], right[0])
            odd = _product(emitter, logical, left[1], right[1])
            return _sum(
                emitter,
                [
                    _shifted(emitter, even, bool(flags & EVEN_SHIFT)),
                    _shifted(emitter, odd, bool(flags & ODD_SHIFT)),
                    addend,
                ],
            )

        _double_wide(True, lambda _: op)(size)(emitter, statement)

    return lower


def _carryless(
    emitter: HlasmEmitter, left: Register, right: Register, bits: int
) -> Register:
    terms = [
        emitter.binop(
            BinopKind.MUL,
            _binop(emitter, BinopKind.LSHIFT, left, k),
            _binop(
                emitter,
                BinopKind.BIT_AND,
                _binop(emitter, BinopKind.RSHIFT, right, k),
                1,
            ),
        )
        for k in range(bits)
    ]
    return reduce(
        lambda total, term: emitter.binop(BinopKind.BIT_XOR, total, term), terms
    )


def _galois(size: ElementSize) -> PairOp:
    bits = element_bits(size)

    def op(
        emitter: HlasmEmitter, left: Pair, right: Pair, addend: Register
    ) -> Register:
        products = [_carryless(emitter, left[k], right[k], bits) for k in (0, 1)]
        return reduce(
            lambda total, term: emitter.binop(BinopKind.BIT_XOR, total, term),
            [*products, addend],
        )

    return op


def _folded_add(emitter: HlasmEmitter, total: Register, word: Register) -> Register:
    added = emitter.binop(BinopKind.ADD, total, word)
    low = _binop(emitter, BinopKind.BIT_AND, added, ones(WORD_BITS))
    return emitter.binop(
        BinopKind.ADD, low, _binop(emitter, BinopKind.RSHIFT, added, WORD_BITS)
    )


def _checksum(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    words = vr_at(SECOND)(emitter, statement)
    start = element_of(emitter, vr_at(THIRD)(emitter, statement), F, CHECKSUM_WORD)
    total = reduce(
        lambda total, at: _folded_add(
            emitter, total, element_of(emitter, words, F, at)
        ),
        range(F.count),
        start,
    )
    pieces = [
        total if at == CHECKSUM_WORD else emitter.int_(0) for at in range(F.count)
    ]
    to_v1(emitter, statement, assembled(emitter, F, pieces))


def _sum_across(lane: ElementSize) -> Callable[[ElementSize], StatementLowering]:
    def build(size: ElementSize) -> StatementLowering:
        parts = lane.width // size.width

        def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
            summed = vr_at(SECOND)(emitter, statement)
            added = vr_at(THIRD)(emitter, statement)
            pieces = [
                _sum(
                    emitter,
                    [
                        *(
                            element_of(emitter, summed, size, j * parts + t)
                            for t in range(parts)
                        ),
                        element_of(emitter, added, size, j * parts + parts - 1),
                    ],
                )
                for j in range(lane.count)
            ]
            to_v1(emitter, statement, assembled(emitter, lane, pieces))

        return lower

    return build


def _is(emitter: HlasmEmitter, value: Register, constant: int) -> Register:
    differs = below(
        emitter, emitter.int_(0), _binop(emitter, BinopKind.BIT_XOR, value, constant)
    )
    return emitter.binop(BinopKind.SUB, emitter.int_(1), differs)


def _sign_factor(
    emitter: HlasmEmitter, value: Register, bits: int, signed: bool
) -> Register:
    if not signed:
        return emitter.int_(1)
    negative = _binop(emitter, BinopKind.RSHIFT, value, bits - 1)
    return emitter.binop(
        BinopKind.SUB, emitter.int_(1), _binop(emitter, BinopKind.MUL, negative, 2)
    )


def _overflow(emitter: HlasmEmitter, pair: Pair, bits: int) -> Register:
    dividend, divisor = pair
    return emitter.binop(
        BinopKind.MUL,
        _is(emitter, dividend, 1 << (bits - 1)),
        _is(emitter, divisor, ones(bits)),
    )


def _no_overflow(emitter: HlasmEmitter, pair: Pair, bits: int) -> Register:
    return emitter.int_(0)


def _quotient(emitter: HlasmEmitter, magnitudes: Pair, signs: Pair) -> Register:
    kept = emitter.binop(BinopKind.FLOOR_DIV, *magnitudes)
    return emitter.binop(BinopKind.MUL, kept, emitter.binop(BinopKind.MUL, *signs))


def _remainder(emitter: HlasmEmitter, magnitudes: Pair, signs: Pair) -> Register:
    kept = emitter.binop(BinopKind.MOD, *magnitudes)
    return emitter.binop(BinopKind.MUL, kept, signs[0])


def _division(bits: int, signed: bool, remainder: bool) -> Division:
    value = _signed(bits) if signed else _logical(bits)
    overflow_of = _no_overflow if remainder or not signed else _overflow
    kept_of = _remainder if remainder else _quotient

    def divided(emitter: HlasmEmitter, pair: Pair) -> Outcome:
        dividend, divisor = pair
        zero = _is(emitter, divisor, 0)
        fault = emitter.binop(BinopKind.BIT_OR, zero, overflow_of(emitter, pair, bits))
        signs = (
            _sign_factor(emitter, dividend, bits, signed),
            _sign_factor(emitter, divisor, bits, signed),
        )
        nonzero = emitter.binop(BinopKind.ADD, divisor, zero)
        magnitudes = (
            emitter.binop(BinopKind.MUL, value(emitter, dividend), signs[0]),
            emitter.binop(BinopKind.MUL, value(emitter, nonzero), signs[1]),
        )
        valid = emitter.binop(BinopKind.SUB, emitter.int_(1), fault)
        return (
            emitter.binop(BinopKind.MUL, kept_of(emitter, magnitudes, signs), valid),
            fault,
        )

    return divided


def _trapped(
    emitter: HlasmEmitter, result: Register, outcomes: Sequence[Outcome]
) -> Register:
    vxc = reduce(
        lambda later, at: pick(
            emitter,
            outcomes[at][1],
            emitter.int_((at << INDEX_SHIFT) | INTEGER_DIVIDE_CODE),
            later,
        ),
        reversed(range(len(outcomes))),
        emitter.int_(0),
    )
    trap = reduce(
        lambda any_fault, outcome: emitter.binop(
            BinopKind.BIT_OR, any_fault, outcome[1]
        ),
        outcomes,
        emitter.int_(0),
    )
    return combined_bits(
        emitter,
        [result, VXC_FIELD.placed(emitter, vxc), TRAP_FIELD.placed(emitter, trap)],
    )


def _divide_body(size: ElementSize, division: Division, masked: bool) -> Body:
    def body(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
        left, right = parameters
        outcomes = [
            division(
                emitter,
                (
                    element_of(emitter, left, size, at),
                    element_of(emitter, right, size, at),
                ),
            )
            for at in range(size.count)
        ]
        result = assembled(emitter, size, [value for value, _ in outcomes])
        return result if masked else _trapped(emitter, result, outcomes)

    return body


def _divide_functions(
    kind: str, signed: bool, remainder: bool
) -> Mapping[tuple[ElementSize, bool], IrFunction]:
    return {
        (size, masked): IrFunction(
            f"__hlasm_vector_{kind}_{size.name.lower()}{'_masked' if masked else ''}",
            2,
            _divide_body(
                size, _division(element_bits(size), signed, remainder), masked
            ),
        )
        for size in DIVIDE_SIZES
        for masked in (False, True)
    }


def _raised(emitter: HlasmEmitter, returned: Register, masked: bool) -> None:
    if masked:
        return
    emit_when(
        emitter,
        TRAP_FIELD.of(emitter, returned),
        lambda: emit_vector_exception(emitter, VXC_FIELD.of(emitter, returned)),
    )


def _divide(
    functions: Mapping[tuple[ElementSize, bool], IrFunction],
) -> Callable[[ElementSize], StatementLowering]:
    def build(size: ElementSize) -> StatementLowering:
        def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
            masked = bool(m_field(statement, FIFTH) & INTEGER_DIVIDE_CONTROL)
            sources = (
                vr_at(SECOND)(emitter, statement),
                vr_at(THIRD)(emitter, statement),
            )
            returned = functions[(size, masked)].call(emitter, sources)
            _raised(emitter, returned, masked)
            to_v1(emitter, statement, RESULT_FIELD.of(emitter, returned))

        return lower

    return build


DIVIDE = _divide_functions("divide", signed=True, remainder=False)
DIVIDE_LOGICAL = _divide_functions("divide_logical", signed=False, remainder=False)
REMAINDER = _divide_functions("remainder", signed=True, remainder=True)
REMAINDER_LOGICAL = _divide_functions("remainder_logical", signed=False, remainder=True)

VECTOR_INTEGER_ARITHMETIC_LOWERINGS: Mapping[str, StatementLowering] = {
    "VA": per_size(FOURTH, EVERY_SIZE, _sized(2, _added)),
    "VACC": per_size(FOURTH, EVERY_SIZE, _sized(2, _carry)),
    "VAC": per_size(FIFTH, QUADWORD_ONLY, _sized(3, _with_carry(False, False))),
    "VACCC": per_size(FIFTH, QUADWORD_ONLY, _sized(3, _with_carry(False, True))),
    "VS": per_size(FOURTH, EVERY_SIZE, _sized(2, _subtracted)),
    "VSCBI": per_size(FOURTH, EVERY_SIZE, _sized(2, _borrow_indication)),
    "VSBI": per_size(FIFTH, QUADWORD_ONLY, _sized(3, _with_carry(True, False))),
    "VSBCBI": per_size(FIFTH, QUADWORD_ONLY, _sized(3, _with_carry(True, True))),
    "VAVG": per_size(FOURTH, EVERY_SIZE, _sized(2, _average(signed=True))),
    "VAVGL": per_size(FOURTH, EVERY_SIZE, _sized(2, _average(signed=False))),
    "VD": per_size(FOURTH, DIVIDE_SIZES, _divide(DIVIDE)),
    "VDL": per_size(FOURTH, DIVIDE_SIZES, _divide(DIVIDE_LOGICAL)),
    "VR": per_size(FOURTH, DIVIDE_SIZES, _divide(REMAINDER)),
    "VRL": per_size(FOURTH, DIVIDE_SIZES, _divide(REMAINDER_LOGICAL)),
    "VML": per_size(FOURTH, EVERY_SIZE, _sized(2, _multiplied(_logical, False, False))),
    "VMH": per_size(FOURTH, EVERY_SIZE, _sized(2, _multiplied(_signed, True, False))),
    "VMLH": per_size(FOURTH, EVERY_SIZE, _sized(2, _multiplied(_logical, True, False))),
    "VMAL": per_size(FIFTH, EVERY_SIZE, _sized(3, _multiplied(_logical, False, True))),
    "VMAH": per_size(FIFTH, EVERY_SIZE, _sized(3, _multiplied(_signed, True, True))),
    "VMALH": per_size(FIFTH, EVERY_SIZE, _sized(3, _multiplied(_logical, True, True))),
    "VME": per_size(
        FOURTH, UP_TO_DOUBLEWORD, _double_wide(False, _one_side(_signed, 0))
    ),
    "VMLE": per_size(
        FOURTH, UP_TO_DOUBLEWORD, _double_wide(False, _one_side(_logical, 0))
    ),
    "VMO": per_size(
        FOURTH, UP_TO_DOUBLEWORD, _double_wide(False, _one_side(_signed, 1))
    ),
    "VMLO": per_size(
        FOURTH, UP_TO_DOUBLEWORD, _double_wide(False, _one_side(_logical, 1))
    ),
    "VMAE": per_size(
        FIFTH, UP_TO_DOUBLEWORD, _double_wide(True, _one_side(_signed, 0))
    ),
    "VMALE": per_size(
        FIFTH, UP_TO_DOUBLEWORD, _double_wide(True, _one_side(_logical, 0))
    ),
    "VMAO": per_size(
        FIFTH, UP_TO_DOUBLEWORD, _double_wide(True, _one_side(_signed, 1))
    ),
    "VMALO": per_size(
        FIFTH, UP_TO_DOUBLEWORD, _double_wide(True, _one_side(_logical, 1))
    ),
    "VMSL": per_size(FIFTH, DOUBLEWORD_ONLY, _multiply_sum),
    "VGFM": per_size(FOURTH, UP_TO_DOUBLEWORD, _double_wide(False, _galois)),
    "VGFMA": per_size(FIFTH, UP_TO_DOUBLEWORD, _double_wide(True, _galois)),
    "VCKSM": _checksum,
    "VSUM": per_size(FOURTH, frozenset({B, H}), _sum_across(F)),
    "VSUMG": per_size(FOURTH, frozenset({H, F}), _sum_across(G)),
    "VSUMQ": per_size(FOURTH, frozenset({F, G}), _sum_across(Q)),
}
