# pyright: standard
"""A base, index or length sub-field of an instruction operand."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.instruction_table.parameter_kind import ParameterKind


class Parameter(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ParameterKind
    bits: int
    signed: bool
