# pyright: standard
"""The TOD clock and CPU timer builtins over an injected machine clock; irreducible, since they read outside the program."""

from collections.abc import Mapping, Sequence

from interpreter.func_name import FuncName
from interpreter.hlasm.hlasm_constants import CPU_TIMER_BUILTIN, TOD_CLOCK_BUILTIN
from interpreter.hlasm.machine_clock import MachineClock
from interpreter.types.typed_value import TypedValue
from interpreter.vm.builtin import Builtin
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult


def clock_builtins(clock: MachineClock) -> Mapping[FuncName, Builtin]:
    def tod_clock(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        return BuiltinResult(value=clock.tod_clock())

    def cpu_timer(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        return BuiltinResult(value=clock.cpu_timer())

    return {TOD_CLOCK_BUILTIN: tod_clock, CPU_TIMER_BUILTIN: cpu_timer}
