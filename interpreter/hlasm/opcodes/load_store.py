# pyright: standard
"""Load and store opcodes: storage, register and relative-long moves, multiples and masked bytes."""

from collections.abc import Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import (
    Source,
    from_aligned_storage,
    from_gr32,
    from_gr64,
    from_relative,
    from_storage,
    gather_bytes,
    into_low_bytes,
    keep,
    move,
    reversed_bytes,
    signed,
    storage_address_at,
    to_gr32,
    to_gr64,
    to_relative,
    to_storage,
)
from interpreter.hlasm.effective_address import effective_address
from interpreter.hlasm.fixed_width_ir import build_sign_cc_ir
from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    BITS_PER_BYTE,
    BYTE_MASK,
    DOUBLEWORD_BYTES,
    GPR_COUNT,
    HALFWORD_BITS,
    HALFWORD_BYTES,
    HALFWORD_MASK,
    ONE_BYTE,
    PARAM_VALUE,
    WORD_BITS,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_ir
from interpreter.hlasm.operands import mask_operand, reg_operand, storage_operand
from interpreter.hlasm.register_part import RegisterPart
from interpreter.hlasm.register_parts import LOW_WORD_PART, WHOLE_REGISTER_PART
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.register import Register

RIGHTMOST_BYTE_ZERO_32 = 0xFFFFFF00
RIGHTMOST_BYTE_ZERO_64 = 0xFFFFFFFF_FFFFFF00
LOW_WORD_POSITIONS = 4
MASK_BITS = (0b1000, 0b0100, 0b0010, 0b0001)
SIGN_CC = {
    width: build_sign_cc_ir(f"hlasm.icm{width}", BITS_PER_BYTE * width)
    for width in range(1, LOW_WORD_POSITIONS + 1)
}

STORAGE_LOADS: Mapping[str, StatementLowering] = {
    "L": move(from_storage(WORD_BYTES), (), to_gr32),
    "LY": move(from_storage(WORD_BYTES), (), to_gr32),
    "LH": move(from_storage(HALFWORD_BYTES), (signed(HALFWORD_BITS),), to_gr32),
    "LHY": move(from_storage(HALFWORD_BYTES), (signed(HALFWORD_BITS),), to_gr32),
    "LB": move(from_storage(ONE_BYTE), (signed(BITS_PER_BYTE),), to_gr32),
    "LLC": move(from_storage(ONE_BYTE), (), to_gr32),
    "LLH": move(from_storage(HALFWORD_BYTES), (), to_gr32),
    "LZRF": move(from_storage(WORD_BYTES), (keep(RIGHTMOST_BYTE_ZERO_32),), to_gr32),
    "LRV": move(from_storage(WORD_BYTES), (reversed_bytes(WORD_BYTES),), to_gr32),
    "LG": move(from_storage(DOUBLEWORD_BYTES), (), to_gr64),
    "LGF": move(from_storage(WORD_BYTES), (signed(WORD_BITS),), to_gr64),
    "LGH": move(from_storage(HALFWORD_BYTES), (signed(HALFWORD_BITS),), to_gr64),
    "LGB": move(from_storage(ONE_BYTE), (signed(BITS_PER_BYTE),), to_gr64),
    "LLGC": move(from_storage(ONE_BYTE), (), to_gr64),
    "LLGH": move(from_storage(HALFWORD_BYTES), (), to_gr64),
    "LLGF": move(from_storage(WORD_BYTES), (), to_gr64),
    "LLGT": move(from_storage(WORD_BYTES), (keep(ADDRESS_MASK_31),), to_gr64),
    "LZRG": move(
        from_storage(DOUBLEWORD_BYTES), (keep(RIGHTMOST_BYTE_ZERO_64),), to_gr64
    ),
    "LLZRGF": move(from_storage(WORD_BYTES), (keep(RIGHTMOST_BYTE_ZERO_32),), to_gr64),
    "LRVG": move(
        from_storage(DOUBLEWORD_BYTES), (reversed_bytes(DOUBLEWORD_BYTES),), to_gr64
    ),
    "LGG": move(
        from_aligned_storage(DOUBLEWORD_BYTES), (keep(ADDRESS_MASK_31),), to_gr64
    ),
    "LLGFSG": move(from_aligned_storage(WORD_BYTES), (keep(ADDRESS_MASK_31),), to_gr64),
    "IC": move(from_storage(ONE_BYTE), (), into_low_bytes(ONE_BYTE)),
    "ICY": move(from_storage(ONE_BYTE), (), into_low_bytes(ONE_BYTE)),
    "LRVH": move(
        from_storage(HALFWORD_BYTES),
        (reversed_bytes(HALFWORD_BYTES),),
        into_low_bytes(HALFWORD_BYTES),
    ),
}

