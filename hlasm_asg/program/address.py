# pyright: standard
"""One value of an address-constant nominal."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.external_address import ExternalAddress
from hlasm_asg.program.reloc_address import RelocAddress

Address = Annotated[
    AbsAddress | RelocAddress | ExternalAddress, Field(discriminator="kind")
]
