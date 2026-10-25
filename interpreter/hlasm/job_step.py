# pyright: standard
"""The job-step module: per entry name, a function that builds the PARM list and enters the module as the system would, and a COBOL entry `__entry_<NAME>` that enters it from a COBOL CALL; and the far branch, which finds a target's owner in the far-branch table and calls it, or tells the activation to return."""

from collections.abc import Sequence
from dataclasses import fields

from interpreter.func_name import FuncName
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.binder import Binder
from interpreter.hlasm.binder_start_up import aligned_region, bound_address
from interpreter.hlasm.branch_owner import BranchOwner
from interpreter.hlasm.cobol_linkage import cobol_entry, emit_cobol_call
from interpreter.hlasm.cobol_owner import CobolOwner
from interpreter.hlasm.entry_state import enter_registers
from interpreter.hlasm.far_branch import FarBranch
from interpreter.hlasm.far_branch_entry import FarBranchEntry
from interpreter.hlasm.hlasm_constants import (
    END_STEP_PREFIX,
    ENTRY_ADDRESS_REGISTER,
    FAR_BRANCH_CALLED,
    FAR_BRANCH_FUNCTION,
    FAR_BRANCH_RETURNING,
    JOB_STEP_PREFIX,
    LAST_PARAMETER_BIT,
    LINK_REGISTER,
    MODULE_BIT_PREFIX,
    MODULE_FUNCTION_PREFIX,
    NOTHING_BELOW,
    OPERATION_EXCEPTION_ABEND,
    PARM_LIST_BYTES,
    RETURN_CODE_REGISTER,
    TARGET_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import IrFunction, define_called
from interpreter.hlasm.module_owner import ModuleOwner
from interpreter.hlasm.placed_name import PlacedName
from interpreter.hlasm.program_entry import program_entry_name
from interpreter.hlasm.program_function import ProgramFunction
from interpreter.hlasm.unresolved_call import emit_unresolved_call
from interpreter.hlasm.unresolved_owner import UnresolvedOwner
from interpreter.hlasm_run_inputs.run_input_names import (
    JOB_PARM_BUILTIN,
    PARM_LENGTH_BYTES,
    PARM_TEXT_BYTES,
)
from interpreter.instructions import (
    Branch,
    BranchIf,
    InstructionBase,
    Label_,
    Return_,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register
from interpreter.var_name import VarName

FAR_BRANCH_ARITY = len(fields(FarBranch))


def job_step_label(stem: str) -> CodeLabel:
    return CodeLabel(f"func_{stem}_0")


def named_step(name: str) -> str:
    return f"{JOB_STEP_PREFIX}{name}"


def end_step(module: str) -> str:
    return f"{END_STEP_PREFIX}{module}"


def _parm_list(emitter: HlasmEmitter) -> Register:
    area = PARM_LENGTH_BYTES + PARM_TEXT_BYTES
    region = aligned_region(emitter, emitter.int_(PARM_LIST_BYTES + area))
    text = emitter.binop(BinopKind.ADD, region, emitter.int_(PARM_LIST_BYTES))
    last = emitter.binop(BinopKind.BIT_OR, text, emitter.int_(LAST_PARAMETER_BIT))
    emitter.store_storage(region, 0, PARM_LIST_BYTES, last)
    image = emitter.call(JOB_PARM_BUILTIN, ())
    emitter.write_bytes(region, emitter.int_(PARM_LIST_BYTES), area, image)
    return region


def _job_step(emitter: HlasmEmitter, stem: str, entry: PlacedName) -> None:
    end = CodeLabel(f"end_{stem}_1")
    emitter.emit_inst(Branch(label=end))
    emitter.emit_inst(Label_(label=job_step_label(stem)))
    parameters = _parm_list(emitter)
    enter_registers(emitter, bound_address(emitter, entry), parameters)
    result = emitter.call(
        FuncName(f"{MODULE_FUNCTION_PREFIX}{entry.module}"),
        (emitter.load_gr32(ENTRY_ADDRESS_REGISTER), emitter.int_(NOTHING_BELOW)),
    )
    emitter.emit_inst(Return_(value_reg=result))
    emitter.emit_inst(Label_(label=end))


def _call_by_name(emitter: HlasmEmitter, owner: UnresolvedOwner) -> None:
    result = emit_unresolved_call(emitter, VarName(program_entry_name(owner.name)))
    emitter.store_gr32(RETURN_CODE_REGISTER, result)
    emitter.emit_inst(
        StoreVar(name=TARGET_VAR, value_reg=emitter.load_gr32(LINK_REGISTER))
    )
    emitter.emit_inst(Return_(value_reg=emitter.int_(FAR_BRANCH_CALLED)))


def _when(emitter: HlasmEmitter, condition: Register, prefix: str) -> CodeLabel:
    taken, other = emitter.fresh_label(prefix), emitter.fresh_label(f"{prefix}_not")
    emitter.emit_inst(BranchIf(cond_reg=condition, branch_targets=(taken, other)))
    emitter.emit_inst(Label_(label=taken))
    return other


def _refuse_own(emitter: HlasmEmitter, request: FarBranch, bit: Register) -> None:
    own = _when(emitter, emitter.binop(BinopKind.EQ, request.me, bit), "hl_far_own")
    emit_abend(emitter, OPERATION_EXCEPTION_ABEND)
    emitter.emit_inst(Label_(label=own))


def _call_module(emitter: HlasmEmitter, request: FarBranch, module: str) -> None:
    bit = emitter.load_var(VarName(f"{MODULE_BIT_PREFIX}{module}"))
    _refuse_own(emitter, request, bit)
    held = emitter.binop(
        BinopKind.NE,
        emitter.binop(BinopKind.BIT_AND, request.below, bit),
        emitter.int_(0),
    )
    plain = emitter.binop(BinopKind.EQ, request.linking, emitter.int_(0))
    below = _when(emitter, emitter.binop(BinopKind.AND, held, plain), "hl_far_below")
    emitter.emit_inst(Return_(value_reg=emitter.int_(FAR_BRANCH_RETURNING)))
    emitter.emit_inst(Label_(label=below))
    stack = emitter.binop(BinopKind.BIT_OR, request.below, request.me)
    emitter.call(FuncName(f"{MODULE_FUNCTION_PREFIX}{module}"), (request.target, stack))
    emitter.emit_inst(Return_(value_reg=emitter.int_(FAR_BRANCH_CALLED)))


def _call_program(emitter: HlasmEmitter, owner: UnresolvedOwner | CobolOwner) -> None:
    match owner:
        case UnresolvedOwner() as unresolved:
            _call_by_name(emitter, unresolved)
        case CobolOwner(program=program):
            emit_cobol_call(emitter, program)


def _call_owner(emitter: HlasmEmitter, request: FarBranch, owner: BranchOwner) -> None:
    match owner:
        case ModuleOwner(module=module):
            _call_module(emitter, request, module)
        case UnresolvedOwner() | CobolOwner() as program:
            _call_program(emitter, program)


def _far_case(emitter: HlasmEmitter, request: FarBranch, entry: FarBranchEntry) -> None:
    low = bound_address(emitter, entry.start)
    high = emitter.binop(BinopKind.ADD, low, emitter.int_(entry.length))
    inside = emitter.binop(
        BinopKind.AND,
        emitter.binop(BinopKind.GE, request.target, low),
        emitter.binop(BinopKind.LT, request.target, high),
    )
    other = _when(emitter, inside, "hl_far_owner")
    _call_owner(emitter, request, entry.owner)
    emitter.emit_inst(Label_(label=other))


def _far_branch(binder: Binder) -> IrFunction:
    def body(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
        request = FarBranch(*parameters)
        _ = [_far_case(emitter, request, e) for e in binder.far_branch_table()]
        emit_abend(emitter, OPERATION_EXCEPTION_ABEND)
        return emitter.int_(FAR_BRANCH_CALLED)

    return IrFunction(FAR_BRANCH_FUNCTION, FAR_BRANCH_ARITY, body)


def _defined(
    emitter: HlasmEmitter, functions: tuple[ProgramFunction, ...]
) -> tuple[ProgramFunction, ...]:
    _ = [function.define(emitter) for function in functions]
    return define_called(emitter, functions)


def job_step_module(
    binder: Binder,
) -> tuple[tuple[InstructionBase, ...], tuple[ProgramFunction, ...]]:
    emitter = HlasmEmitter("hlasm_job.")
    steps = {
        **{named_step(name): at for name, at in binder.entry_points().items()},
        **{end_step(module): at for module, at in binder.module_entries().items()},
    }
    _ = [_job_step(emitter, stem, entry) for stem, entry in steps.items()]
    defined = _defined(
        emitter,
        (
            _far_branch(binder),
            *(cobol_entry(name, at) for name, at in binder.entry_points().items()),
        ),
    )
    return emitter.instructions(), defined
