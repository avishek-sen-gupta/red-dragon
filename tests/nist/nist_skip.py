"""A NIST program the harness does not run, and why."""

from __future__ import annotations

import pytest

from tests.nist.nist_outcome import NistOutcome


class NistSkip(pytest.skip.Exception):
    """A NIST program the harness does not run, and why."""

    def __init__(self, outcome: NistOutcome, reason: str) -> None:
        super().__init__(reason)
        self.outcome = outcome
        self.detail = reason.splitlines()[0]
