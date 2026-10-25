# pyright: standard
"""Vector string instructions: VFAE, VFEE, VFENE, VSTRC, VISTR and VSTRS as element functions per element size and IN/RT/ZS combination, built from per-element zero, equal and below flags held one bit per element in the whole register; the index result is a byte index in byte 7 of V1 and the CC is set with CS (always for VSTRS)."""

from collections.abc import Callable, Mapping, Sequence
from functools import reduce

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.conditional import pick
from interpreter.hlasm.element_return_field import CC_FIELD, RESULT_BITS, RESULT_FIELD
from interpreter.hlasm.element_size import ElementSize
from interpreter.hlasm.hlasm_constants import BITS_PER_BYTE, VECTOR_REGISTER_BYTES
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import Body, IrFunction
from interpreter.hlasm.opcodes.vector_fields import (
    FIFTH,
    FOURTH,
    SECOND,
    THIRD,
    below,
    element_bits,
    element_of,
    m_field,
    ones,
    per_size,
    replication,
    to_v1,
    vr_at,
    zero_bits_checked,
)
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

SIXTH = 5
INVERT = 0b1000
RESULT_TYPE = 0b0100
ZERO_SEARCH = 0b0010
CONDITION_CODE_SET = 0b0001
FIND_FLAGS = INVERT | RESULT_TYPE | ZERO_SEARCH
INDEX_SHIFT = RESULT_BITS - 8 * BITS_PER_BYTE
ALL_ONES = ones(RESULT_BITS)
EQUAL_BIT, LOW_BIT, HIGH_BIT = 0, 1, 2

B, H, F = ElementSize.BYTE, ElementSize.HALFWORD, ElementSize.WORD
STRING_SIZES = frozenset({B, H, F})

type Hits = Callable[[HlasmEmitter, Sequence[Register], ElementSize], Register]
type Outcome = Callable[
    [HlasmEmitter, Sequence[Register], ElementSize, Register, Register, Register],
    Register,
]
type Functions = Mapping[tuple[ElementSize, int], IrFunction]
type Bounds = tuple[Register, Register, Register]
type Found = tuple[Register, Register]


def _op(emitter: HlasmEmitter, kind: BinopKind, left: Register, right: int) -> Register:
    return emitter.binop(kind, left, emitter.int_(right))


def _not(emitter: HlasmEmitter, value: Register) -> Register:
    return _op(emitter, BinopKind.BIT_XOR, value, ALL_ONES)


def _flags(emitter: HlasmEmitter, value: Register, size: ElementSize) -> Register:
    moved = _op(emitter, BinopKind.RSHIFT, value, element_bits(size) - 1)
    return _op(emitter, BinopKind.BIT_AND, moved, replication(size))


def _nonzero(emitter: HlasmEmitter, value: Register, size: ElementSize) -> Register:
    low = replication(size) * ones(element_bits(size) - 1)
    kept = _op(emitter, BinopKind.BIT_AND, value, low)
    carried = _op(emitter, BinopKind.ADD, kept, low)
    return _flags(emitter, emitter.binop(BinopKind.BIT_OR, carried, value), size)


def _zero(emitter: HlasmEmitter, value: Register, size: ElementSize) -> Register:
    return _op(
        emitter, BinopKind.BIT_XOR, _nonzero(emitter, value, size), replication(size)
    )


def _equal(
    emitter: HlasmEmitter, left: Register, right: Register, size: ElementSize
) -> Register:
    return _zero(emitter, emitter.binop(BinopKind.BIT_XOR, left, right), size)


def _below(
    emitter: HlasmEmitter, left: Register, right: Register, size: ElementSize
) -> Register:
    top = element_bits(size) - 1
    raised = _op(emitter, BinopKind.BIT_OR, left, replication(size) << top)
    lowered = _op(emitter, BinopKind.BIT_AND, right, replication(size) * ones(top))
    difference = emitter.binop(BinopKind.SUB, raised, lowered)
    clear = emitter.binop(BinopKind.BIT_AND, _not(emitter, left), right)
    differing = emitter.binop(BinopKind.BIT_XOR, left, right)
    borrowed = _not(emitter, emitter.binop(BinopKind.BIT_OR, differing, difference))
    return _flags(emitter, emitter.binop(BinopKind.BIT_OR, clear, borrowed), size)