REGISTER_LOADS: Mapping[str, StatementLowering] = {
    "LR": move(from_gr32(1), (), to_gr32),
    "LGR": move(from_gr64(1), (), to_gr64),
    "LBR": move(from_gr32(1), (signed(BITS_PER_BYTE),), to_gr32),
    "LGBR": move(from_gr32(1), (signed(BITS_PER_BYTE),), to_gr64),
    "LHR": move(from_gr32(1), (signed(HALFWORD_BITS),), to_gr32),
    "LGHR": move(from_gr32(1), (signed(HALFWORD_BITS),), to_gr64),
    "LGFR": move(from_gr32(1), (signed(WORD_BITS),), to_gr64),
    "LLCR": move(from_gr32(1), (keep(BYTE_MASK),), to_gr32),
    "LLGCR": move(from_gr32(1), (keep(BYTE_MASK),), to_gr64),
    "LLHR": move(from_gr32(1), (keep(HALFWORD_MASK),), to_gr32),
    "LLGHR": move(from_gr32(1), (keep(HALFWORD_MASK),), to_gr64),
    "LLGFR": move(from_gr32(1), (), to_gr64),
    "LLGTR": move(from_gr32(1), (keep(ADDRESS_MASK_31),), to_gr64),
    "LRVR": move(from_gr32(1), (reversed_bytes(WORD_BYTES),), to_gr32),
    "LRVGR": move(from_gr64(1), (reversed_bytes(DOUBLEWORD_BYTES),), to_gr64),
}

RELATIVE_LOADS: Mapping[str, StatementLowering] = {
    "LRL": move(from_relative(WORD_BYTES), (), to_gr32),
    "LGRL": move(from_relative(DOUBLEWORD_BYTES), (), to_gr64),
    "LGFRL": move(from_relative(WORD_BYTES), (signed(WORD_BITS),), to_gr64),
    "LLGFRL": move(from_relative(WORD_BYTES), (), to_gr64),
    "LHRL": move(from_relative(HALFWORD_BYTES), (signed(HALFWORD_BITS),), to_gr32),
    "LGHRL": move(from_relative(HALFWORD_BYTES), (signed(HALFWORD_BITS),), to_gr64),
    "LLHRL": move(from_relative(HALFWORD_BYTES), (), to_gr32),
    "LLGHRL": move(from_relative(HALFWORD_BYTES), (), to_gr64),
}

STORES: Mapping[str, StatementLowering] = {
    "ST": move(from_gr32(0), (), to_storage(WORD_BYTES)),
    "STY": move(from_gr32(0), (), to_storage(WORD_BYTES)),
    "STG": move(from_gr64(0), (), to_storage(DOUBLEWORD_BYTES)),
    "STH": move(from_gr32(0), (), to_storage(HALFWORD_BYTES)),
    "STHY": move(from_gr32(0), (), to_storage(HALFWORD_BYTES)),
    "STC": move(from_gr32(0), (), to_storage(ONE_BYTE)),
    "STCY": move(from_gr32(0), (), to_storage(ONE_BYTE)),
    "STRV": move(from_gr32(0), (reversed_bytes(WORD_BYTES),), to_storage(WORD_BYTES)),
    "STRVG": move(
        from_gr64(0), (reversed_bytes(DOUBLEWORD_BYTES),), to_storage(DOUBLEWORD_BYTES)
    ),
    "STRVH": move(
        from_gr32(0), (reversed_bytes(HALFWORD_BYTES),), to_storage(HALFWORD_BYTES)
    ),
    "STRL": move(from_gr32(0), (), to_relative(WORD_BYTES)),
    "STGRL": move(from_gr64(0), (), to_relative(DOUBLEWORD_BYTES)),
    "STHRL": move(from_gr32(0), (), to_relative(HALFWORD_BYTES)),
}


def _register_range(statement: MachineStatement) -> tuple[int, ...]:
    r1, r3 = reg_operand(statement, 0), reg_operand(statement, 1)
    return tuple((r1 + at) % GPR_COUNT for at in range((r3 - r1) % GPR_COUNT + 1))


def _operand_address(
    emitter: HlasmEmitter, statement: MachineStatement, index: int
) -> Register:
    return effective_address(emitter, storage_operand(statement, index))


