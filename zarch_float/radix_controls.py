# pyright: standard
"""PFPO's target-radix-dependent controls (PoO figure 9-26): HFP overflow and underflow reporting, and the DFP preferred quantum of an exact result (DPQC)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RadixControls:
    hfp_overflow: bool
    hfp_underflow: bool
    quantum_of_one: bool
