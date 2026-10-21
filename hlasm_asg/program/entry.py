# pyright: standard
"""How the program says where it starts."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from hlasm_asg.program.default_entry import DefaultEntry
from hlasm_asg.program.named_entry import NamedEntry

Entry = Annotated[NamedEntry | DefaultEntry, Field(discriminator="kind")]
