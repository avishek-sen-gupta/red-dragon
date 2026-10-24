# pyright: standard
"""A CXD statement: the fullword the binder fills with the total length of the external dummy sections."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.origin import Origin


class CxdStatement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["CXD"]
    section: str
    offset: int
    label: str
    mnemonic: Literal["CXD"]
    origin: Origin
