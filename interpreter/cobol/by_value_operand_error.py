"""A CALL or PROCEDURE DIVISION USING BY VALUE operand IBM Enterprise COBOL refuses at compile time."""

from __future__ import annotations

from interpreter.cobol.by_value_phrase import ByValuePhrase


class ByValueOperandError(ValueError):
    def __init__(self, name: str, line: int, phrase: ByValuePhrase) -> None:
        self.name = name
        self.line = line
        super().__init__(
            f"line {line}: {phrase.value} {name}: IBM Enterprise COBOL passes"
            " BY VALUE only an elementary binary, COMP-1, COMP-2 or pointer item,"
            " a single alphanumeric character, or a DISPLAY item reference-modified"
            " to length 1"
        )
