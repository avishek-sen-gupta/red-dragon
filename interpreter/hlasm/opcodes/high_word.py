# pyright: standard
"""High-word opcodes: arithmetic, compares, loads, stores, masked bytes and branch on count over bits 0-31 of a register; the low word of R1 is never written."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import (
    Source,
    from_gr32,
    from_gr_high32,
    from_storage,
    move,
    relative_target,
    signed,
    to_gr_high32,
    to_storage,
)
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    HALFWORD_BITS,
    HALFWORD_BYTES,
    ONE_BYTE,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.compare import (
    LOGICAL_32,
    SIGNED_32,
    compare,
    compare_under_mask,
)
from interpreter.hlasm.opcodes.compare_branch_trap import trapping_on_zero
from interpreter.hlasm.opcodes.load_store import (
    insert_under_mask,
    load_multiple,
    store_multiple,
    store_under_mask,
)
from interpreter.hlasm.opcodes.logical_add_subtract import (
    ADD_32 as ADD_LOGICAL_32,
)
from interpreter.hlasm.opcodes.logical_add_subtract import (
    SUB_BORROW_32,
    carried_sum,
    logical_sum,
    no_borrow,
)
from interpreter.hlasm.opcodes.loop_branch import on_count
from interpreter.hlasm.opcodes.operand_sources import (
    LOGICAL_WORD_IMMEDIATE,
    WORD_IMMEDIATE,
    WORD_STORAGE,
)
from interpreter.hlasm.opcodes.signed_add_subtract import (
    ADD_32,
    SUB_32,
    signed_arithmetic,
)
from interpreter.hlasm.register_parts import HIGH_WORD_PART
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind

R1_HIGH = from_gr_high32(0)
R2_HIGH = from_gr_high32(1)
R2_LOW = from_gr32(1)
R3_HIGH = from_gr_high32(2)
R3_LOW = from_gr32(2)

ADD_LOGICAL_HIGH = logical_sum(ADD_LOGICAL_32, to_gr_high32)
SUB_LOGICAL_HIGH = carried_sum(SUB_BORROW_32, to_gr_high32, no_borrow)


def _sum_keeping_cc(left: Source, right: Source) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        total = emitter.binop(
            BinopKind.ADD, left(emitter, statement), right(emitter, statement)
        )
        to_gr_high32(emitter, statement, total)

    return lower


ARITHMETIC: Mapping[str, StatementLowering] = {
    "AHHHR": signed_arithmetic(ADD_32, R2_HIGH, R3_HIGH, to_gr_high32),
    "AHHLR": signed_arithmetic(ADD_32, R2_HIGH, R3_LOW, to_gr_high32),
    "SHHHR": signed_arithmetic(SUB_32, R2_HIGH, R3_HIGH, to_gr_high32),
    "SHHLR": signed_arithmetic(SUB_32, R2_HIGH, R3_LOW, to_gr_high32),
    "AIH": signed_arithmetic(ADD_32, R1_HIGH, WORD_IMMEDIATE, to_gr_high32),
    "ALHHHR": ADD_LOGICAL_HIGH(R2_HIGH, R3_HIGH),
    "ALHHLR": ADD_LOGICAL_HIGH(R2_HIGH, R3_LOW),
    "SLHHHR": SUB_LOGICAL_HIGH(R2_HIGH, R3_HIGH),
    "SLHHLR": SUB_LOGICAL_HIGH(R2_HIGH, R3_LOW),
    "ALSIH": ADD_LOGICAL_HIGH(R1_HIGH, WORD_IMMEDIATE),
    "ALSIHN": _sum_keeping_cc(R1_HIGH, WORD_IMMEDIATE),
}

COMPARES: Mapping[str, StatementLowering] = {
    "CHHR": compare(SIGNED_32, R1_HIGH, R2_HIGH),
    "CHLR": compare(SIGNED_32, R1_HIGH, R2_LOW),
    "CHF": compare(SIGNED_32, R1_HIGH, WORD_STORAGE),
    "CIH": compare(SIGNED_32, R1_HIGH, WORD_IMMEDIATE),
    "CLHHR": compare(LOGICAL_32, R1_HIGH, R2_HIGH),
    "CLHLR": compare(LOGICAL_32, R1_HIGH, R2_LOW),
    "CLHF": compare(LOGICAL_32, R1_HIGH, WORD_STORAGE),
    "CLIH": compare(LOGICAL_32, R1_HIGH, LOGICAL_WORD_IMMEDIATE),
    "CLMH": compare_under_mask(HIGH_WORD_PART),
}

LOADS_AND_STORES: Mapping[str, StatementLowering] = {
    "LBH": move(from_storage(ONE_BYTE), (signed(BITS_PER_BYTE),), to_gr_high32),
    "LHH": move(from_storage(HALFWORD_BYTES), (signed(HALFWORD_BITS),), to_gr_high32),
    "LLCH": move(from_storage(ONE_BYTE), (), to_gr_high32),
    "LLHH": move(from_storage(HALFWORD_BYTES), (), to_gr_high32),
    "LFH": move(WORD_STORAGE, (), to_gr_high32),
    "LFHAT": move(WORD_STORAGE, (), trapping_on_zero(to_gr_high32)),
    "STCH": move(R1_HIGH, (), to_storage(ONE_BYTE)),
    "STHH": move(R1_HIGH, (), to_storage(HALFWORD_BYTES)),
    "STFH": move(R1_HIGH, (), to_storage(WORD_BYTES)),
    "LMH": load_multiple(HIGH_WORD_PART),
    "STMH": store_multiple(HIGH_WORD_PART),
    "ICMH": insert_under_mask(HIGH_WORD_PART),
    "STCMH": store_under_mask(HIGH_WORD_PART),
}

HIGH_WORD_LOWERINGS: Mapping[str, StatementLowering] = {
    **ARITHMETIC,
    **COMPARES,
    **LOADS_AND_STORES,
    "BRCTH": on_count(HIGH_WORD_PART, relative_target),
}
