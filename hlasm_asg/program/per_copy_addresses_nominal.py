# pyright: standard
"""Address values that reference the location counter, evaluated for each duplication copy at its own address."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.address import Address


class PerCopyAddressesNominal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["ADDRESSES_PER_COPY"]
    copies: tuple[tuple[Address, ...], ...]
