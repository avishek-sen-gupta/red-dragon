# pyright: standard
"""Test under mask opcodes: the selected bits of a storage byte or a register halfword set the CC; nothing is stored."""

from collections.abc import Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_one_layouts import IMMEDIATE_BYTE
from interpreter.hlasm.data_movement import Source, field_of, immediate
from interpreter.hlasm.field_lowering import (
    FieldLowering,
    with_field_source,
    written_lowerings,
)
from interpreter.hlasm.fixed_width_ir import (
    build_test_under_mask_cc_ir,
    build_test_under_mask_ranked_cc_ir,
)
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    HALFWORD_BITS,
    ONE_BYTE,
    PARAM_LEFT,
    PARAM_RIGHT,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_ir
from interpreter.hlasm.opcodes.compare import from_first_storage
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import InstructionBase

BYTE_TEST = build_test_under_mask_cc_ir("hlasm.tm8", BITS_PER_BYTE)
HALFWORD_TEST = build_test_under_mask_ranked_cc_ir("hlasm.tm16", HALFWORD_BITS)

HIGH_HIGH_SHIFT = 48
HIGH_LOW_SHIFT = 32
LOW_HIGH_SHIFT = 16
LOW_LOW_SHIFT = 0


def _test(
    test: Sequence[InstructionBase], value: Source, mask: Source
) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        arguments = {
            PARAM_LEFT: value(emitter, statement),
            PARAM_RIGHT: mask(emitter, statement),
        }
        emitter.set_cc(inline_ir(emitter, test, arguments))

    return lower


TEST_BYTE = FieldLowering(
    IMMEDIATE_BYTE,
    with_field_source(
        lambda mask: _test(BYTE_TEST, from_first_storage(ONE_BYTE), mask)
    ),
)


def _halfword(shift: int) -> StatementLowering:
    return _test(
        HALFWORD_TEST, field_of(HALFWORD_BITS, shift), immediate(HALFWORD_BITS)
    )


TEST_UNDER_MASK_FIELD_LOWERINGS: Mapping[str, FieldLowering] = {
    "TM": TEST_BYTE,
    "TMY": TEST_BYTE,
}

TEST_UNDER_MASK_LOWERINGS: Mapping[str, StatementLowering] = {
    **written_lowerings(TEST_UNDER_MASK_FIELD_LOWERINGS),
    "TMHH": _halfword(HIGH_HIGH_SHIFT),
    "TMHL": _halfword(HIGH_LOW_SHIFT),
    "TMLH": _halfword(LOW_HIGH_SHIFT),
    "TMH": _halfword(LOW_HIGH_SHIFT),
    "TMLL": _halfword(LOW_LOW_SHIFT),
    "TML": _halfword(LOW_LOW_SHIFT),
}
