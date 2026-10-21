# pyright: standard
"""An overflow with the program mask's fixed-point-overflow bit on is a fixed-point-overflow interruption: the run abends S0C8."""

from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.hlasm_constants import (
    FIXED_POINT_OVERFLOW_ABEND,
    FIXED_POINT_OVERFLOW_MASK,
    OVERFLOW_CC,
    PROGRAM_MASK_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import BranchIf, Label_
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def emit_fixed_point_overflow_check(emitter: HlasmEmitter, cc: Register) -> None:
    overflow = emitter.binop(BinopKind.EQ, cc, emitter.int_(OVERFLOW_CC))
    selected = emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_var(PROGRAM_MASK_VAR),
        emitter.int_(FIXED_POINT_OVERFLOW_MASK),
    )
    enabled = emitter.binop(BinopKind.NE, selected, emitter.int_(0))
    trapped = emitter.binop(BinopKind.AND, overflow, enabled)
    interrupt, completed = emitter.fresh_label(
        "hl_fixed_point_overflow"
    ), emitter.fresh_label("hl_no_fixed_point_overflow")
    emitter.emit_inst(BranchIf(cond_reg=trapped, branch_targets=(interrupt, completed)))
    emitter.emit_inst(Label_(label=interrupt))
    emit_abend(emitter, FIXED_POINT_OVERFLOW_ABEND)
    emitter.emit_inst(Label_(label=completed))
