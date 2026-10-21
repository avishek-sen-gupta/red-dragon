# pyright: standard
"""A section the program defines and its length in bytes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.section_kind import SectionKind


class Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    kind: SectionKind
    length: int
