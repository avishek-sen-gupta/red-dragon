"""Unit tests for run_cics() and the CICS dispatcher loop."""

import inspect
from tests.covers import covers, NotLanguageFeature
from interpreter.run import run_linked


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_run_linked_accepts_initial_vm():
    sig = inspect.signature(run_linked)
    assert "initial_vm" in sig.parameters
