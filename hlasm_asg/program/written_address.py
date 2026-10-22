# pyright: standard
"""A storage operand's address as the source wrote it, before USING resolution."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.reloc_address import RelocAddress

WrittenAddress = Annotated[AbsAddress | RelocAddress, Field(discriminator="kind")]
