# pyright: standard
"""Runs IR with branches through the VM's instruction executor, from the first instruction to a halt or the end."""

from collections.abc import Mapping, Sequence

from interpreter.func_name import FuncName
from interpreter.instructions import Halt_, InstructionBase, Label_
from interpreter.ir import CodeLabel
from interpreter.vm.executor import (
    HandlerContext,
    LocalExecutor,
    _default_handler_context,
)
from interpreter.vm.vm import apply_update
from interpreter.vm.vm_types import StackFrame, VMState


def _step(
    instructions: Sequence[InstructionBase],
    labels: Mapping[CodeLabel, int],
    vm: VMState,
    ctx: HandlerContext,
    at: int,
) -> VMState:
    if at >= len(instructions) or isinstance(instructions[at], Halt_):
        return vm
    update = LocalExecutor.execute(inst=instructions[at], vm=vm, ctx=ctx).update
    apply_update(vm, update)
    following = labels[update.next_label] if update.next_label else at + 1
    return _step(instructions, labels, vm, ctx, following)


def run_branching(instructions: Sequence[InstructionBase]) -> VMState:
    vm = VMState(call_stack=[StackFrame(function_name=FuncName("test"))])
    labels = {
        inst.label: at
        for at, inst in enumerate(instructions)
        if isinstance(inst, Label_)
    }
    return _step(instructions, labels, vm, _default_handler_context(), 0)
