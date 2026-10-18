"""One NIST program's outcome, as a test report carries it to the report."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from tests.nist.nist_module import NistModule
from tests.nist.nist_outcome import NistOutcome


class NistResult(BaseModel):
    """One NIST program's outcome, as a test report carries it to the report."""

    model_config = ConfigDict(frozen=True)

    program: str
    outcome: NistOutcome
    detail: str

    @property
    def module(self) -> NistModule:
        return NistModule(self.program[:2])
