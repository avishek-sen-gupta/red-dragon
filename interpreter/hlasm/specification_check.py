# pyright: standard
"""A raised specification condition abends S0C6 before the instruction changes anything."""

from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.hlasm_constants import SPECIFICATION_EXCEPTION_ABEND
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import BranchIf, Label_
from interpreter.register import Register


def emit_specification_check(emitter: HlasmEmitter, raised: Register) -> None:
    abend, valid = emitter.fresh_label("hl_specification"), emitter.fresh_label(
        "hl_specified"
    )
    emitter.emit_inst(BranchIf(cond_reg=raised, branch_targets=(abend, valid)))
    emitter.emit_inst(Label_(label=abend))
    emit_abend(emitter, SPECIFICATION_EXCEPTION_ABEND)
    emitter.emit_inst(Label_(label=valid))
