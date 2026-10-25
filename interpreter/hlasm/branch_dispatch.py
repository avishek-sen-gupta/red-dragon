# pyright: standard
"""Computed branches: a module activation maps a target in its own sections back to its statement's label, returns at its R14 otherwise, and hands any other target to the far branch."""

from collections.abc import Sequence

from hlasm_asg.program.cnop_statement import CnopStatement
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.section import Section
from hlasm_asg.program.section_kind import SectionKind
from interpreter.constants import PARAM_PREFIX
from interpreter.func_name import FuncName
from interpreter.hlasm.far_branch import FarBranch
from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    BELOW_VAR,
    DISPATCH_LABEL,
    ENTRY_TARGET_VAR,
    FAR_BRANCH_FUNCTION,
    LINK_DISPATCH_LABEL,
    LINK_REGISTER,
    LINKING_VAR,
    LOCAL_DISPATCH_LABEL,
    MODULE_BIT_PREFIX,
    RETURN_CODE_REGISTER,
    RETURN_LABEL,
    RETURN_SENTINEL,
    RETURN_TO_VAR,
    TARGET_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import (
    Branch,
    BranchIf,
    DeclVar,
    Label_,
    Return_,
    StoreVar,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register
from interpreter.var_name import VarName


def statement_label(section: str, offset: int) -> CodeLabel:
    return CodeLabel(f"hl_{section}_{offset}")


def emit_branch(emitter: HlasmEmitter, target: Register) -> None:
    emitter.emit_inst(StoreVar(name=TARGET_VAR, value_reg=target))
    emitter.emit_inst(Branch(label=DISPATCH_LABEL))


def emit_link_branch(emitter: HlasmEmitter, target: Register) -> None:
    emitter.emit_inst(StoreVar(name=TARGET_VAR, value_reg=target))
    emitter.emit_inst(Branch(label=LINK_DISPATCH_LABEL))


def _branch_if(
    emitter: HlasmEmitter, condition: Register, taken: CodeLabel, prefix: str
) -> None:
    fall = emitter.fresh_label(prefix)
    emitter.emit_inst(BranchIf(cond_reg=condition, branch_targets=(taken, fall)))
    emitter.emit_inst(Label_(label=fall))


def _offset_case(
    emitter: HlasmEmitter, offset: Register, case: tuple[str, int]
) -> None:
    section, at = case
    matched = emitter.binop(BinopKind.EQ, offset, emitter.int_(at))
    _branch_if(emitter, matched, statement_label(section, at), "hl_dispatch_next")


def _section_chain(
    emitter: HlasmEmitter, target: Register, case: tuple[str, Sequence[int]]
) -> None:
    section, offsets = case
    offset = emitter.binop(BinopKind.SUB, target, emitter.section_base(section))
    _ = [_offset_case(emitter, offset, (section, at)) for at in offsets]


def _machine_offsets(program: HlasmProgram, section: Section) -> tuple[int, ...]:
    machines = {
        s.offset
        for s in program.statements
        if isinstance(s, MachineStatement) and s.section == section.name
    }
    no_ops = {
        at
        for s in program.statements
        if isinstance(s, CnopStatement) and s.section == section.name
        for at in s.no_ops()
    }
    return tuple(sorted(machines | no_ops))


def _emit_return(emitter: HlasmEmitter) -> None:
    emitter.emit_inst(Label_(label=RETURN_LABEL))
    emitter.emit_inst(Return_(value_reg=emitter.load_gr32(RETURN_CODE_REGISTER)))


def _masked_target(emitter: HlasmEmitter) -> Register:
    raw = emitter.load_var(TARGET_VAR)
    return emitter.binop(BinopKind.BIT_AND, raw, emitter.int_(ADDRESS_MASK_31))


def returns(emitter: HlasmEmitter, masked: Register) -> Register:
    own = emitter.binop(BinopKind.EQ, masked, emitter.load_var(RETURN_TO_VAR))
    system = emitter.binop(BinopKind.EQ, masked, emitter.int_(RETURN_SENTINEL))
    return emitter.binop(BinopKind.OR, own, system)


def _declare_parameter(emitter: HlasmEmitter, name: VarName) -> Register:
    value = emitter.fresh_reg()
    emitter.emit_inst(Symbolic(result_reg=value, hint=f"{PARAM_PREFIX}{name}"))
    emitter.emit_inst(DeclVar(name=name, value_reg=value))
    return value


def emit_activation(emitter: HlasmEmitter) -> None:
    target = _declare_parameter(emitter, ENTRY_TARGET_VAR)
    _declare_parameter(emitter, BELOW_VAR)
    link = emitter.load_gr32(LINK_REGISTER)
    masked = emitter.binop(BinopKind.BIT_AND, link, emitter.int_(ADDRESS_MASK_31))
    emitter.emit_inst(DeclVar(name=RETURN_TO_VAR, value_reg=masked))
    emit_branch(emitter, target)


def _set_linking(emitter: HlasmEmitter, linking: int) -> None:
    emitter.emit_inst(StoreVar(name=LINKING_VAR, value_reg=emitter.int_(linking)))


def _emit_far_branch(emitter: HlasmEmitter, module: str) -> None:
    request = FarBranch(
        _masked_target(emitter),
        emitter.load_var(BELOW_VAR),
        emitter.load_var(VarName(f"{MODULE_BIT_PREFIX}{module}")),
        emitter.load_var(LINKING_VAR),
    )
    returning = emitter.call(FuncName(FAR_BRANCH_FUNCTION), request.arguments())
    emitter.emit_inst(
        BranchIf(cond_reg=returning, branch_targets=(RETURN_LABEL, DISPATCH_LABEL))
    )


def _emit_entries(emitter: HlasmEmitter) -> None:
    emitter.emit_inst(Label_(label=LINK_DISPATCH_LABEL))
    _set_linking(emitter, 1)
    emitter.emit_inst(Branch(label=LOCAL_DISPATCH_LABEL))
    emitter.emit_inst(Label_(label=DISPATCH_LABEL))
    _set_linking(emitter, 0)
    emitter.emit_inst(Label_(label=LOCAL_DISPATCH_LABEL))


def _emit_return_check(emitter: HlasmEmitter) -> None:
    returning = returns(emitter, _masked_target(emitter))
    _branch_if(emitter, returning, RETURN_LABEL, "hl_dispatch_far")


def emit_dispatch(emitter: HlasmEmitter, program: HlasmProgram, module: str) -> None:
    _emit_entries(emitter)
    target = _masked_target(emitter)
    _ = [
        _section_chain(emitter, target, (s.name, _machine_offsets(program, s)))
        for s in program.sections
        if s.kind != SectionKind.DSECT
    ]
    _emit_return_check(emitter)
    _emit_far_branch(emitter, module)
    _emit_return(emitter)
