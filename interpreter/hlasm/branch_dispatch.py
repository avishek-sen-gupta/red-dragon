# pyright: standard
"""Computed branches: a target address is mapped back to its statement's label."""

from collections.abc import Sequence

from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.section import Section
from hlasm_asg.program.section_kind import SectionKind
from interpreter.func_name import FuncName
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    DISPATCH_LABEL,
    LINK_DISPATCH_LABEL,
    LINK_REGISTER,
    OPERATION_EXCEPTION_ABEND,
    RETURN_CODE_REGISTER,
    RETURN_LABEL,
    RETURN_SENTINEL,
    STUB_CALL_FUNCTION,
    STUB_CALL_LABEL,
    STUBS_HIGH_VAR,
    STUBS_LOW_VAR,
    TARGET_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import Branch, BranchIf, Label_, Return_, StoreVar
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


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
    return tuple(
        sorted(
            {
                s.offset
                for s in program.statements
                if isinstance(s, MachineStatement) and s.section == section.name
            }
        )
    )


def _emit_return(emitter: HlasmEmitter) -> None:
    emitter.emit_inst(Label_(label=RETURN_LABEL))
    emitter.emit_inst(Return_(value_reg=emitter.load_gr32(RETURN_CODE_REGISTER)))


def _in_stub_range(emitter: HlasmEmitter, target: Register) -> Register:
    above = emitter.binop(BinopKind.GE, target, emitter.load_var(STUBS_LOW_VAR))
    below = emitter.binop(BinopKind.LT, target, emitter.load_var(STUBS_HIGH_VAR))
    return emitter.binop(BinopKind.AND, above, below)


def _emit_link_dispatch(emitter: HlasmEmitter) -> None:
    emitter.emit_inst(Label_(label=LINK_DISPATCH_LABEL))
    raw = emitter.load_var(TARGET_VAR)
    target = emitter.binop(BinopKind.BIT_AND, raw, emitter.int_(ADDRESS_MASK_31))
    stub = _in_stub_range(emitter, target)
    emitter.emit_inst(
        BranchIf(cond_reg=stub, branch_targets=(STUB_CALL_LABEL, DISPATCH_LABEL))
    )
    emitter.emit_inst(Label_(label=STUB_CALL_LABEL))
    result = emitter.call(FuncName(STUB_CALL_FUNCTION), (target,))
    emitter.store_gr32(RETURN_CODE_REGISTER, result)
    emit_branch(emitter, emitter.load_gr32(LINK_REGISTER))


def emit_dispatch(emitter: HlasmEmitter, program: HlasmProgram) -> None:
    _emit_link_dispatch(emitter)
    emitter.emit_inst(Label_(label=DISPATCH_LABEL))
    raw = emitter.load_var(TARGET_VAR)
    target = emitter.binop(BinopKind.BIT_AND, raw, emitter.int_(ADDRESS_MASK_31))
    returning = emitter.binop(BinopKind.EQ, target, emitter.int_(RETURN_SENTINEL))
    _branch_if(emitter, returning, RETURN_LABEL, "hl_dispatch_sections")
    _ = [
        _section_chain(emitter, target, (s.name, _machine_offsets(program, s)))
        for s in program.sections
        if s.kind != SectionKind.DSECT
    ]
    emit_abend(emitter, OPERATION_EXCEPTION_ABEND)
    _emit_return(emitter)
