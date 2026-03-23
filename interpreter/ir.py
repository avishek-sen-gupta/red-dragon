"""IR Design — Flattened High-Level Three-Address Code."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel

from interpreter.register import Register, NoRegister, NO_REGISTER


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


# Opcodes that define a named variable (declaration or assignment).
# Used by dataflow analysis and interprocedural summary extraction.
VAR_DEFINITION_OPCODES: frozenset[Opcode] = frozenset(
    {Opcode.DECL_VAR, Opcode.STORE_VAR}
)


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


# ── Label types ──────────────────────────────────────────────────


@dataclass(frozen=True)
class CodeLabel:
    """A label on an IR instruction (branch target or block entry)."""

    _FUNC_PREFIX = "func_"
    _CLASS_PREFIX = "class_"
    _END_CLASS_PREFIX = "end_class_"
    _PRELUDE_CLASS_PREFIX = "prelude_class_"
    _PRELUDE_END_CLASS_PREFIX = "prelude_end_class_"
    _ENTRY = "entry"

    value: str

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(f"CodeLabel.value must be str, got {type(self.value).__name__}: {self.value!r}")

    def is_present(self) -> bool:
        return True

    def is_function(self) -> bool:
        """Is this a function entry label (possibly namespaced)?"""
        return (
            self.value.startswith(self._FUNC_PREFIX)
            or f".{self._FUNC_PREFIX}" in self.value
        )

    def is_class(self) -> bool:
        """Is this a class entry label (possibly namespaced)?"""
        return (
            self.value.startswith(self._CLASS_PREFIX)
            or f".{self._CLASS_PREFIX}" in self.value
            or self.value.startswith(self._PRELUDE_CLASS_PREFIX)
            or f".{self._PRELUDE_CLASS_PREFIX}" in self.value
        ) and not self.is_end_class()

    def is_end_class(self) -> bool:
        """Is this an end-class label (possibly namespaced)?"""
        return (
            self.value.startswith(self._END_CLASS_PREFIX)
            or f".{self._END_CLASS_PREFIX}" in self.value
            or self.value.startswith(self._PRELUDE_END_CLASS_PREFIX)
            or f".{self._PRELUDE_END_CLASS_PREFIX}" in self.value
        )

    def is_entry(self) -> bool:
        """Is this the program entry label?"""
        return self.value == self._ENTRY

    def is_end_label(self) -> bool:
        """Is this an end_ label (function or class)?"""
        return self.value.startswith("end_") or self.is_end_class()

    def extract_name(self, prefix: str) -> str:
        """Extract the base name from a label like func_foo_3 → foo."""
        import re

        suffix = self.value[len(prefix) :]
        match = re.match(r"^(.+)_(\d+)$", suffix)
        return match.group(1) if match else suffix

    def starts_with(self, prefix: str) -> bool:
        """Check if the label value starts with the given prefix."""
        return self.value.startswith(prefix)

    def contains(self, substring: str) -> bool:
        """Check if the label value contains the given substring."""
        return substring in self.value

    def __contains__(self, item: str) -> bool:
        """Support ``'x' in label`` syntax."""
        return item in self.value

    def namespace(self, prefix: str) -> CodeLabel:
        """Return a new CodeLabel with a module namespace prefix."""
        return CodeLabel(f"{prefix}.{self.value}")

    def with_suffix(self, suffix: str) -> CodeLabel:
        """Return a new CodeLabel with a suffix appended."""
        return CodeLabel(self.value + suffix)

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, CodeLabel):
            return self.value == other.value
        if isinstance(other, str):
            return self.value == other
        return NotImplemented


@dataclass(frozen=True, eq=False)
class NoCodeLabel(CodeLabel):
    """Null object: instruction has no label."""

    value: str = ""

    def is_present(self) -> bool:
        return False

    def is_function(self) -> bool:
        return False

    def is_class(self) -> bool:
        return False

    def is_end_class(self) -> bool:
        return False

    def is_entry(self) -> bool:
        return False

    def is_end_label(self) -> bool:
        return False

    def starts_with(self, prefix: str) -> bool:
        return False

    def contains(self, substring: str) -> bool:
        return False

    def __contains__(self, item: str) -> bool:
        return False

    def namespace(self, prefix: str) -> CodeLabel:
        return self

    def with_suffix(self, suffix: str) -> CodeLabel:
        return self


NO_LABEL = NoCodeLabel()


class IRInstruction(BaseModel):
    opcode: Opcode
    result_reg: Register = NO_REGISTER
    operands: list[Any] = []
    label: CodeLabel = NO_LABEL
    branch_targets: list[CodeLabel] = []
    source_location: SourceLocation = NO_SOURCE_LOCATION

    def __str__(self) -> str:
        parts: list[str] = []
        if self.label.is_present() and self.opcode == Opcode.LABEL:
            base = f"{self.label}:"
        else:
            if self.result_reg.is_present():
                parts.append(f"{self.result_reg} =")
            parts.append(self.opcode.value.lower())
            for op in self.operands:
                parts.append(str(op))
            if self.branch_targets:
                parts.append(",".join(str(t) for t in self.branch_targets))
            elif self.label.is_present() and self.opcode != Opcode.LABEL:
                parts.append(str(self.label))
            base = " ".join(parts)
        if not self.source_location.is_unknown():
            return f"{base}  # {self.source_location}"
        return base
