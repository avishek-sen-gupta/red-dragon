# pyright: standard
"""A D(X,B) storage operand, with the address as written."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.written_address import WrittenAddress


class StorageOperand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["STORAGE"]
    displacement: int
    index: int
    base: int
    written: WrittenAddress
