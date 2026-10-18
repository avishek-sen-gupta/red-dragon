"""The run unit's RETURN-CODE holds a symbolic value, so it has no integer to read back."""

from __future__ import annotations

from interpreter.vm.vm_types import SymbolicValue


class SymbolicReturnCodeError(ValueError):
    def __init__(self, value: SymbolicValue) -> None:
        super().__init__(
            f"RETURN-CODE holds the symbolic value {value.name}, not an integer"
        )
        self.value = value
