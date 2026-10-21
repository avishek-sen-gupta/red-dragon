# pyright: standard
"""An operand address off its boundary is a specification exception: the run abends S0C6."""

from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.hlasm_constants import SPECIFICATION_EXCEPTION_ABEND
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import BranchIf, Label_
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def emit_alignment_check(
    emitter: HlasmEmitter, address: Register, boundary: int
) -> None:
    offset = emitter.binop(BinopKind.BIT_AND, address, emitter.int_(boundary - 1))
    misaligned = emitter.binop(BinopKind.NE, offset, emitter.int_(0))
    abend, aligned = emitter.fresh_label("hl_misaligned"), emitter.fresh_label(
        "hl_aligned"
    )
    emitter.emit_inst(BranchIf(cond_reg=misaligned, branch_targets=(abend, aligned)))
    emitter.emit_inst(Label_(label=abend))
    emit_abend(emitter, SPECIFICATION_EXCEPTION_ABEND)
    emitter.emit_inst(Label_(label=aligned))
