"""Each callee LINKAGE 01 bound to the address its caller passed for it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class LinkageBinding:
    """Where a LINKAGE 01 lives at run time: a region, and the shift from its
    static start to the argument's offset in that region."""

    start: int
    length: int
    region_reg: Register
    delta_reg: Register

    def holds(self, offset: int) -> bool:
        return self.start <= offset < self.start + max(self.length, 1)


def binding_at(bindings: Sequence[LinkageBinding], offset: int) -> LinkageBinding:
    return next(binding for binding in bindings if binding.holds(offset))
