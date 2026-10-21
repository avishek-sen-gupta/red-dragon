# pyright: standard
"""Bytes of an address constant: a section's run-time address plus an offset."""

from dataclasses import dataclass

from hlasm_asg.program.reloc_address import RelocAddress


@dataclass(frozen=True)
class AddressSlot:
    address: RelocAddress
    width: int