def _smeared(emitter: HlasmEmitter, flags: Register, size: ElementSize) -> Register:
    steps = [1 << k for k in range(size.count.bit_length() - 1)]
    return reduce(
        lambda total, step: emitter.binop(
            BinopKind.BIT_OR,
            total,
            _op(emitter, BinopKind.RSHIFT, total, step * element_bits(size)),
        ),
        steps,
        flags,
    )


def _leftmost(
    emitter: HlasmEmitter, flags: Register, size: ElementSize
) -> tuple[Register, Register]:
    bits = element_bits(size)
    smeared = _smeared(emitter, flags, size)
    shifted = _op(emitter, BinopKind.RSHIFT, smeared, bits)
    leading = emitter.binop(BinopKind.BIT_XOR, smeared, shifted)
    summed = _op(emitter, BinopKind.MUL, smeared, replication(size))
    counted = _op(
        emitter,
        BinopKind.BIT_AND,
        _op(emitter, BinopKind.RSHIFT, summed, RESULT_BITS - bits),
        ones(bits),
    )
    index = emitter.binop(BinopKind.SUB, emitter.int_(size.count), counted)
    return _op(emitter, BinopKind.MUL, index, size.width), leading


def _any(emitter: HlasmEmitter, value: Register) -> Register:
    return below(emitter, emitter.int_(0), value)


def _at(emitter: HlasmEmitter, flags: Register, leading: Register) -> Register:
    return _any(emitter, emitter.binop(BinopKind.BIT_AND, flags, leading))


def _negated(emitter: HlasmEmitter, flag: Register) -> Register:
    return emitter.binop(BinopKind.SUB, emitter.int_(1), flag)


def _filled(emitter: HlasmEmitter, flags: Register, size: ElementSize) -> Register:
    return _op(emitter, BinopKind.MUL, flags, ones(element_bits(size)))


def _returned(emitter: HlasmEmitter, result: Register, cc: Register) -> Register:
    return emitter.binop(BinopKind.BIT_OR, result, CC_FIELD.placed(emitter, cc))


def _indexed(emitter: HlasmEmitter, index: Register) -> Register:
    return _op(emitter, BinopKind.LSHIFT, index, INDEX_SHIFT)


def _found_first(
    emitter: HlasmEmitter,
    sources: Sequence[Register],
    size: ElementSize,
    found: Register,
    zeros: Register,
    leading: Register,
) -> Register:
    alone = emitter.binop(
        BinopKind.MUL,
        _at(emitter, found, leading),
        _negated(emitter, _at(emitter, zeros, leading)),
    )
    unzeroed = emitter.binop(
        BinopKind.SUB,
        emitter.int_(3),
        _op(emitter, BinopKind.MUL, _any(emitter, found), 2),
    )
    doubled = _op(emitter, BinopKind.MUL, alone, 2)
    return pick(emitter, _any(emitter, zeros), doubled, unzeroed)


def _mismatch_order(
    emitter: HlasmEmitter,
    sources: Sequence[Register],
    size: ElementSize,
    found: Register,
    zeros: Register,
    leading: Register,
) -> Register:
    lower = _at(emitter, _below(emitter, sources[0], sources[1], size), leading)
    unequal = emitter.binop(BinopKind.SUB, emitter.int_(2), lower)
    zeroed = _op(emitter, BinopKind.MUL, _at(emitter, zeros, leading), 3)
    equal = emitter.binop(BinopKind.SUB, emitter.int_(3), zeroed)
    return pick(emitter, _at(emitter, found, leading), unequal, equal)


