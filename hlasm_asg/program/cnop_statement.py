# pyright: standard
"""A CNOP statement: the bytes of BCR 0,0 no-ops it pads with to reach its alignment."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.origin import Origin

NO_OP_BYTES = 2


class CnopStatement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["CNOP"]
    section: str
    offset: int
    label: str
    mnemonic: Literal["CNOP"]
    length: int
    origin: Origin

    def no_ops(self) -> range:
        return range(self.offset, self.offset + self.length, NO_OP_BYTES)
