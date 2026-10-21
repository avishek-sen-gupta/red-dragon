# pyright: standard
"""A symbol of the program: absolute or relocatable."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from hlasm_asg.program.abs_symbol import AbsSymbol
from hlasm_asg.program.reloc_symbol import RelocSymbol

Symbol = Annotated[AbsSymbol | RelocSymbol, Field(discriminator="kind")]
