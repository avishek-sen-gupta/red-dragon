# pyright: standard
"""The far branch's parameters, in its argument order: the masked target, the modules with an activation below the caller, the caller's module bit (0 for a system call such as LINK) and whether the branch linked."""

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class FarBranch:
    target: Register
    below: Register
    me: Register
    linking: Register

    def arguments(self) -> tuple[Register, Register, Register, Register]:
        return (self.target, self.below, self.me, self.linking)
