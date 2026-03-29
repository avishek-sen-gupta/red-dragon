"""Address — typed heap/region address."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Address:
    """A heap object or region address (e.g., 'obj_0', 'arr_3', 'mem_0')."""

    value: str

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(
                f"Address.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Address):
            return self.value == other.value
        return NotImplemented

    def __bool__(self) -> bool:
        return bool(self.value)

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Address):
            return self.value < other.value
        return NotImplemented

    def startswith(self, prefix: str) -> bool:
        return self.value.startswith(prefix)


@dataclass(frozen=True, eq=False)
class NoAddress(Address):
    """Null object: no address."""

    value: str = ""

    def is_present(self) -> bool:
        return False


NO_ADDRESS = NoAddress()
