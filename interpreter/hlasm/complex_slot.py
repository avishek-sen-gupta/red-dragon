# pyright: standard
"""Bytes of a complex-relocatable address constant, filled by the binder from its signed terms and absolute part."""

from dataclasses import dataclass

from hlasm_asg.program.complex_address import ComplexAddress


@dataclass(frozen=True)
class ComplexSlot:
    address: ComplexAddress
    width: int
