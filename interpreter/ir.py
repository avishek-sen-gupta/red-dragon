"""IR Design — Flattened High-Level Three-Address Code."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class SpreadArguments:
    """Marks a call operand as spread — the VM unpacks the heap array into individual args."""

    register: str

    def __str__(self) -> str:
        return f"*{self.register}"


class Opcode(str, Enum):
    # Value producers
    CONST = "CONST"
    LOAD_VAR = "LOAD_VAR"
    LOAD_FIELD = "LOAD_FIELD"
    LOAD_INDEX = "LOAD_INDEX"
    NEW_OBJECT = "NEW_OBJECT"
    NEW_ARRAY = "NEW_ARRAY"
    BINOP = "BINOP"
    UNOP = "UNOP"
    CALL_FUNCTION = "CALL_FUNCTION"
    CALL_METHOD = "CALL_METHOD"
    CALL_UNKNOWN = "CALL_UNKNOWN"
    # Value consumers / control flow
    DECL_VAR = "DECL_VAR"
    STORE_VAR = "STORE_VAR"
    STORE_FIELD = "STORE_FIELD"
    STORE_INDEX = "STORE_INDEX"
    BRANCH_IF = "BRANCH_IF"
    BRANCH = "BRANCH"
    RETURN = "RETURN"
    THROW = "THROW"
    TRY_PUSH = "TRY_PUSH"
    TRY_POP = "TRY_POP"
    # Special
    SYMBOLIC = "SYMBOLIC"
    # Region operations (byte-addressed memory)
    ALLOC_REGION = "ALLOC_REGION"
    WRITE_REGION = "WRITE_REGION"
    LOAD_REGION = "LOAD_REGION"
    # Continuation operations (named return points)
    SET_CONTINUATION = "SET_CONTINUATION"
    RESUME_CONTINUATION = "RESUME_CONTINUATION"
    # Pointer operations
    ADDRESS_OF = "ADDRESS_OF"
    LOAD_INDIRECT = "LOAD_INDIRECT"
    LOAD_FIELD_INDIRECT = "LOAD_FIELD_INDIRECT"
    STORE_INDIRECT = "STORE_INDIRECT"
    # Labels (pseudo-instruction)
    LABEL = "LABEL"


class SourceLocation(BaseModel):
    """Structured source span from tree-sitter AST nodes."""

    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def is_unknown(self) -> bool:
        return (
            self.start_line == 0
            and self.start_col == 0
            and self.end_line == 0
            and self.end_col == 0
        )

    def __str__(self) -> str:
        if self.is_unknown():
            return "<unknown>"
        return f"{self.start_line}:{self.start_col}-{self.end_line}:{self.end_col}"


NO_SOURCE_LOCATION = SourceLocation(start_line=0, start_col=0, end_line=0, end_col=0)


class IRInstruction(BaseModel):
    opcode: Opcode
    result_reg: str | None = None
    operands: list[Any] = []
    label: str | None = None  # for LABEL / branch targets
    source_location: SourceLocation = NO_SOURCE_LOCATION

    def __str__(self) -> str:
        parts: list[str] = []
        if self.label and self.opcode == Opcode.LABEL:
            base = f"{self.label}:"
        else:
            if self.result_reg:
                parts.append(f"{self.result_reg} =")
            parts.append(self.opcode.value.lower())
            for op in self.operands:
                parts.append(str(op))
            if self.label and self.opcode != Opcode.LABEL:
                parts.append(self.label)
            base = " ".join(parts)
        if not self.source_location.is_unknown():
            return f"{base}  # {self.source_location}"
        return base
