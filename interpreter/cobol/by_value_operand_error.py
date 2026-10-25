"""A CALL BY VALUE operand IBM Enterprise COBOL refuses at compile time."""

from __future__ import annotations


class ByValueOperandError(ValueError):
    def __init__(self, name: str, line: int) -> None:
        self.name = name
        self.line = line
        super().__init__(
            f"line {line}: CALL BY VALUE {name}: IBM Enterprise COBOL passes"
            " BY VALUE only an elementary binary, COMP-1, COMP-2 or pointer item,"
            " or a single alphanumeric character"
        )
