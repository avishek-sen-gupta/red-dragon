"""Integration: a real EXEC SQL program flows through the JAR bridge into the
injected SQL strategy (proves serializeExecSql + the full array seam)."""

from __future__ import annotations

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.cobol_statements import ExecSqlStatement
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from tests.integration.cobol_helpers import bridge_jar, to_fixed

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


def _build_real_parser(bridge_jar: str) -> ProLeapCobolParser:
    """Build a JAR-backed ProLeapCobolParser the same way production code does."""
    return ProLeapCobolParser(RealSubprocessRunner(), bridge_jar)


def test_real_exec_sql_reaches_strategy(bridge_jar):
    spy = _SqlSpy()
    parser = _build_real_parser(bridge_jar)
    frontend = CobolFrontend(parser, extension_strategies=[spy])
    frontend.lower(_PROGRAM)
    assert (
        len(spy.lowered) == 1
    ), f"Expected 1 ExecSqlStatement, got {len(spy.lowered)}: {spy.lowered}"
    assert isinstance(spy.lowered[0], ExecSqlStatement)
    # Opaque node: text is the raw EXEC SQL verbatim (envelope included).
    assert "SELECT" in spy.lowered[0].text
    assert "SYSDUMMY1" in spy.lowered[0].text
