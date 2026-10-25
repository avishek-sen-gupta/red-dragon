# pyright: standard
"""Vector support loads and stores: whole registers and register ranges, elements by static index, immediates, replicated and zero-extended elements, run-time-length and block-bounded loads, gather and scatter, and the byte- and element-reversed forms."""

from collections.abc import Callable, Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import copy_byte, emit_byte_loop
from interpreter.hlasm.data_movement import (
    Sink,
    Source,
    Transform,
    from_storage,
    gather_bytes,
    move,
    reversed_bytes,
    signed_immediate,
    storage_address,
    storage_address_at,
    to_storage,
)
from interpreter.hlasm.effective_address import vector_indexed_address
from interpreter.hlasm.element_placement import ElementPlacement
from interpreter.hlasm.element_size import ElementSize
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    DOUBLEWORD_BITS,
    HALFWORD_BITS,
    VECTOR_REGISTER_BYTES,
    VECTOR_REGISTERS_VAR,
    WORD_BITS,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_registers import smaller
from interpreter.hlasm.opcodes.fp_forms import checked
from interpreter.hlasm.opcodes.miscellaneous import (
    LARGEST_BOUNDARY_CODE,
    SMALLEST_BLOCK,
    block_count,
)
from interpreter.hlasm.opcodes.vector_fields import (
    V1,
    element_index_checked,
    m_field,
    per_size,
    replicated,
    to_v1,
    vr_at,
)
from interpreter.hlasm.operands import (
    reg_operand,
    vec_reg_operand,
    vector_indexed_operand,
)
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.vector_elements import load_element, store_element
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

SECOND_OPERAND = 1
M3 = 2
RANGE_END = 1
RANGE_STORAGE = 2
LENGTH_REGISTER = 1
LENGTH_STORAGE = 2
MOST_REGISTERS = 16
LAST_BYTE = VECTOR_REGISTER_BYTES - 1
LEFT_ALIGNED_WORD = 6
LEFT_ALIGNED_SHIFT = BITS_PER_BYTE * VECTOR_REGISTER_BYTES - WORD_BITS

B, H, F, G, Q = (
    ElementSize.BYTE,
    ElementSize.HALFWORD,
    ElementSize.WORD,
    ElementSize.DOUBLEWORD,
    ElementSize.QUADWORD,
)
REPLICATED_SIZES = frozenset({B, H, F, G})
BYTE_REVERSED_SIZES = frozenset({H, F, G, Q})
ELEMENT_SIZES_FROM_HALFWORD = frozenset({H, F, G})

type RegionAt = tuple[Register, Register]
type ByteCopy = Callable[[HlasmEmitter, Register, RegionAt, int], None]


def _element(size: ElementSize) -> Source:
    return lambda emitter, statement: load_element(
        emitter, vec_reg_operand(statement, V1), size, m_field(statement, M3)
    )


def _to_element(size: ElementSize) -> Sink:
    def store(
        emitter: HlasmEmitter, statement: MachineStatement, value: Register
    ) -> None:
        store_element(
            emitter, vec_reg_operand(statement, V1), size, m_field(statement, M3), value
        )

    return store


def _shifted_left(bits: int) -> Transform:
    return lambda emitter, value: emitter.binop(
        BinopKind.LSHIFT, value, emitter.int_(bits)
    )


def _permuted(target: Callable[[int], int]) -> Transform:
    moves = tuple((LAST_BYTE - b, LAST_BYTE - target(b)) for b in range(LAST_BYTE + 1))
    return lambda emitter, value: gather_bytes(emitter, value, moves)


def _bytes_reversed(size: ElementSize) -> Transform:
    width = size.width
    return _permuted(lambda b: b - b % width + width - 1 - b % width)


