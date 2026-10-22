# pyright: standard
"""The clocks a run reads from outside the program: the TOD clock and the CPU timer."""

from typing import Protocol


class MachineClock(Protocol):
    def tod_clock(self) -> int: ...

    def cpu_timer(self) -> int: ...
