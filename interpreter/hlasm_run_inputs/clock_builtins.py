# pyright: standard
"""The TOD clock, CPU timer and interval wait builtins over an injected machine clock; irreducible, since they reach outside the program."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from interpreter.func_name import FuncName
from interpreter.hlasm_run_inputs.machine_clock import MachineClock
from interpreter.hlasm_run_inputs.run_input_names import (
    CPU_TIMER_BUILTIN,
    TOD_CLOCK_BUILTIN,
    WAIT_BUILTIN,
)
from interpreter.types.typed_value import TypedValue
from interpreter.vm.builtin import Builtin
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult


@dataclass(frozen=True)
class _ClockBuiltins:
    clock: MachineClock

    def tod_clock(self, args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        return BuiltinResult(value=self.clock.tod_clock())

    def cpu_timer(self, args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        return BuiltinResult(value=self.clock.cpu_timer())

    def wait(self, args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        self.clock.wait(int(args[0].value))
        return BuiltinResult(value=None)


def clock_builtins(clock: MachineClock) -> Mapping[FuncName, Builtin]:
    builtins = _ClockBuiltins(clock)
    return {
        TOD_CLOCK_BUILTIN: builtins.tod_clock,
        CPU_TIMER_BUILTIN: builtins.cpu_timer,
        WAIT_BUILTIN: builtins.wait,
    }
