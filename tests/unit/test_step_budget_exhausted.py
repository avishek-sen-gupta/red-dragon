"""The VM warns when it stops because the step budget ran out, not because the program ended."""

from __future__ import annotations

import logging

from interpreter.api import execute_traced
from interpreter.run import run
from tests.covers import NotLanguageFeature, covers

BUDGET_MESSAGE = "VM ran out of step budget"

INFINITE_LOOP = """\
x = 0
while True:
    x = x + 1
"""

TERMINATING = """\
x = 1
"""


def _budget_warned(caplog) -> bool:
    return any(BUDGET_MESSAGE in r.getMessage() for r in caplog.records)


class TestStepBudgetExhausted:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_warns_when_budget_exhausted_before_program_ends(self, caplog):
        with caplog.at_level(logging.WARNING, logger="interpreter.run"):
            run(INFINITE_LOOP, language="python", max_steps=50)
        assert _budget_warned(caplog)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_no_warning_when_program_ends_within_budget(self, caplog):
        with caplog.at_level(logging.WARNING, logger="interpreter.run"):
            run(TERMINATING, language="python", max_steps=500)
        assert not _budget_warned(caplog)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_traced_execution_warns_when_budget_exhausted(self, caplog):
        with caplog.at_level(logging.WARNING, logger="interpreter.run"):
            execute_traced(INFINITE_LOOP, language="python", max_steps=50)
        assert _budget_warned(caplog)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_traced_execution_no_warning_when_program_ends(self, caplog):
        with caplog.at_level(logging.WARNING, logger="interpreter.run"):
            execute_traced(TERMINATING, language="python", max_steps=500)
        assert not _budget_warned(caplog)