def _find_body(size: ElementSize, flags: int, hits: Hits, outcome: Outcome) -> Body:
    def body(emitter: HlasmEmitter, sources: Sequence[Register]) -> Register:
        raw = hits(emitter, sources, size)
        found = (
            _op(emitter, BinopKind.BIT_XOR, raw, replication(size))
            if flags & INVERT
            else raw
        )
        zeros = (
            _zero(emitter, sources[0], size) if flags & ZERO_SEARCH else emitter.int_(0)
        )
        either = emitter.binop(BinopKind.BIT_OR, found, zeros)
        index, leading = _leftmost(emitter, either, size)
        result = (
            _filled(emitter, found, size)
            if flags & RESULT_TYPE
            else _indexed(emitter, index)
        )
        cc = outcome(emitter, sources, size, found, zeros, leading)
        return _returned(emitter, result, cc)

    return body


def _equal_any(
    emitter: HlasmEmitter, sources: Sequence[Register], size: ElementSize
) -> Register:
    searched, wanted = sources
    matches = [
        _equal(
            emitter,
            searched,
            _op(
                emitter,
                BinopKind.MUL,
                element_of(emitter, wanted, size, at),
                replication(size),
            ),
            size,
        )
        for at in range(size.count)
    ]
    return reduce(
        lambda total, one: emitter.binop(BinopKind.BIT_OR, total, one), matches
    )


def _equal_each(
    emitter: HlasmEmitter, sources: Sequence[Register], size: ElementSize
) -> Register:
    return _equal(emitter, sources[0], sources[1], size)


def _unequal_each(
    emitter: HlasmEmitter, sources: Sequence[Register], size: ElementSize
) -> Register:
    differing = emitter.binop(BinopKind.BIT_XOR, sources[0], sources[1])
    return _nonzero(emitter, differing, size)


def _control(
    emitter: HlasmEmitter, control: Register, size: ElementSize, bit: int
) -> Register:
    moved = _op(emitter, BinopKind.RSHIFT, control, element_bits(size) - 1 - bit)
    chosen = _op(emitter, BinopKind.BIT_AND, moved, 1)
    return _op(emitter, BinopKind.MUL, chosen, replication(size))


def _limit_holds(
    emitter: HlasmEmitter, sources: Sequence[Register], size: ElementSize, at: int
) -> Register:
    searched, limits, controls = sources
    limit = _op(
        emitter,
        BinopKind.MUL,
        element_of(emitter, limits, size, at),
        replication(size),
    )
    control = element_of(emitter, controls, size, at)
    equal = _equal(emitter, searched, limit, size)
    lower = _below(emitter, searched, limit, size)
    higher = _op(
        emitter,
        BinopKind.BIT_XOR,
        emitter.binop(BinopKind.BIT_OR, equal, lower),
        replication(size),
    )
    held = [
        emitter.binop(BinopKind.BIT_AND, outcome, _control(emitter, control, size, bit))
        for outcome, bit in ((equal, EQUAL_BIT), (lower, LOW_BIT), (higher, HIGH_BIT))
    ]
    return reduce(lambda total, one: emitter.binop(BinopKind.BIT_OR, total, one), held)


def _in_range(
    emitter: HlasmEmitter, sources: Sequence[Register], size: ElementSize
) -> Register:
    ranges = [
        emitter.binop(
            BinopKind.BIT_AND,
            _limit_holds(emitter, sources, size, at),
            _limit_holds(emitter, sources, size, at + 1),
        )
        for at in range(0, size.count, 2)
    ]
    return reduce(
        lambda total, one: emitter.binop(BinopKind.BIT_OR, total, one), ranges
    )


def _isolate_body(size: ElementSize, flags: int) -> Body:
    def body(emitter: HlasmEmitter, sources: Sequence[Register]) -> Register:
        zeros = _zero(emitter, sources[0], size)
        cleared = _filled(emitter, _smeared(emitter, zeros, size), size)
        kept = emitter.binop(BinopKind.BIT_AND, sources[0], _not(emitter, cleared))
        found = _op(emitter, BinopKind.MUL, _any(emitter, zeros), 3)
        return _returned(
            emitter, kept, emitter.binop(BinopKind.SUB, emitter.int_(3), found)
        )

    return body


