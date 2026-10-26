# pyright: standard
"""The system machine clock turns host readings into a 104-bit TOD clock since 1900 and a CPU timer counting down from the top."""

import time

from interpreter.hlasm_run_inputs.system_machine_clock import SystemMachineClock
from tests.covers import NotLanguageFeature, covers

START_OF_1972_UNIX_NS = 63_072_000 * 1_000_000_000
START_OF_1972_STCK = 0x8126D60E_46000000
TOD_EXTENSION_BITS = 40
CPU_TIMER_START = 0x7FFFFFFF_FFFFFFFF


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_host_readings_become_the_tod_clock_and_cpu_timer():
    on_the_microsecond = SystemMachineClock(
        wall_ns=lambda: START_OF_1972_UNIX_NS, cpu_ns=lambda: 1_500, sleep=time.sleep
    )
    a_nanosecond_later = SystemMachineClock(
        wall_ns=lambda: START_OF_1972_UNIX_NS + 1, cpu_ns=lambda: 0, sleep=time.sleep
    )

    assert (
        on_the_microsecond.tod_clock(),
        a_nanosecond_later.tod_clock(),
        on_the_microsecond.cpu_timer(),
        a_nanosecond_later.cpu_timer(),
    ) == (
        START_OF_1972_STCK << TOD_EXTENSION_BITS,
        0x8126D60E_46000004_189374BC_6A,
        CPU_TIMER_START - 6_144,
        CPU_TIMER_START,
    )
