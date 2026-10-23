# pyright: standard
"""What one assembly is given: the system-variable values supplied to it and the instant it reads its time from."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from hlasm_asg.assembly_input import AssemblyInput
from hlasm_asg.unusable_assembly_input import UnusableAssemblyInput

SYSPARM_LIMIT = 255


@dataclass(frozen=True)
class AssemblyInputs:
    names: Mapping[AssemblyInput, str]
    clock: datetime

    def __post_init__(self) -> None:
        if not self.clock.tzinfo:
            raise UnusableAssemblyInput(
                f"the assembly clock gave {self.clock.isoformat()}, which has no UTC offset"
            )
        sysparm = len(self.names.get(AssemblyInput.SYSPARM, ""))
        if sysparm > SYSPARM_LIMIT:
            raise UnusableAssemblyInput(
                f"SYSPARM is {sysparm} characters; HLASM allows at most {SYSPARM_LIMIT}"
            )
