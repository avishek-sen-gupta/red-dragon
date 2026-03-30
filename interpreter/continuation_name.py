"""ContinuationName — typed COBOL continuation point name."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ContinuationName:
    """A COBOL continuation point name (e.g., 'para_WORK_end', 'section_MAIN_end')."""

    value: str

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(
                f"ContinuationName.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ContinuationName):
            return self.value == other.value
        return NotImplemented

    def __bool__(self) -> bool:
        return bool(self.value)


@dataclass(frozen=True, eq=False)
class NoContinuationName(ContinuationName):
    """Null object: no continuation name."""

    value: str = ""

    def is_present(self) -> bool:
        return False


NO_CONTINUATION_NAME = NoContinuationName()
