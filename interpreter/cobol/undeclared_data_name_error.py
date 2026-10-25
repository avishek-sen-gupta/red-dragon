"""A statement names a data item the program does not declare: a compile-time error."""

from __future__ import annotations

from cobol_asg.source_span import SourceSpan


def line_of(span: SourceSpan | None) -> int:
    match span:
        case SourceSpan(line_start=line):
            return line
        case None:
            return 0


class UndeclaredDataNameError(LookupError):
    def __init__(self, name: str, span: SourceSpan | None) -> None:
        self.name = name
        self.line = line_of(span)
        super().__init__(
            f"line {self.line}: data name {name!r} is not declared in the DATA DIVISION"
        )
