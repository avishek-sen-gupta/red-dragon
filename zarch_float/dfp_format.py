# pyright: standard
"""A DFP format: precision in digits and the left-units-view exponent range."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DfpFormat:
    precision: int
    emax: int

    @property
    def emin(self) -> int:
        return 1 - self.emax

    @property
    def quantum_min(self) -> int:
        return self.emin - self.precision + 1

    @property
    def bias(self) -> int:
        return -self.quantum_min

    @property
    def quantum_max(self) -> int:
        return self.emax - self.precision + 1


SHORT = DfpFormat(7, 96)
LONG = DfpFormat(16, 384)
EXTENDED = DfpFormat(34, 6144)
