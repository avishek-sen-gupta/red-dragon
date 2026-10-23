# pyright: standard
"""A VRV storage operand D2(V2,B2): its index is a vector register whose element is added to the address, never a general register."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VectorIndexedOperand:
    displacement: int
    vector_index: int
    base: int
