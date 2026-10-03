"""Each callee LINKAGE 01 bound to the address its caller passed for it."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class LinkageBinding:
    """Where a LINKAGE 01 lives at run time: a region, and the shift from its
    static start to the argument's offset in that region."""

    name: str
    start: int
    length: int
    region_reg: Register
    delta_reg: Register
