# pyright: standard
"""Load and store opcodes: storage, register and relative-long moves, multiples and masked bytes."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import (
    from_aligned_storage,
    from_gr32,
    from_gr64,
    from_relative,
    from_storage,
    gather_bytes,
    into_low_bytes,
    keep,
    merge_low_word,
    move,
    reversed_bytes,
    signed,
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
    DOUBLEWORD_BYTES,
    GPR_COUNT,
    PARAM_VALUE,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_ir
from interpreter.hlasm.operands import mask_operand, reg_operand, storage_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.register import Register

type RegisterWrite = Callable[[HlasmEmitter, int, Register], None]
type RegisterRead = Callable[[HlasmEmitter, int], Register]

BYTE = 1
HALFWORD = 2
WORD = WORD_BYTES
DOUBLEWORD = DOUBLEWORD_BYTES
RIGHTMOST_BYTE_ZERO_32 = 0xFFFFFF00
RIGHTMOST_BYTE_ZERO_64 = 0xFFFFFFFF_FFFFFF00
BYTE_MASK = 0xFF
HALFWORD_MASK = 0xFFFF
BYTE_BITS = 8
HALFWORD_BITS = 16
WORD_BITS = 32
LOW_WORD_POSITIONS = 4
MASK_BITS = (0b1000, 0b0100, 0b0010, 0b0001)
SIGN_CC = {
    width: build_sign_cc_ir(f"hlasm.icm{width}", BITS_PER_BYTE * width)
    for width in range(1, LOW_WORD_POSITIONS + 1)
}

STORAGE_LOADS: Mapping[str, StatementLowering] = {
    "L": move(from_storage(WORD), (), to_gr32),
    "LY": move(from_storage(WORD), (), to_gr32),
    "LH": move(from_storage(HALFWORD), (signed(HALFWORD_BITS),), to_gr32),
    "LHY": move(from_storage(HALFWORD), (signed(HALFWORD_BITS),), to_gr32),
    "LB": move(from_storage(BYTE), (signed(BYTE_BITS),), to_gr32),
    "LLC": move(from_storage(BYTE), (), to_gr32),
    "LLH": move(from_storage(HALFWORD), (), to_gr32),
    "LZRF": move(from_storage(WORD), (keep(RIGHTMOST_BYTE_ZERO_32),), to_gr32),
    "LRV": move(from_storage(WORD), (reversed_bytes(WORD),), to_gr32),
    "LG": move(from_storage(DOUBLEWORD), (), to_gr64),
    "LGF": move(from_storage(WORD), (signed(WORD_BITS),), to_gr64),
    "LGH": move(from_storage(HALFWORD), (signed(HALFWORD_BITS),), to_gr64),
    "LGB": move(from_storage(BYTE), (signed(BYTE_BITS),), to_gr64),
    "LLGC": move(from_storage(BYTE), (), to_gr64),
    "LLGH": move(from_storage(HALFWORD), (), to_gr64),
    "LLGF": move(from_storage(WORD), (), to_gr64),
    "LLGT": move(from_storage(WORD), (keep(ADDRESS_MASK_31),), to_gr64),
    "LZRG": move(from_storage(DOUBLEWORD), (keep(RIGHTMOST_BYTE_ZERO_64),), to_gr64),
    "LLZRGF": move(from_storage(WORD), (keep(RIGHTMOST_BYTE_ZERO_32),), to_gr64),
    "LRVG": move(from_storage(DOUBLEWORD), (reversed_bytes(DOUBLEWORD),), to_gr64),
    "LGG": move(from_aligned_storage(DOUBLEWORD), (keep(ADDRESS_MASK_31),), to_gr64),
    "LLGFSG": move(from_aligned_storage(WORD), (keep(ADDRESS_MASK_31),), to_gr64),
    "IC": move(from_storage(BYTE), (), into_low_bytes(BYTE)),
    "ICY": move(from_storage(BYTE), (), into_low_bytes(BYTE)),
    "LRVH": move(
        from_storage(HALFWORD), (reversed_bytes(HALFWORD),), into_low_bytes(HALFWORD)
    ),
}

REGISTER_LOADS: Mapping[str, StatementLowering] = {
    "LGR": move(from_gr64(1), (), to_gr64),
    "LBR": move(from_gr32(1), (signed(BYTE_BITS),), to_gr32),
    "LGBR": move(from_gr32(1), (signed(BYTE_BITS),), to_gr64),
    "LHR": move(from_gr32(1), (signed(HALFWORD_BITS),), to_gr32),
    "LGHR": move(from_gr32(1), (signed(HALFWORD_BITS),), to_gr64),
    "LGFR": move(from_gr32(1), (signed(WORD_BITS),), to_gr64),
    "LLCR": move(from_gr32(1), (keep(BYTE_MASK),), to_gr32),
    "LLGCR": move(from_gr32(1), (keep(BYTE_MASK),), to_gr64),
    "LLHR": move(from_gr32(1), (keep(HALFWORD_MASK),), to_gr32),
    "LLGHR": move(from_gr32(1), (keep(HALFWORD_MASK),), to_gr64),
    "LLGFR": move(from_gr32(1), (), to_gr64),
    "LLGTR": move(from_gr32(1), (keep(ADDRESS_MASK_31),), to_gr64),
    "LRVR": move(from_gr32(1), (reversed_bytes(WORD),), to_gr32),
    "LRVGR": move(from_gr64(1), (reversed_bytes(DOUBLEWORD),), to_gr64),
}

RELATIVE_LOADS: Mapping[str, StatementLowering] = {
    "LRL": move(from_relative(WORD), (), to_gr32),
    "LGRL": move(from_relative(DOUBLEWORD), (), to_gr64),
    "LGFRL": move(from_relative(WORD), (signed(WORD_BITS),), to_gr64),
    "LLGFRL": move(from_relative(WORD), (), to_gr64),
    "LHRL": move(from_relative(HALFWORD), (signed(HALFWORD_BITS),), to_gr32),
    "LGHRL": move(from_relative(HALFWORD), (signed(HALFWORD_BITS),), to_gr64),
    "LLHRL": move(from_relative(HALFWORD), (), to_gr32),
    "LLGHRL": move(from_relative(HALFWORD), (), to_gr64),
}

STORES: Mapping[str, StatementLowering] = {
    "ST": move(from_gr32(0), (), to_storage(WORD)),
    "STY": move(from_gr32(0), (), to_storage(WORD)),
    "STG": move(from_gr64(0), (), to_storage(DOUBLEWORD)),
    "STH": move(from_gr32(0), (), to_storage(HALFWORD)),
    "STHY": move(from_gr32(0), (), to_storage(HALFWORD)),
    "STC": move(from_gr32(0), (), to_storage(BYTE)),
    "STCY": move(from_gr32(0), (), to_storage(BYTE)),
    "STRV": move(from_gr32(0), (reversed_bytes(WORD),), to_storage(WORD)),
    "STRVG": move(from_gr64(0), (reversed_bytes(DOUBLEWORD),), to_storage(DOUBLEWORD)),
    "STRVH": move(from_gr32(0), (reversed_bytes(HALFWORD),), to_storage(HALFWORD)),
    "STRL": move(from_gr32(0), (), to_relative(WORD)),
    "STGRL": move(from_gr64(0), (), to_relative(DOUBLEWORD)),
    "STHRL": move(from_gr32(0), (), to_relative(HALFWORD)),
}


def _register_range(statement: MachineStatement) -> tuple[int, ...]:
    r1, r3 = reg_operand(statement, 0), reg_operand(statement, 1)
    return tuple((r1 + at) % GPR_COUNT for at in range((r3 - r1) % GPR_COUNT + 1))


def _operand_address(
    emitter: HlasmEmitter, statement: MachineStatement, index: int
) -> Register:
    return effective_address(emitter, storage_operand(statement, index))


def _load_multiple(width: int, write: RegisterWrite) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        address = _operand_address(emitter, statement, 2)
        _ = [
            write(emitter, r, emitter.load_storage(address, width * at, width))
            for at, r in enumerate(_register_range(statement))
        ]

    return lower


def _store_multiple(width: int, read: RegisterRead) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        address = _operand_address(emitter, statement, 2)
        _ = [
            emitter.store_storage(address, width * at, width, read(emitter, r))
            for at, r in enumerate(_register_range(statement))
        ]

    return lower


def _load_multiple_disjoint_one(
    emitter: HlasmEmitter, r: int, at: int, halves: tuple[Register, Register]
) -> None:
    high, low = halves
    emitter.store_gr_high32(r, emitter.load_storage(high, WORD * at, WORD))
    emitter.store_gr32(r, emitter.load_storage(low, WORD * at, WORD))


def lower_lmd(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    halves = (
        _operand_address(emitter, statement, 2),
        _operand_address(emitter, statement, 3),
    )
    _ = [
        _load_multiple_disjoint_one(emitter, r, at, halves)
        for at, r in enumerate(_register_range(statement))
    ]


def _selected_positions(mask: int) -> tuple[int, ...]:
    return tuple(at for at, bit in enumerate(MASK_BITS) if mask & bit)


def _position_shift(position: int) -> int:
    return LOW_WORD_POSITIONS - 1 - position


def lower_insert_under_mask(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    positions = _selected_positions(mask_operand(statement, 1))
    if not positions:
        emitter.set_cc(emitter.int_(0))
        return
    width = len(positions)
    loaded = emitter.load_storage(_operand_address(emitter, statement, 2), 0, width)
    moves = tuple(
        (width - 1 - at, _position_shift(p)) for at, p in enumerate(positions)
    )
    field_mask = sum(
        BYTE_MASK << (BITS_PER_BYTE * _position_shift(p)) for p in positions
    )
    merge_low_word(
        emitter,
        reg_operand(statement, 0),
        gather_bytes(emitter, loaded, moves),
        field_mask,
    )
    emitter.set_cc(inline_ir(emitter, SIGN_CC[width], {PARAM_VALUE: loaded}))


def lower_store_under_mask(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    positions = _selected_positions(mask_operand(statement, 1))
    if not positions:
        return
    width = len(positions)
    value = emitter.load_gr32(reg_operand(statement, 0))
    moves = tuple(
        (_position_shift(p), width - 1 - at) for at, p in enumerate(positions)
    )
    emitter.store_storage(
        _operand_address(emitter, statement, 2),
        0,
        width,
        gather_bytes(emitter, value, moves),
    )


MULTIPLES: Mapping[str, StatementLowering] = {
    "LM": _load_multiple(WORD, lambda emitter, r, value: emitter.store_gr32(r, value)),
    "LMY": _load_multiple(WORD, lambda emitter, r, value: emitter.store_gr32(r, value)),
    "LMG": _load_multiple(
        DOUBLEWORD, lambda emitter, r, value: emitter.store_gr64(r, value)
    ),
    "STM": _store_multiple(WORD, lambda emitter, r: emitter.load_gr32(r)),
    "STMY": _store_multiple(WORD, lambda emitter, r: emitter.load_gr32(r)),
    "STMG": _store_multiple(DOUBLEWORD, lambda emitter, r: emitter.load_gr64(r)),
    "LMD": lower_lmd,
    "ICM": lower_insert_under_mask,
    "ICMY": lower_insert_under_mask,
    "STCM": lower_store_under_mask,
    "STCMY": lower_store_under_mask,
}

LOAD_STORE_LOWERINGS: Mapping[str, StatementLowering] = {
    **STORAGE_LOADS,
    **REGISTER_LOADS,
    **RELATIVE_LOADS,
    **STORES,
    **MULTIPLES,
}
