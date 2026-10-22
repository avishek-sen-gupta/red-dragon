# pyright: standard
"""Compare opcodes, signed and logical: register, storage, immediate, relative-long and masked operands; only the CC is set."""

from collections.abc import Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_one_layouts import IMMEDIATE_BYTE
from interpreter.hlasm.data_movement import (
    Source,
    from_gr32,
    from_gr64,
    from_relative,
    from_storage_at,
    sign_extended,
    storage_address_at,
)
from interpreter.hlasm.field_lowering import (
    FieldLowering,
    with_field_source,
    written_lowerings,
)
from interpreter.hlasm.fixed_width_ir import (
    build_compare_logical_cc_ir,
    build_compare_signed_cc_ir,
)
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    DOUBLEWORD_BITS,
    DOUBLEWORD_BYTES,
    HALFWORD_BITS,
    HALFWORD_BYTES,
    ONE_BYTE,
    PARAM_LEFT,
    PARAM_RIGHT,
    WORD_BITS,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_ir
from interpreter.hlasm.opcodes.load_store import (
    register_bytes_under_mask,
    selected_positions,
)
from interpreter.hlasm.opcodes.operand_sources import (
    DOUBLEWORD_STORAGE,
    HALFWORD_IMMEDIATE,
    LOGICAL_HALFWORD_IMMEDIATE,
    LOGICAL_WORD_IMMEDIATE,
    SIGNED_HALFWORD_STORAGE,
    SIGNED_LOW_WORD,
    SIGNED_WORD_STORAGE,
    WORD_IMMEDIATE,
    WORD_STORAGE,
)
from interpreter.hlasm.operands import mask_operand, reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import InstructionBase

type Comparison = Sequence[InstructionBase]

FIRST_OPERAND = 0
MASK_OPERAND = 1
MASKED_STORAGE_OPERAND = 2
EQUAL = 0

SIGNED_16 = build_compare_signed_cc_ir("hlasm.cmp16", HALFWORD_BITS)
SIGNED_32 = build_compare_signed_cc_ir("hlasm.cmp32", WORD_BITS)
SIGNED_64 = build_compare_signed_cc_ir("hlasm.cmp64", DOUBLEWORD_BITS)
LOGICAL_8 = build_compare_logical_cc_ir("hlasm.cmpl8", BITS_PER_BYTE)
LOGICAL_16 = build_compare_logical_cc_ir("hlasm.cmpl16", HALFWORD_BITS)
LOGICAL_32 = build_compare_logical_cc_ir("hlasm.cmpl32", WORD_BITS)
LOGICAL_64 = build_compare_logical_cc_ir("hlasm.cmpl64", DOUBLEWORD_BITS)


def compare(comparison: Comparison, left: Source, right: Source) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        arguments = {
            PARAM_LEFT: left(emitter, statement),
            PARAM_RIGHT: right(emitter, statement),
        }
        emitter.set_cc(inline_ir(emitter, comparison, arguments))

    return lower


def from_first_storage(width: int) -> Source:
    return from_storage_at(FIRST_OPERAND, width)


def lower_compare_under_mask(
    emitter: HlasmEmitter, statement: MachineStatement
) -> None:
    positions = selected_positions(mask_operand(statement, MASK_OPERAND))
    if not positions:
        emitter.set_cc(emitter.int_(EQUAL))
        return
    field = register_bytes_under_mask(
        emitter, reg_operand(statement, FIRST_OPERAND), positions
    )
    address = storage_address_at(MASKED_STORAGE_OPERAND)(emitter, statement)
    stored = emitter.load_storage(address, 0, len(positions))
    emitter.set_cc(
        inline_ir(emitter, LOGICAL_32, {PARAM_LEFT: field, PARAM_RIGHT: stored})
    )


SIGNED_HALFWORD_RELATIVE = sign_extended(from_relative(HALFWORD_BYTES), HALFWORD_BITS)
SIGNED_WORD_RELATIVE = sign_extended(from_relative(WORD_BYTES), WORD_BITS)
COMPARE_IMMEDIATE_BYTE = FieldLowering(
    IMMEDIATE_BYTE,
    with_field_source(
        lambda immediate: compare(LOGICAL_8, from_first_storage(ONE_BYTE), immediate)
    ),
)

