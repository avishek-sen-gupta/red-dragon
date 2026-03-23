"""Typed register references — replaces stringly-typed result_reg."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Register:
    """A named register in the IR. Always starts with %."""

    name: str

    def __post_init__(self):
        if not isinstance(self.name, str):
            raise TypeError(f"Register.name must be str, got {type(self.name).__name__}: {self.name!r}")

    def is_present(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Register):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return NotImplemented


@dataclass(frozen=True, eq=False)
class NoRegister(Register):
    """Null object: instruction produces no result."""

    name: str = ""

    def is_present(self) -> bool:
        return False


NO_REGISTER = NoRegister()
