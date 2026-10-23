# pyright: standard
"""What one assembly is given: the system-variable values supplied to it and the instant it reads its time from."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from hlasm_asg.assembly_input import AssemblyInput


@dataclass(frozen=True)
class AssemblyInputs:
    names: Mapping[AssemblyInput, str]
    clock: datetime
