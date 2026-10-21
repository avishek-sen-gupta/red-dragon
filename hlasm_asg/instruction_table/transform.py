# pyright: standard
"""One step deriving a base-instruction operand from an extended mnemonic's operands."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.instruction_table.transform_kind import TransformKind


class Transform(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: TransformKind
    skip: int
    value: int
    source: int
    insert: bool
