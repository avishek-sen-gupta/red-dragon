"""IR Design — Flattened High-Level Three-Address Code."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


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
    STORE_VAR = "STORE_VAR"
    STORE_FIELD = "STORE_FIELD"
    STORE_INDEX = "STORE_INDEX"
    BRANCH_IF = "BRANCH_IF"
    BRANCH = "BRANCH"
    RETURN = "RETURN"
    THROW = "THROW"
    # Special
    SYMBOLIC = "SYMBOLIC"
    # Labels (pseudo-instruction)
    LABEL = "LABEL"


class IRInstruction(BaseModel):
    opcode: Opcode
    result_reg: str | None = None
    operands: list[Any] = []
    label: str | None = None  # for LABEL / branch targets
    source_location: str | None = None

    def __str__(self) -> str:
        parts: list[str] = []
        if self.label and self.opcode == Opcode.LABEL:
            return f"{self.label}:"
        if self.result_reg:
            parts.append(f"{self.result_reg} =")
        parts.append(self.opcode.value.lower())
        for op in self.operands:
            parts.append(str(op))
        if self.label and self.opcode != Opcode.LABEL:
            parts.append(self.label)
        return " ".join(parts)
