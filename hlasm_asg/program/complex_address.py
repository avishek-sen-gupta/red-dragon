# pyright: standard
"""A complex-relocatable address constant: its relocatable terms, each signed and repeated by its count, plus its absolute part."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.reloc_term import RelocTerm


class ComplexAddress(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["COMPLEX"]
    terms: tuple[RelocTerm, ...]
    offset: int
