"""Typed register references — replaces stringly-typed result_reg."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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

    def startswith(self, prefix: str) -> bool:
        """String-like startswith — delegates to the name."""
        return self.name.startswith(prefix)

    def __hash__(self) -> int:
        return hash(self.name)

    def __bool__(self) -> bool:
        return True

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Register):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return NotImplemented

    @classmethod
    def __get_pydantic_core_schema__(cls, _source: Any, _handler: Any) -> Any:
        """Allow Pydantic to coerce str | None → Register/NoRegister."""
        from pydantic_core import core_schema

        def _coerce(value: Any) -> Register:
            if isinstance(value, NoRegister):
                return value
            if isinstance(value, Register):
                return value
            if value is None or value == "":
                return NO_REGISTER
            if isinstance(value, str):
                return Register(value)
            raise TypeError(f"Cannot coerce {type(value).__name__} to Register: {value!r}")

        return core_schema.no_info_plain_validator_function(_coerce)


@dataclass(frozen=True, eq=False)
class NoRegister(Register):
    """Null object: instruction produces no result."""

    name: str = ""

    def is_present(self) -> bool:
        return False

    def __bool__(self) -> bool:
        return False


NO_REGISTER = NoRegister()