SIGNED_COMPARES: Mapping[str, StatementLowering] = {
    "C": compare(SIGNED_32, from_gr32(0), WORD_STORAGE),
    "CY": compare(SIGNED_32, from_gr32(0), WORD_STORAGE),
    "CR": compare(SIGNED_32, from_gr32(0), from_gr32(1)),
    "CFI": compare(SIGNED_32, from_gr32(0), WORD_IMMEDIATE),
    "CRL": compare(SIGNED_32, from_gr32(0), from_relative(WORD_BYTES)),
    "CH": compare(SIGNED_32, from_gr32(0), SIGNED_HALFWORD_STORAGE),
    "CHY": compare(SIGNED_32, from_gr32(0), SIGNED_HALFWORD_STORAGE),
    "CHI": compare(SIGNED_32, from_gr32(0), HALFWORD_IMMEDIATE),
    "CHRL": compare(SIGNED_32, from_gr32(0), SIGNED_HALFWORD_RELATIVE),
    "CHSI": compare(SIGNED_32, from_first_storage(WORD_BYTES), HALFWORD_IMMEDIATE),
    "CHHSI": compare(SIGNED_16, from_first_storage(HALFWORD_BYTES), HALFWORD_IMMEDIATE),
    "CG": compare(SIGNED_64, from_gr64(0), DOUBLEWORD_STORAGE),
    "CGR": compare(SIGNED_64, from_gr64(0), from_gr64(1)),
    "CGRL": compare(SIGNED_64, from_gr64(0), from_relative(DOUBLEWORD_BYTES)),
    "CGF": compare(SIGNED_64, from_gr64(0), SIGNED_WORD_STORAGE),
    "CGFR": compare(SIGNED_64, from_gr64(0), SIGNED_LOW_WORD),
    "CGFI": compare(SIGNED_64, from_gr64(0), WORD_IMMEDIATE),
    "CGFRL": compare(SIGNED_64, from_gr64(0), SIGNED_WORD_RELATIVE),
    "CGH": compare(SIGNED_64, from_gr64(0), SIGNED_HALFWORD_STORAGE),
    "CGHI": compare(SIGNED_64, from_gr64(0), HALFWORD_IMMEDIATE),
    "CGHRL": compare(SIGNED_64, from_gr64(0), SIGNED_HALFWORD_RELATIVE),
    "CGHSI": compare(
        SIGNED_64, from_first_storage(DOUBLEWORD_BYTES), HALFWORD_IMMEDIATE
    ),
}

LOGICAL_COMPARES: Mapping[str, StatementLowering] = {
    "CL": compare(LOGICAL_32, from_gr32(0), WORD_STORAGE),
    "CLY": compare(LOGICAL_32, from_gr32(0), WORD_STORAGE),
    "CLR": compare(LOGICAL_32, from_gr32(0), from_gr32(1)),
    "CLFI": compare(LOGICAL_32, from_gr32(0), LOGICAL_WORD_IMMEDIATE),
    "CLRL": compare(LOGICAL_32, from_gr32(0), from_relative(WORD_BYTES)),
    "CLHRL": compare(LOGICAL_32, from_gr32(0), from_relative(HALFWORD_BYTES)),
    "CLFHSI": compare(
        LOGICAL_32, from_first_storage(WORD_BYTES), LOGICAL_HALFWORD_IMMEDIATE
    ),
    "CLHHSI": compare(
        LOGICAL_16, from_first_storage(HALFWORD_BYTES), LOGICAL_HALFWORD_IMMEDIATE
    ),
    "CLG": compare(LOGICAL_64, from_gr64(0), DOUBLEWORD_STORAGE),
    "CLGR": compare(LOGICAL_64, from_gr64(0), from_gr64(1)),
    "CLGRL": compare(LOGICAL_64, from_gr64(0), from_relative(DOUBLEWORD_BYTES)),
    "CLGF": compare(LOGICAL_64, from_gr64(0), WORD_STORAGE),
    "CLGFR": compare(LOGICAL_64, from_gr64(0), from_gr32(1)),
    "CLGFI": compare(LOGICAL_64, from_gr64(0), LOGICAL_WORD_IMMEDIATE),
    "CLGFRL": compare(LOGICAL_64, from_gr64(0), from_relative(WORD_BYTES)),
    "CLGHRL": compare(LOGICAL_64, from_gr64(0), from_relative(HALFWORD_BYTES)),
    "CLGHSI": compare(
        LOGICAL_64, from_first_storage(DOUBLEWORD_BYTES), LOGICAL_HALFWORD_IMMEDIATE
    ),
    "CLM": lower_compare_under_mask,
    "CLMY": lower_compare_under_mask,
}

COMPARE_FIELD_LOWERINGS: Mapping[str, FieldLowering] = {
    "CLI": COMPARE_IMMEDIATE_BYTE,
    "CLIY": COMPARE_IMMEDIATE_BYTE,
}

COMPARE_LOWERINGS: Mapping[str, StatementLowering] = {
    **SIGNED_COMPARES,
    **LOGICAL_COMPARES,
    **written_lowerings(COMPARE_FIELD_LOWERINGS),
}
