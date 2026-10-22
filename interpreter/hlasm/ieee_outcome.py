# pyright: standard
"""The registers an IEEE trap decision reads: trap conditions, nontrap flags, and the DXC of each trap kind."""

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class IeeeOutcome:
    trap: Register
    flags: Register
    scaled_dxc: Register
    inexact_dxc: Register
