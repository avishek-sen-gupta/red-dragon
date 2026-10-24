# pyright: standard
"""Whether a diagnostic came from an MNOTE, and with which severity or as a comment."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from hlasm_asg.program.mnote_comment import MnoteComment
from hlasm_asg.program.mnote_level import MnoteLevel
from hlasm_asg.program.no_mnote import NoMnote

Mnote = Annotated[MnoteLevel | MnoteComment | NoMnote, Field(discriminator="kind")]
