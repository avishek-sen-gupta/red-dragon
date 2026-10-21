# pyright: standard
"""Where a statement came from."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from hlasm_asg.program.macro_origin import MacroOrigin
from hlasm_asg.program.open_code_origin import OpenCodeOrigin

Origin = Annotated[OpenCodeOrigin | MacroOrigin, Field(discriminator="kind")]
