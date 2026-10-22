# pyright: standard
"""A machine clock that always reads the same TOD clock and CPU timer, so clock instructions store known values."""

from interpreter.hlasm.machine_clock import MachineClock

FIXED_TOD_CLOCK = 0xDE012345_6789ABCD_EF012345_00
FIXED_CPU_TIMER = 0x0000004E_2F1A0000


class FixedMachineClock(MachineClock):
    def tod_clock(self) -> int:
        return FIXED_TOD_CLOCK

    def cpu_timer(self) -> int:
        return FIXED_CPU_TIMER
