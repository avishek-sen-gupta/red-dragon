# pyright: standard
"""Seed opcodes: LR, and the linking branches BASR, BALR and BRAS."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.branch_dispatch import emit_branch
from interpreter.hlasm.effective_address import relative_address
from interpreter.hlasm.hlasm_constants import AMODE_31_LINK_BIT
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import reg_operand, reloc_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.storage_layout import section_var
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def lower_lr(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    emitter.store_gr32(
        reg_operand(statement, 0), emitter.load_gr32(reg_operand(statement, 1))
    )


def _next_address(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    base = emitter.load_var(section_var(statement.section))
    after = emitter.int_(statement.offset + statement.length)
    return emitter.binop(BinopKind.ADD, base, after)


def _link(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    link = emitter.binop(
        BinopKind.BIT_OR,
        _next_address(emitter, statement),
        emitter.int_(AMODE_31_LINK_BIT),
    )
    emitter.store_gr32(reg_operand(statement, 0), link)


def lower_branch_and_link(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    r2 = reg_operand(statement, 1)
    target = emitter.load_gr32(r2)
    _link(emitter, statement)
    if r2 == 0:
        return
    emit_branch(emitter, target)


def lower_bras(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    target = relative_address(emitter, reloc_operand(statement, 1))
    _link(emitter, statement)
    emit_branch(emitter, target)


SEED_LOWERINGS: Mapping[str, StatementLowering] = {
    "LR": lower_lr,
    "BASR": lower_branch_and_link,
    "BALR": lower_branch_and_link,
    "BRAS": lower_bras,
}