def _elements_reversed(size: ElementSize) -> Transform:
    width = size.width
    return _permuted(lambda b: (size.count - 1 - b // width) * width + b % width)


def _whole(
    sizes: frozenset[ElementSize], build: Callable[[ElementSize], StatementLowering]
) -> StatementLowering:
    return per_size(M3, sizes, build)


def _coded(
    placements: Mapping[int, ElementPlacement],
    build: Callable[[ElementPlacement], StatementLowering],
) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        build(placements[m_field(statement, M3)])(emitter, statement)

    return checked(lambda statement: m_field(statement, M3) not in placements, lower)


def _zero_extended(sizes: frozenset[ElementSize]) -> Mapping[int, ElementPlacement]:
    return {
        **{size.value: ElementPlacement(size.width, DOUBLEWORD_BITS) for size in sizes},
        LEFT_ALIGNED_WORD: ElementPlacement(WORD_BYTES, LEFT_ALIGNED_SHIFT),
    }


def _load_element(
    size: ElementSize, transforms: Sequence[Transform]
) -> StatementLowering:
    return element_index_checked(
        M3, size, move(from_storage(size.width), transforms, _to_element(size))
    )


def _store_element(
    size: ElementSize, transforms: Sequence[Transform]
) -> StatementLowering:
    return element_index_checked(
        M3, size, move(_element(size), transforms, to_storage(size.width))
    )


def _load_immediate(size: ElementSize) -> StatementLowering:
    immediate = signed_immediate(SECOND_OPERAND, HALFWORD_BITS)
    return element_index_checked(M3, size, move(immediate, (), _to_element(size)))


def _register_range(statement: MachineStatement) -> tuple[int, int]:
    first = vec_reg_operand(statement, V1)
    return first, vec_reg_operand(statement, RANGE_END) - first + 1


def _invalid_range(statement: MachineStatement) -> bool:
    _, count = _register_range(statement)
    return not 0 < count <= MOST_REGISTERS


def _into_registers(
    emitter: HlasmEmitter, storage: Register, registers: RegionAt, width: int
) -> None:
    region, offset = registers
    image = emitter.load_bytes(storage, emitter.int_(0), width)
    emitter.write_bytes(region, offset, width, image)


def _into_storage(
    emitter: HlasmEmitter, storage: Register, registers: RegionAt, width: int
) -> None:
    image = emitter.load_bytes(*registers, width)
    emitter.write_bytes(storage, emitter.int_(0), width, image)


def _multiple(copy: ByteCopy) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        first, count = _register_range(statement)
        address = storage_address_at(RANGE_STORAGE)(emitter, statement)
        registers = (
            emitter.load_var(VECTOR_REGISTERS_VAR),
            emitter.int_(VECTOR_REGISTER_BYTES * first),
        )
        copy(emitter, address, registers, VECTOR_REGISTER_BYTES * count)

    return checked(_invalid_range, lower)


def _vr_address(emitter: HlasmEmitter, v: int) -> Register:
    return emitter.binop(
        BinopKind.ADD,
        emitter.load_var(VECTOR_REGISTERS_VAR),
        emitter.int_(VECTOR_REGISTER_BYTES * v),
    )


def _length(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    highest = emitter.load_gr32(reg_operand(statement, LENGTH_REGISTER))
    last = smaller(emitter, highest, emitter.int_(LAST_BYTE))
    return emitter.binop(BinopKind.ADD, last, emitter.int_(1))


def _load_zeroed(
    emitter: HlasmEmitter, v: int, address: Register, length: Register
) -> None:
    emitter.store_vr(v, emitter.int_(0))
    target = _vr_address(emitter, v)
    emit_byte_loop(
        emitter, length, lambda at: copy_byte(emitter, (target, address), at)
    )


def _load_with_length(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    address = storage_address_at(LENGTH_STORAGE)(emitter, statement)
    length = _length(emitter, statement)
    _load_zeroed(emitter, vec_reg_operand(statement, V1), address, length)


def _store_with_length(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    address = storage_address_at(LENGTH_STORAGE)(emitter, statement)
    length = _length(emitter, statement)
    source = _vr_address(emitter, vec_reg_operand(statement, V1))
    emit_byte_loop(
        emitter, length, lambda at: copy_byte(emitter, (address, source), at)
    )


def _load_to_block_boundary(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    address = storage_address(emitter, statement)
    block = SMALLEST_BLOCK << m_field(statement, M3)
    length = block_count(emitter, address, block)
    _load_zeroed(emitter, vec_reg_operand(statement, V1), address, length)


def _gather(size: ElementSize) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        index = m_field(statement, M3)
        operand = vector_indexed_operand(statement, SECOND_OPERAND)
        address = vector_indexed_address(emitter, operand, size, index)
        value = emitter.load_storage(address, 0, size.width)
        store_element(emitter, vec_reg_operand(statement, V1), size, index, value)

    return element_index_checked(M3, size, lower)


def _scatter(size: ElementSize) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        index = m_field(statement, M3)
        operand = vector_indexed_operand(statement, SECOND_OPERAND)
        address = vector_indexed_address(emitter, operand, size, index)
        value = load_element(emitter, vec_reg_operand(statement, V1), size, index)
        emitter.store_storage(address, 0, size.width, value)

    return element_index_checked(M3, size, lower)


def _reversing(size: ElementSize) -> tuple[Transform]:
    return (reversed_bytes(size.width),)


WHOLE_REGISTERS: Mapping[str, StatementLowering] = {
    "VL": move(from_storage(VECTOR_REGISTER_BYTES), (), to_v1),
    "VST": move(vr_at(V1), (), to_storage(VECTOR_REGISTER_BYTES)),
    "VLR": move(vr_at(SECOND_OPERAND), (), to_v1),
    "VLM": _multiple(_into_registers),
    "VSTM": _multiple(_into_storage),
}

ELEMENTS: Mapping[str, StatementLowering] = {
    "VLEB": _load_element(B, ()),
    "VLEH": _load_element(H, ()),
    "VLEF": _load_element(F, ()),
    "VLEG": _load_element(G, ()),
    "VSTEB": _store_element(B, ()),
    "VSTEH": _store_element(H, ()),
    "VSTEF": _store_element(F, ()),
    "VSTEG": _store_element(G, ()),
    "VLEIB": _load_immediate(B),
    "VLEIH": _load_immediate(H),
    "VLEIF": _load_immediate(F),
    "VLEIG": _load_immediate(G),
    "VLEBRH": _load_element(H, _reversing(H)),
    "VLEBRF": _load_element(F, _reversing(F)),
    "VLEBRG": _load_element(G, _reversing(G)),
    "VSTEBRH": _store_element(H, _reversing(H)),
    "VSTEBRF": _store_element(F, _reversing(F)),
    "VSTEBRG": _store_element(G, _reversing(G)),
}

PLACED_ELEMENTS: Mapping[str, StatementLowering] = {
    "VLREP": _whole(
        REPLICATED_SIZES,
        lambda size: move(from_storage(size.width), (replicated(size),), to_v1),
    ),
    "VLBRREP": _whole(
        ELEMENT_SIZES_FROM_HALFWORD,
        lambda size: move(
            from_storage(size.width), (*_reversing(size), replicated(size)), to_v1
        ),
    ),
    "VLLEZ": _coded(
        _zero_extended(REPLICATED_SIZES),
        lambda place: move(
            from_storage(place.width), (_shifted_left(place.shift),), to_v1
        ),
    ),
    "VLLEBRZ": _coded(
        _zero_extended(ELEMENT_SIZES_FROM_HALFWORD),
        lambda place: move(
            from_storage(place.width),
            (reversed_bytes(place.width), _shifted_left(place.shift)),
            to_v1,
        ),
    ),
}

PARTIAL_LOADS: Mapping[str, StatementLowering] = {
    "VLL": _load_with_length,
    "VSTL": _store_with_length,
    "VLBB": checked(
        lambda statement: m_field(statement, M3) > LARGEST_BOUNDARY_CODE,
        _load_to_block_boundary,
    ),
}

GATHER_SCATTER: Mapping[str, StatementLowering] = {
    "VGEF": _gather(F),
    "VGEG": _gather(G),
    "VSCEF": _scatter(F),
    "VSCEG": _scatter(G),
}

REORDERED: Mapping[str, StatementLowering] = {
    "VLBR": _whole(
        BYTE_REVERSED_SIZES,
        lambda size: move(
            from_storage(VECTOR_REGISTER_BYTES), (_bytes_reversed(size),), to_v1
        ),
    ),
    "VSTBR": _whole(
        BYTE_REVERSED_SIZES,
        lambda size: move(
            vr_at(V1), (_bytes_reversed(size),), to_storage(VECTOR_REGISTER_BYTES)
        ),
    ),
    "VLER": _whole(
        ELEMENT_SIZES_FROM_HALFWORD,
        lambda size: move(
            from_storage(VECTOR_REGISTER_BYTES), (_elements_reversed(size),), to_v1
        ),
    ),
    "VSTER": _whole(
        ELEMENT_SIZES_FROM_HALFWORD,
        lambda size: move(
            vr_at(V1), (_elements_reversed(size),), to_storage(VECTOR_REGISTER_BYTES)
        ),
    ),
}

VECTOR_MEMORY_LOWERINGS: Mapping[str, StatementLowering] = {
    **WHOLE_REGISTERS,
    **ELEMENTS,
    **PLACED_ELEMENTS,
    **PARTIAL_LOADS,
    **GATHER_SCATTER,
    **REORDERED,
}
