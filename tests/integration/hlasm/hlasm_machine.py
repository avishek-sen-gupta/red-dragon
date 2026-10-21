# pyright: standard
"""What a run left in the machine: the run, the condition code and the 64-bit general registers."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from tests.integration.hlasm.hlasm_run import HlasmRun


@dataclass(frozen=True)
class HlasmMachine:
    run: HlasmRun
    cc: int
    gprs: Mapping[int, int]

    def restricted_to(self, registers: Iterable[int]) -> "HlasmMachine":
        return HlasmMachine(self.run, self.cc, {r: self.gprs[r] for r in registers})
