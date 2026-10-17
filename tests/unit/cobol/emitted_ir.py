"""Runs the IR a lowering emitted into an EmitContext, branches included, and returns one register's value."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from itertools import accumulate

from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.func_name import FuncName
from interpreter.instructions import InstructionBase, Label_, Return_
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.types.typed_value import typed_from_runtime, unwrap
from interpreter.vm.executor import LocalExecutor, _default_handler_context
from interpreter.vm.vm import VMState, apply_update
from interpreter.vm.vm_types import StackFrame, SymbolicValue

_STEP_LIMIT = 100_000
_FALL_THROUGH = CodeLabel("")

type ParamValue = str | int | bool | Decimal | SymbolicValue | list[int]


def run_emitted(
    emit: Callable[[IrEmitter, tuple[Register, ...]], Register],
    params: tuple[ParamValue, ...],
) -> ParamValue:
    """Emit IR with ``emit`` over registers preloaded with ``params``, run it
    through the VM, and return the value of the register ``emit`` returned."""
    (value,) = run_emitted_values(lambda e, registers: (emit(e, registers),), params)
    return value


def run_emitted_values(
    emit: Callable[[IrEmitter, tuple[Register, ...]], tuple[Register, ...]],
    params: tuple[ParamValue, ...],
) -> tuple[ParamValue, ...]:
    """Like ``run_emitted`` for an emitter that leaves several results."""
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    registers = tuple(ctx.fresh_reg() for _ in params)
    results = emit(IrEmitter(ctx=ctx, span=None), registers)
    ctx.emit_inst(Return_(value_reg=results[0]))
    vm = VMState(
        call_stack=[
            StackFrame(
                function_name=FuncName("emitted"),
                registers={
                    register: typed_from_runtime(value)
                    for register, value in zip(registers, params, strict=True)
                },
            )
        ]
    )
    _run_to_return(ctx.instructions, vm)
    return tuple(unwrap(vm.call_stack[-1].registers[result]) for result in results)


def _run_to_return(instructions: Sequence[InstructionBase], vm: VMState) -> None:
    labels: Mapping[CodeLabel, int] = {
        inst.label: index
        for index, inst in enumerate(instructions)
        if isinstance(inst, Label_)
    }
    handlers = _default_handler_context()

    def step(pc: int, _count: int) -> int:
        inst = instructions[pc]
        if isinstance(inst, Label_):
            return pc + 1
        outcome = LocalExecutor.execute(inst=inst, vm=vm, ctx=handlers)
        assert outcome.handled, f"Instruction not handled: {inst}"
        apply_update(vm, outcome.update)
        return labels.get(outcome.update.next_label or _FALL_THROUGH, pc + 1)

    next(
        pc
        for pc in accumulate(range(_STEP_LIMIT), step, initial=0)
        if isinstance(instructions[pc], Return_)
    )
