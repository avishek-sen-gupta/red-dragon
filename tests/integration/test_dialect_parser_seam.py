# pyright: standard
"""Integration: a real EXEC SQL program flows through the JAR bridge into an
injected DialectParser (proves the full construction-time seam, generically —
RedDragon's own fake dialect, not Squall's real ExecSqlStatement)."""

from __future__ import annotations

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from tests.integration.cobol_helpers import bridge_jar, to_fixed
from tests.unit.cobol.dialect_parser_fixtures import FakeExtensionStatement

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


class _FakeExecSqlDialectParser:
    """Claims the bridge's real "EXEC_SQL" tag but returns RedDragon's own fake
    type — proves the generic mechanism without depending on Squall."""

    def applies(self, data: dict) -> bool:
        return data.get("type") == "EXEC_SQL"

    def parse(self, data: dict):
        return FakeExtensionStatement(text=data.get("exec_sql_text", ""))


class _SqlSpy:
    def __init__(self):
        self.lowered = []

    def handles(self, stmt):
        return isinstance(stmt, FakeExtensionStatement)

    def preprocess_program_dict(self, data):
        return data

    def on_procedure_entry(self, ctx, materialised): ...

    def lower(self, ctx, stmt, materialised):
        self.lowered.append(stmt)


def _build_real_parser(bridge_jar: str) -> ProLeapCobolParser:
    return ProLeapCobolParser(RealSubprocessRunner(), bridge_jar)


def test_real_exec_sql_reaches_fake_dialect_parser(bridge_jar):
    spy = _SqlSpy()
    parser = _build_real_parser(bridge_jar)
    frontend = CobolFrontend(
        parser,
        extension_strategies=[spy],
        dialect_parsers=[_FakeExecSqlDialectParser()],
    )
    frontend.lower(_PROGRAM)
    assert (
        len(spy.lowered) == 1
    ), f"Expected 1 FakeExtensionStatement, got {len(spy.lowered)}: {spy.lowered}"
    assert isinstance(spy.lowered[0], FakeExtensionStatement)
    assert "SELECT" in spy.lowered[0].text
    assert "SYSDUMMY1" in spy.lowered[0].text


def test_real_exec_sql_with_no_dialect_parser_raises(bridge_jar):
    import pytest

    parser = _build_real_parser(bridge_jar)
    frontend = CobolFrontend(parser, extension_strategies=[])
    with pytest.raises(ValueError, match="Unknown COBOL statement type: 'EXEC_SQL'"):
        frontend.lower(_PROGRAM)
