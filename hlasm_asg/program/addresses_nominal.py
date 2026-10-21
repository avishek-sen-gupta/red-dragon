# pyright: standard
"""A nominal value made of address values."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from hlasm_asg.program.address import Address


class AddressesNominal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["ADDRESSES"]
    values: tuple[Address, ...]