def _first_zero(
    emitter: HlasmEmitter, value: Register, size: ElementSize
) -> tuple[Register, Register]:
    zeros = _zero(emitter, value, size)
    return _leftmost(emitter, zeros, size)[0], _any(emitter, zeros)


def _search_bounds(
    emitter: HlasmEmitter, sources: Sequence[Register], size: ElementSize, flags: int
) -> Bounds:
    string, substring, lengths = sources
    given = _op(
        emitter,
        BinopKind.BIT_AND,
        _op(emitter, BinopKind.RSHIFT, lengths, INDEX_SHIFT),
        ones(BITS_PER_BYTE),
    )
    if not flags & ZERO_SEARCH:
        return given, emitter.int_(VECTOR_REGISTER_BYTES), emitter.int_(0)
    terminated, _ = _first_zero(emitter, substring, size)
    length = pick(emitter, below(emitter, terminated, given), terminated, given)
    end, ended = _first_zero(emitter, string, size)
    return length, end, ended


def _window(emitter: HlasmEmitter, length: Register) -> Register:
    bits = _op(emitter, BinopKind.MUL, length, BITS_PER_BYTE)
    return _not(emitter, emitter.binop(BinopKind.RSHIFT, emitter.int_(ALL_ONES), bits))


def _differing(
    emitter: HlasmEmitter, string: Register, substring: Register, at: int
) -> Register:
    moved = _op(emitter, BinopKind.LSHIFT, string, BITS_PER_BYTE * at)
    aligned = _op(emitter, BinopKind.BIT_AND, moved, ALL_ONES)
    return emitter.binop(BinopKind.BIT_XOR, aligned, substring)


def _clear(emitter: HlasmEmitter, value: Register, mask: Register) -> Register:
    return _negated(
        emitter, _any(emitter, emitter.binop(BinopKind.BIT_AND, value, mask))
    )


def _found_at(
    emitter: HlasmEmitter,
    sources: Sequence[Register],
    bounds: Bounds,
    window: Register,
    at: int,
) -> Found:
    length, end, ended = bounds
    differing = _differing(emitter, sources[0], sources[1], at)
    reach = _op(emitter, BinopKind.ADD, length, at)
    inside = _negated(emitter, below(emitter, end, reach))
    full = emitter.binop(BinopKind.MUL, _clear(emitter, differing, window), inside)
    past = below(emitter, emitter.int_(VECTOR_REGISTER_BYTES), reach)
    open_ended = emitter.binop(BinopKind.MUL, past, _negated(emitter, ended))
    tail = emitter.int_(ALL_ONES ^ ones(BITS_PER_BYTE * at))
    partial = emitter.binop(BinopKind.MUL, _clear(emitter, differing, tail), open_ended)
    return full, emitter.binop(BinopKind.BIT_OR, full, partial)


def _earlier(emitter: HlasmEmitter, found: Found, later: Found, at: int) -> Found:
    full, hit = found
    index, was_full = later
    return (
        pick(emitter, hit, emitter.int_(at), index),
        pick(emitter, hit, full, was_full),
    )


def _search_result(
    emitter: HlasmEmitter, index: Register, full: Register, ended: Register
) -> Register:
    hit = below(emitter, index, emitter.int_(VECTOR_REGISTER_BYTES))
    matched = emitter.binop(BinopKind.SUB, emitter.int_(3), full)
    cc = pick(emitter, hit, matched, ended)
    return _returned(emitter, _indexed(emitter, index), cc)


