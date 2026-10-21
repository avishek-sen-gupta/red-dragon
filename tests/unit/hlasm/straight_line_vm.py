# pyright: standard
"""Runs straight-line IR through the VM's instruction executor."""

from collections.abc import Mapping, Sequence

from interpreter.func_name import FuncName
from interpreter.instructions import InstructionBase
from interpreter.register import Register
from interpreter.types.typed_value import TypedValue, typed_from_runtime, unwrap
from interpreter.vm.executor import LocalExecutor, _default_handler_context
from interpreter.vm.vm import apply_update
from interpreter.vm.vm_types import StackFrame, VMState


def run_straight_line(
    instructions: Sequence[InstructionBase], parameters: Mapping[str, int]
) -> VMState:
    vm = VMState(
        call_stack=[
            StackFrame(
                function_name=FuncName("test"),
                registers={
                    Register(name): typed_from_runtime(value)
                    for name, value in parameters.items()
                },
            )
        ]
    )
    ctx = _default_handler_context()
    for inst in instructions:
        apply_update(vm, LocalExecutor.execute(inst=inst, vm=vm, ctx=ctx).update)
    return vm


def returned_value(
    instructions: Sequence[InstructionBase], parameters: Mapping[str, int]
) -> int | list[int]:
    vm = run_straight_line(instructions[:-1], parameters)
    result = LocalExecutor.execute(
        inst=instructions[-1], vm=vm, ctx=_default_handler_context()
    )
    return unwrap(result.update.return_value)


def register_value(vm: VMState, register: Register) -> TypedValue:
    return vm.current_frame.registers[register]
