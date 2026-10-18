"""A NIST program's run failed in a way the harness recognises."""

from __future__ import annotations

from tests.nist.nist_outcome import NistOutcome


class NistFailure(AssertionError):
    """A NIST program's run failed in a way the harness recognises."""

    def __init__(self, outcome: NistOutcome, message: str, detail: str) -> None:
        super().__init__(message)
        self.outcome = outcome
        self.detail = detail
