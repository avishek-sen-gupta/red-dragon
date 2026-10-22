# pyright: standard
"""The machine clock read from the host: the TOD clock from wall time since 1900, the CPU timer counting down by process CPU time."""

from collections.abc import Callable
from dataclasses import dataclass

from interpreter.hlasm.machine_clock import MachineClock

UNIX_EPOCH_AFTER_TOD_EPOCH_NS = 2_208_988_800 * 1_000_000_000
TOD_FRACTION_BITS = 52
NS_PER_MICROSECOND = 1_000
CPU_TIMER_START = (1 << 63) - 1
CPU_TIMER_UNITS_PER_MICROSECOND = 4_096


@dataclass(frozen=True)
class SystemMachineClock(MachineClock):
    wall_ns: Callable[[], int]
    cpu_ns: Callable[[], int]

    def tod_clock(self) -> int:
        since_tod_epoch = self.wall_ns() + UNIX_EPOCH_AFTER_TOD_EPOCH_NS
        return (since_tod_epoch << TOD_FRACTION_BITS) // NS_PER_MICROSECOND

    def cpu_timer(self) -> int:
        used = self.cpu_ns() * CPU_TIMER_UNITS_PER_MICROSECOND // NS_PER_MICROSECOND
        return CPU_TIMER_START - used
