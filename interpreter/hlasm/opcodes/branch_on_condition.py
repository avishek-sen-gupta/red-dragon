# pyright: standard
"""Branch on condition: BC, BCR, BIC, BRC, BRCL, and the branch-prediction hints BPP and BPRP."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.branch_dispatch import emit_branch
from interpreter.hlasm.data_movement import (
    from_gr32,
    from_storage,
    relative_target,
    storage_address,
)
from interpreter.hlasm.hlasm_constants import CC_VAR, DOUBLEWORD_BYTES
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import mask_operand, reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import BranchIf, Label_
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Target = Callable[[HlasmEmitter, MachineStatement], Register]
type MaskedBranch = Callable[[HlasmEmitter, MachineStatement, int, Target], None]

CC_MASK_TOP = 8
NEVER = 0
ALWAYS = 15
MASK_OPERAND = 0
NO_BRANCH_REGISTER = 0


def _selected(emitter: HlasmEmitter, mask: int) -> Register:
    shifted = emitter.binop(
        BinopKind.RSHIFT, emitter.int_(CC_MASK_TOP), emitter.load_var(CC_VAR)
    )
    selected = emitter.binop(BinopKind.BIT_AND, shifted, emitter.int_(mask))
    return emitter.binop(BinopKind.NE, selected, emitter.int_(0))


def _conditional(
    emitter: HlasmEmitter, statement: MachineStatement, mask: int, target: Target
) -> None:
    taken_label = emitter.fresh_label("hl_bc_taken")
    fall_label = emitter.fresh_label("hl_bc_fall")
    emitter.emit_inst(
        BranchIf(
            cond_reg=_selected(emitter, mask),
            branch_targets=(taken_label, fall_label),
        )
    )
    emitter.emit_inst(Label_(label=taken_label))
    emit_branch(emitter, target(emitter, statement))
    emitter.emit_inst(Label_(label=fall_label))


def _never(
    emitter: HlasmEmitter, statement: MachineStatement, mask: int, target: Target
) -> None:
    return


def _always(
    emitter: HlasmEmitter, statement: MachineStatement, mask: int, target: Target
) -> None:
    emit_branch(emitter, target(emitter, statement))


_UNTESTED_MASKS: Mapping[int, MaskedBranch] = {NEVER: _never, ALWAYS: _always}


def _on_condition(target: Target) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        mask = mask_operand(statement, MASK_OPERAND)
        _UNTESTED_MASKS.get(mask, _conditional)(emitter, statement, mask, target)

    return lower


_bcr_on_condition = _on_condition(from_gr32(1))


def lower_bcr(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    if reg_operand(statement, 1) == NO_BRANCH_REGISTER:
        return
    _bcr_on_condition(emitter, statement)


def lower_branch_prediction(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    return


BRANCH_ON_CONDITION_LOWERINGS: Mapping[str, StatementLowering] = {
    "BC": _on_condition(storage_address),
    "BCR": lower_bcr,
    "BIC": _on_condition(from_storage(DOUBLEWORD_BYTES)),
    "BRC": _on_condition(relative_target),
    "BRCL": _on_condition(relative_target),
    "BPP": lower_branch_prediction,
    "BPRP": lower_branch_prediction,
}
