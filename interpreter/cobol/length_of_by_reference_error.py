"""A CALL BY REFERENCE LENGTH OF operand, which IBM Enterprise COBOL refuses at compile time."""

from __future__ import annotations


class LengthOfByReferenceError(ValueError):
    def __init__(self, name: str, line: int) -> None:
        self.name = name
        self.line = line
        super().__init__(
            f"line {line}: CALL BY REFERENCE LENGTH OF {name}: IBM Enterprise COBOL"
            " passes the LENGTH OF special register only BY CONTENT or BY VALUE"
        )
