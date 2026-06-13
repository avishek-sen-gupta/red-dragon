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
