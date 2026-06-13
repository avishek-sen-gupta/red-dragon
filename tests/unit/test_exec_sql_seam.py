"""RedDragon EXEC SQL extension seam — node, protocol, dispatch, frontend wiring."""

from interpreter.cobol.cobol_statements import ExecSqlStatement, parse_statement


class TestExecSqlStatementNode:
    def test_from_dict_extracts_text_and_verb(self):
        data = {
            "type": "EXEC_SQL",
            "exec_sql_text": "SELECT ACCT_BAL INTO :WS-BAL FROM ACCOUNT WHERE ACCT_ID = :WS-ID",
        }
        stmt = ExecSqlStatement.from_dict(data)
        assert stmt.verb == "SELECT"
        assert stmt.text == data["exec_sql_text"]

    def test_from_dict_empty_text_yields_empty_verb(self):
        stmt = ExecSqlStatement.from_dict({"type": "EXEC_SQL"})
        assert stmt.verb == ""
        assert stmt.text == ""

    def test_verb_is_uppercased_first_token(self):
        stmt = ExecSqlStatement.from_dict(
            {"type": "EXEC_SQL", "exec_sql_text": "  insert into T values (1)"}
        )
        assert stmt.verb == "INSERT"

    def test_parse_statement_dispatches_exec_sql(self):
        stmt = parse_statement({"type": "EXEC_SQL", "exec_sql_text": "DELETE FROM T"})
        assert isinstance(stmt, ExecSqlStatement)
        assert stmt.verb == "DELETE"


from interpreter.cobol.red_dragon_extension_strategy import (
    RedDragonExtensionLoweringStrategy,
)


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


# ── Task 3-5 tests ────────────────────────────────────────────────────────────

from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.statement_dispatch import dispatch_statement


class _SpyStrategy:
    def __init__(self, kind):
        self._kind = kind  # the statement class this spy claims
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
        spy = _SpyStrategy(ExecSqlStatement)
        ctx = EmitContext(dispatch_fn=dispatch_statement, extension_strategies=[spy])
        assert list(ctx.extension_strategies) == [spy]


class TestArrayDispatch:
    def test_routes_to_strategy_that_handles(self):
        sql_spy = _SpyStrategy(ExecSqlStatement)
        ctx = EmitContext(
            dispatch_fn=dispatch_statement, extension_strategies=[sql_spy]
        )
        stmt = ExecSqlStatement(verb="SELECT", text="SELECT 1 INTO :X FROM T")
        dispatch_statement(ctx, stmt, materialised=None)
        assert sql_spy.lowered == [stmt]

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
        stmt = ExecSqlStatement(verb="DELETE", text="DELETE FROM T")
        dispatch_statement(ctx, stmt, materialised=None)
        assert first.lowered == [stmt]
        assert second.lowered == []

    def test_empty_array_no_handler_warns(self, caplog):
        import logging

        ctx = EmitContext(dispatch_fn=dispatch_statement, extension_strategies=[])
        stmt = ExecSqlStatement(verb="SELECT", text="SELECT 1")
        with caplog.at_level(logging.WARNING):
            dispatch_statement(ctx, stmt, materialised=None)
        assert "Unhandled" in caplog.text


from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.asg_types import CobolASG
from interpreter.cobol.cobol_parser import CobolParser


class _PreprocessRecordingParser(CobolParser):
    """Fake parser: calls the injected preprocessor on a minimal program dict,
    then returns an empty ASG so frontend.lower() completes."""

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
