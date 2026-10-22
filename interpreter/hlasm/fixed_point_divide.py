# pyright: standard
"""A zero divisor or a quotient out of range is a fixed-point-divide exception, which no mask suppresses: the run abends S0C9."""

from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.hlasm_constants import FIXED_POINT_DIVIDE_ABEND
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import BranchIf, Label_
from interpreter.register import Register


def emit_fixed_point_divide_check(emitter: HlasmEmitter, raised: Register) -> None:
    interrupt, completed = emitter.fresh_label(
        "hl_fixed_point_divide"
    ), emitter.fresh_label("hl_no_fixed_point_divide")
    emitter.emit_inst(BranchIf(cond_reg=raised, branch_targets=(interrupt, completed)))
    emitter.emit_inst(Label_(label=interrupt))
    emit_abend(emitter, FIXED_POINT_DIVIDE_ABEND)
    emitter.emit_inst(Label_(label=completed))
