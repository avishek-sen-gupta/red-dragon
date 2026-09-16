"""Shared fixtures for tests/unit/cobol/."""

import pytest

from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.statement_dispatch import dispatch_statement


@pytest.fixture
def cobol_emit_context() -> EmitContext:
    return EmitContext(dispatch_fn=dispatch_statement)
