# pyright: standard
"""An assembly clock that always reads the same instant, so &SYSDATC and &SYSTIME are known."""

from dataclasses import dataclass
from datetime import datetime

from hlasm_asg.assembly_clock import AssemblyClock


@dataclass(frozen=True)
class FixedAssemblyClock(AssemblyClock):
    at: datetime

    def now(self) -> datetime:
        return self.at
