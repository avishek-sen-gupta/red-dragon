# pyright: standard
"""One relocatable term of a complex-relocatable value: a section or external symbol and its sign."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.term_kind import TermKind
from hlasm_asg.program.term_sign import TermSign


class RelocTerm(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: TermKind
    name: str
    sign: TermSign