MULTIPLE_ADDRESS = storage_address_at(2)


def load_multiple(
    part: RegisterPart, address_of: Source = MULTIPLE_ADDRESS
) -> StatementLowering:
    width = part.bytes()

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        address = address_of(emitter, statement)
        _ = [
            part.store(emitter, r, emitter.load_storage(address, width * at, width))
            for at, r in enumerate(_register_range(statement))
        ]

    return lower


def store_multiple(
    part: RegisterPart, address_of: Source = MULTIPLE_ADDRESS
) -> StatementLowering:
    width = part.bytes()

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        address = address_of(emitter, statement)
        _ = [
            emitter.store_storage(address, width * at, width, part.load(emitter, r))
            for at, r in enumerate(_register_range(statement))
        ]

    return lower


def _load_multiple_disjoint_one(
    emitter: HlasmEmitter, r: int, at: int, halves: tuple[Register, Register]
) -> None:
    high, low = halves
    emitter.store_gr_high32(r, emitter.load_storage(high, WORD_BYTES * at, WORD_BYTES))
    emitter.store_gr32(r, emitter.load_storage(low, WORD_BYTES * at, WORD_BYTES))


def lower_lmd(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    halves = (
        _operand_address(emitter, statement, 2),
        _operand_address(emitter, statement, 3),
    )
    _ = [
        _load_multiple_disjoint_one(emitter, r, at, halves)
        for at, r in enumerate(_register_range(statement))
    ]


def selected_positions(mask: int) -> tuple[int, ...]:
    return tuple(at for at, bit in enumerate(MASK_BITS) if mask & bit)


def _position_shift(position: int) -> int:
    return LOW_WORD_POSITIONS - 1 - position


def _insert_selected(
    emitter: HlasmEmitter,
    statement: MachineStatement,
    part: RegisterPart,
    positions: Sequence[int],
) -> None:
    width = len(positions)
    loaded = emitter.load_storage(_operand_address(emitter, statement, 2), 0, width)
    moves = tuple(
        (width - 1 - at, _position_shift(p)) for at, p in enumerate(positions)
    )
    field_mask = sum(
        BYTE_MASK << (BITS_PER_BYTE * _position_shift(p)) for p in positions
    )
    part.merge(
        emitter,
        reg_operand(statement, 0),
        gather_bytes(emitter, loaded, moves),
        field_mask,
    )
    emitter.set_cc(inline_ir(emitter, SIGN_CC[width], {PARAM_VALUE: loaded}))


def insert_under_mask(part: RegisterPart) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        positions = selected_positions(mask_operand(statement, 1))
        if not positions:
            emitter.set_cc(emitter.int_(0))
            return
        _insert_selected(emitter, statement, part, positions)

    return lower


def register_bytes_under_mask(
    emitter: HlasmEmitter, part: RegisterPart, r: int, positions: Sequence[int]
) -> Register:
    width = len(positions)
    moves = tuple(
        (_position_shift(p), width - 1 - at) for at, p in enumerate(positions)
    )
    return gather_bytes(emitter, part.load(emitter, r), moves)


def store_under_mask(part: RegisterPart) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        positions = selected_positions(mask_operand(statement, 1))
        if not positions:
            return
        emitter.store_storage(
            _operand_address(emitter, statement, 2),
            0,
            len(positions),
            register_bytes_under_mask(
                emitter, part, reg_operand(statement, 0), positions
            ),
        )

    return lower


MULTIPLES: Mapping[str, StatementLowering] = {
    "LM": load_multiple(LOW_WORD_PART),
    "LMY": load_multiple(LOW_WORD_PART),
    "LMG": load_multiple(WHOLE_REGISTER_PART),
    "STM": store_multiple(LOW_WORD_PART),
    "STMY": store_multiple(LOW_WORD_PART),
    "STMG": store_multiple(WHOLE_REGISTER_PART),
    "LMD": lower_lmd,
    "ICM": insert_under_mask(LOW_WORD_PART),
    "ICMY": insert_under_mask(LOW_WORD_PART),
    "STCM": store_under_mask(LOW_WORD_PART),
    "STCMY": store_under_mask(LOW_WORD_PART),
}

LOAD_STORE_LOWERINGS: Mapping[str, StatementLowering] = {
    **STORAGE_LOADS,
    **REGISTER_LOADS,
    **RELATIVE_LOADS,
    **STORES,
    **MULTIPLES,
}
