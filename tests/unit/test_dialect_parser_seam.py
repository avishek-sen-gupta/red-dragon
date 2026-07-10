# pyright: standard
"""RedDragon extension seam — node, protocol, dispatch, frontend wiring.

Proves the GENERIC extension_strategies + dialect_parsers machinery using
RedDragon's own fake dialect (tests/unit/cobol/dialect_parser_fixtures.py) —
never Cicada's or Squall's real types. Renamed from test_exec_sql_seam.py
(which used to import Squall's ExecSqlStatement directly; that type has
relocated to Squall and RedDragon must not depend on it)."""

from interpreter.cobol.cobol_statements import parse_statement, _dialect_parsers
from tests.unit.cobol.dialect_parser_fixtures import (
    FakeDialectParser,
    FakeExtensionStatement,
)


class TestDialectParserFallbackDispatch:
    def test_parse_statement_dispatches_to_applying_parser(self):
        token = _dialect_parsers.set([FakeDialectParser()])
        try:
            stmt = parse_statement({"type": "FAKE_EXTENSION", "fake_text": "hello"})
        finally:
            _dialect_parsers.reset(token)
        assert isinstance(stmt, FakeExtensionStatement)
        assert stmt.text == "hello"

    def test_no_dialect_parser_applies_raises_value_error(self):
        token = _dialect_parsers.set([FakeDialectParser()])
        try:
            with pytest.raises(ValueError, match="Unknown COBOL statement type"):
                parse_statement({"type": "SOMETHING_ELSE"})
        finally:
            _dialect_parsers.reset(token)

    def test_empty_dialect_parsers_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown COBOL statement type"):
            parse_statement({"type": "FAKE_EXTENSION", "fake_text": "x"})

    def test_recognized_core_type_never_offered_to_dialect_parsers(self):
        """A core type (MOVE) is dispatched by _DISPATCH_TABLE directly, never
        second-guessed against a dialect parser that would also claim it."""

        class _AlwaysApplies:
            def applies(self, data: dict) -> bool:
                return True

            def parse(self, data: dict):
                raise AssertionError(
                    "should never be called for a recognized core type"
                )

        token = _dialect_parsers.set([_AlwaysApplies()])
        try:
            stmt = parse_statement(
                {"type": "MOVE", "source": {"kind": "lit", "value": "1"}, "targets": []}
            )
        finally:
            _dialect_parsers.reset(token)
        assert stmt.__class__.__name__ == "MoveStatement"


import pytest  # noqa: E402 — see note below

# ── Extension-strategy lowering protocol tests (unchanged from the old file,
#    moved here verbatim since this file already covers "the seam" broadly) ──

from interpreter.frontend_extension_lowering import RedDragonExtensionLoweringStrategy


class _ConformingStrategy:
    def handles(self, stmt):
        return True

    def preprocess_program_dict(self, data):
        return data

    def on_procedure_entry(self, ctx, materialised): ...
    def lower(self, ctx, stmt, materialised): ...


class _MissingHandles:
    def preprocess_program_dict(self, data):
        return data

    def on_procedure_entry(self, ctx, materialised): ...
    def lower(self, ctx, stmt, materialised): ...


class TestExtensionStrategyProtocol:
    def test_conforming_class_is_instance(self):
        assert isinstance(_ConformingStrategy(), RedDragonExtensionLoweringStrategy)

    def test_missing_handles_is_not_instance(self):
        assert not isinstance(_MissingHandles(), RedDragonExtensionLoweringStrategy)


from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.statement_dispatch import dispatch_statement


class _SpyStrategy:
    def __init__(self, kind):
        self._kind = kind
        self.lowered = []
        self.entered = 0
        self.preprocessed = 0

    def handles(self, stmt):
        return isinstance(stmt, self._kind)

    def preprocess_program_dict(self, data):
        self.preprocessed += 1
        return data

    def on_procedure_entry(self, ctx, materialised):
        self.entered += 1

    def lower(self, ctx, stmt, materialised):
        self.lowered.append(stmt)


class TestEmitContextExtensionArray:
    def test_default_is_empty(self):
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        assert tuple(ctx.extension_strategies) == ()

    def test_injected_array_is_exposed(self):
        spy = _SpyStrategy(FakeExtensionStatement)
        ctx = EmitContext(dispatch_fn=dispatch_statement, extension_strategies=[spy])
        assert list(ctx.extension_strategies) == [spy]


class TestArrayDispatch:
    def test_routes_to_strategy_that_handles(self):
        spy = _SpyStrategy(FakeExtensionStatement)
        ctx = EmitContext(dispatch_fn=dispatch_statement, extension_strategies=[spy])
        stmt = FakeExtensionStatement(text="SELECT 1 INTO :X FROM T")
        dispatch_statement(ctx, stmt, materialised=None)
        assert spy.lowered == [stmt]

    def test_first_handler_wins_and_others_skipped(self):
        class _AlwaysHandles:
            def __init__(self):
                self.lowered = []

            def handles(self, stmt):
                return True

            def preprocess_program_dict(self, data):
                return data

            def on_procedure_entry(self, ctx, materialised): ...

            def lower(self, ctx, stmt, materialised):
                self.lowered.append(stmt)

        first, second = _AlwaysHandles(), _AlwaysHandles()
        ctx = EmitContext(
            dispatch_fn=dispatch_statement, extension_strategies=[first, second]
        )
        stmt = FakeExtensionStatement(text="DELETE FROM T")
        dispatch_statement(ctx, stmt, materialised=None)
        assert first.lowered == [stmt]
        assert second.lowered == []

    def test_empty_array_no_handler_warns(self, caplog):
        import logging

        ctx = EmitContext(dispatch_fn=dispatch_statement, extension_strategies=[])
        stmt = FakeExtensionStatement(text="SELECT 1")
        with caplog.at_level(logging.WARNING):
            dispatch_statement(ctx, stmt, materialised=None)
        assert "Unhandled" in caplog.text


from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.asg_types import CobolASG
from interpreter.cobol.cobol_parser import CobolParser


class _PreprocessRecordingParser(CobolParser):
    def parse(self, source: bytes, preprocessor=None) -> CobolASG:
        if preprocessor is not None:
            preprocessor({"type": "PROGRAM", "program_id": "T"})
        return CobolASG()


class TestFrontendExtensionArray:
    def test_all_strategies_preprocess_in_order(self):
        order = []

        class _OrderSpy:
            def __init__(self, tag):
                self._tag = tag

            def handles(self, stmt):
                return False

            def preprocess_program_dict(self, data):
                order.append(self._tag)
                return data

            def on_procedure_entry(self, ctx, materialised): ...
            def lower(self, ctx, stmt, materialised): ...

        a, b = _OrderSpy("a"), _OrderSpy("b")
        frontend = CobolFrontend(
            _PreprocessRecordingParser(), extension_strategies=[a, b]
        )
        frontend.lower(b"")
        assert order == ["a", "b"]

    def test_default_array_is_empty(self):
        frontend = CobolFrontend(_PreprocessRecordingParser())
        assert tuple(frontend._extension_strategies) == ()
