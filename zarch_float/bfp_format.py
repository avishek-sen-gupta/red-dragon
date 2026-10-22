# pyright: standard
"""A BFP format: precision, exponent range, and the trap scale of results in it."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BfpFormat:
    precision: int
    emax: int
    trap_scale: int

    @property
    def emin(self) -> int:
        return 1 - self.emax

    @property
    def quantum_min(self) -> int:
        return self.emin - self.precision + 1

    @property
    def quantum_max(self) -> int:
        return self.emax - self.precision + 1


SHORT = BfpFormat(24, 127, 192)
LONG = BfpFormat(53, 1023, 1536)
EXTENDED = BfpFormat(113, 16383, 24576)
