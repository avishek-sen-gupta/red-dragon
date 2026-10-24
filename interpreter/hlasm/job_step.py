# pyright: standard
"""The job-step module: per entry name, a function that builds the PARM list and enters the module as the system would; and the function a linking branch to a stub calls, which calls the unresolved name as a static COBOL CALL would."""

from collections.abc import Sequence

from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.hlasm.binder import Binder
from interpreter.hlasm.binder_start_up import aligned_region, bound_address
from interpreter.hlasm.entry_state import enter_registers
from interpreter.hlasm.hlasm_constants import (
    END_STEP_PREFIX,
    JOB_PARM_BUILTIN,
    JOB_STEP_PREFIX,
    LAST_PARAMETER_BIT,
    MODULE_FUNCTION_PREFIX,
    PARM_LENGTH_BYTES,
    PARM_LIST_BYTES,
    PARM_TEXT_BYTES,
    PROGRAM_ENTRY_PREFIX,
    STUB_CALL_FUNCTION,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import IrFunction
from interpreter.hlasm.placed_name import PlacedName
from interpreter.hlasm.stub_name import StubName
from interpreter.instructions import (
    Branch,
    BranchIf,
    CallWithMemory,
    InstructionBase,
    Label_,
    NewArray,
    Return_,
    StoreField,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register
from interpreter.var_name import VarName

ARGUMENT_COUNT = FieldName("count")


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
    result = emitter.call(FuncName(f"{MODULE_FUNCTION_PREFIX}{entry.module}"), ())
    emitter.emit_inst(Return_(value_reg=result))
    emitter.emit_inst(Label_(label=end))


def _no_arguments(emitter: HlasmEmitter) -> Register:
    arguments = emitter.fresh_reg()
    emitter.emit_inst(NewArray(result_reg=arguments, size_reg=emitter.int_(0)))
    emitter.emit_inst(
        StoreField(
            obj_reg=arguments, field_name=ARGUMENT_COUNT, value_reg=emitter.int_(0)
        )
    )
    return arguments


def _stub_case(emitter: HlasmEmitter, target: Register, stub: StubName) -> None:
    called = emitter.fresh_label("hl_stub_called")
    other = emitter.fresh_label("hl_stub_other")
    matched = emitter.binop(BinopKind.EQ, target, bound_address(emitter, stub))
    emitter.emit_inst(BranchIf(cond_reg=matched, branch_targets=(called, other)))
    emitter.emit_inst(Label_(label=called))
    result = emitter.fresh_reg()
    emitter.emit_inst(
        CallWithMemory(
            result_reg=result,
            location=VarName(f"{PROGRAM_ENTRY_PREFIX}{stub.name.upper()}"),
            memory=_no_arguments(emitter),
        )
    )
    emitter.emit_inst(Return_(value_reg=result))
    emitter.emit_inst(Label_(label=other))


def _stub_call(binder: Binder) -> IrFunction:
    def body(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
        _ = [_stub_case(emitter, parameters[0], stub) for stub in binder.stubs.values()]
        return emitter.int_(0)

    return IrFunction(STUB_CALL_FUNCTION, 1, body)


def job_step_module(binder: Binder) -> tuple[tuple[InstructionBase, ...], IrFunction]:
    emitter = HlasmEmitter("hlasm_job.")
    steps = {
        **{named_step(name): at for name, at in binder.entry_points().items()},
        **{end_step(module): at for module, at in binder.module_entries().items()},
    }
    _ = [_job_step(emitter, stem, entry) for stem, entry in steps.items()]
    stub_call = _stub_call(binder)
    stub_call.define(emitter)
    return emitter.instructions(), stub_call
