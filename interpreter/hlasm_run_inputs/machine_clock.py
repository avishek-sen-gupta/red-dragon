# pyright: standard
"""The clocks a run reads from outside the program, the TOD clock and the CPU timer, and the interval wait that lets real time pass."""

from typing import Protocol


class MachineClock(Protocol):
    def tod_clock(self) -> int: ...

    def cpu_timer(self) -> int: ...

    def wait(self, hundredths: int) -> None: ...