def _search_body(size: ElementSize, flags: int) -> Body:
    def body(emitter: HlasmEmitter, sources: Sequence[Register]) -> Register:
        bounds = _search_bounds(emitter, sources, size, flags)
        window = _window(emitter, bounds[0])
        index, full = reduce(
            lambda later, at: _earlier(
                emitter, _found_at(emitter, sources, bounds, window, at), later, at
            ),
            reversed(range(0, VECTOR_REGISTER_BYTES, size.width)),
            (emitter.int_(VECTOR_REGISTER_BYTES), emitter.int_(0)),
        )
        return _search_result(emitter, index, full, bounds[2])

    return body


def _functions(
    kind: str, arity: int, allowed: int, body: Callable[[ElementSize, int], Body]
) -> Functions:
    return {
        (size, flags): IrFunction(
            f"__hlasm_vector_{kind}_{size.name.lower()}_{flags}",
            arity,
            body(size, flags),
        )
        for size in STRING_SIZES
        for flags in range(allowed + 1)
        if flags & ~allowed == 0
    }


def _finder(hits: Hits, outcome: Outcome) -> Callable[[ElementSize, int], Body]:
    return lambda size, flags: _find_body(size, flags, hits, outcome)


def _read(
    emitter: HlasmEmitter, statement: MachineStatement, arity: int
) -> list[Register]:
    return [vr_at(SECOND + k)(emitter, statement) for k in range(arity)]


def _cc_when_set(emitter: HlasmEmitter, returned: Register, flags: int) -> None:
    if not flags & CONDITION_CODE_SET:
        return
    emitter.set_cc(CC_FIELD.of(emitter, returned))


def _called(
    functions: Functions, arity: int, field: int, forced: int
) -> Callable[[ElementSize], StatementLowering]:
    def build(size: ElementSize) -> StatementLowering:
        def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
            flags = m_field(statement, field) | forced
            function = functions[(size, flags & ~CONDITION_CODE_SET)]
            returned = function.call(emitter, _read(emitter, statement, arity))
            to_v1(emitter, statement, RESULT_FIELD.of(emitter, returned))
            _cc_when_set(emitter, returned, flags)

        return lower

    return build


FIND_ANY = _functions("find_any", 2, FIND_FLAGS, _finder(_equal_any, _found_first))
FIND_EQUAL = _functions(
    "find_equal", 2, ZERO_SEARCH, _finder(_equal_each, _found_first)
)
FIND_UNEQUAL = _functions(
    "find_unequal", 2, ZERO_SEARCH, _finder(_unequal_each, _mismatch_order)
)
RANGE = _functions("range", 3, FIND_FLAGS, _finder(_in_range, _found_first))
ISOLATE = _functions("isolate", 1, 0, _isolate_body)
SEARCH = _functions("search", 3, ZERO_SEARCH, _search_body)

VECTOR_STRING_LOWERINGS: Mapping[str, StatementLowering] = {
    "VFAE": per_size(FOURTH, STRING_SIZES, _called(FIND_ANY, 2, FIFTH, 0)),
    "VFEE": zero_bits_checked(
        FIFTH,
        INVERT | RESULT_TYPE,
        per_size(FOURTH, STRING_SIZES, _called(FIND_EQUAL, 2, FIFTH, 0)),
    ),
    "VFENE": zero_bits_checked(
        FIFTH,
        INVERT | RESULT_TYPE,
        per_size(FOURTH, STRING_SIZES, _called(FIND_UNEQUAL, 2, FIFTH, 0)),
    ),
    "VISTR": zero_bits_checked(
        FOURTH,
        FIND_FLAGS,
        per_size(THIRD, STRING_SIZES, _called(ISOLATE, 1, FOURTH, 0)),
    ),
    "VSTRC": per_size(FIFTH, STRING_SIZES, _called(RANGE, 3, SIXTH, 0)),
    "VSTRS": zero_bits_checked(
        SIXTH,
        INVERT | RESULT_TYPE | CONDITION_CODE_SET,
        per_size(FIFTH, STRING_SIZES, _called(SEARCH, 3, SIXTH, CONDITION_CODE_SET)),
    ),
}
