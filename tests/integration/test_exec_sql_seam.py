"""Integration: a real EXEC SQL program flows through the JAR bridge into the
injected SQL strategy (proves serializeExecSql + the full array seam)."""

from __future__ import annotations

import os
import pytest

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.cobol_statements import ExecSqlStatement
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from tests.integration.cobol_helpers import JAR_AVAILABLE, JAR_PATH, to_fixed

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)

_PROGRAM = to_fixed(
    [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. SQLT.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "77 WS-ID PIC 9(4) VALUE 0.",
        "PROCEDURE DIVISION.",
        "    EXEC SQL",
        "        SELECT 1 INTO :WS-ID FROM SYSIBM.SYSDUMMY1",
        "    END-EXEC.",
        "    STOP RUN.",
    ]
).encode("utf-8")


class _SqlSpy:
    def __init__(self):
        self.lowered = []

    def handles(self, stmt):
        return isinstance(stmt, ExecSqlStatement)

    def preprocess_program_dict(self, data):
        return data

    def on_procedure_entry(self, ctx, materialised): ...

    def lower(self, ctx, stmt, materialised):
        self.lowered.append(stmt)


def _build_real_parser() -> ProLeapCobolParser:
    """Build a JAR-backed ProLeapCobolParser the same way production code does."""
    os.environ["PROLEAP_BRIDGE_JAR"] = JAR_PATH
    return ProLeapCobolParser(RealSubprocessRunner(), JAR_PATH)


def test_real_exec_sql_reaches_strategy():
    spy = _SqlSpy()
    parser = _build_real_parser()
    frontend = CobolFrontend(parser, extension_strategies=[spy])
    frontend.lower(_PROGRAM)
    assert (
        len(spy.lowered) == 1
    ), f"Expected 1 ExecSqlStatement, got {len(spy.lowered)}: {spy.lowered}"
    assert isinstance(spy.lowered[0], ExecSqlStatement)
    assert spy.lowered[0].verb == "SELECT"
    assert "SYSDUMMY1" in spy.lowered[0].text
