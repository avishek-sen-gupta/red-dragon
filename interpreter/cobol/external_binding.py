"""Where one EXTERNAL area lives at run time: the run unit's region for it."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.external_area import ExternalArea
from interpreter.register import Register


@dataclass(frozen=True)
class ExternalBinding:
    area: ExternalArea
    region_reg: Register
