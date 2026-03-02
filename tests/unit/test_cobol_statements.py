"""Tests for typed COBOL statement hierarchy — round-trip and dispatch."""

import pytest

from interpreter.cobol.cobol_statements import (
    AcceptStatement,
    AlterStatement,
    ArithmeticStatement,
    CallStatement,
    CancelStatement,
    CloseStatement,
    ComputeStatement,
    ContinueStatement,
    DeleteStatement,
    DisplayStatement,
    EntryStatement,
    EvaluateStatement,
    ExitStatement,
    GotoStatement,
    IfStatement,
    InitializeStatement,
    InspectStatement,
    MoveStatement,
    OpenStatement,
    PerformStatement,
    PerformTimesSpec,
    PerformUntilSpec,
    PerformVaryingSpec,
    ReadStatement,
    Replacing,
    RewriteStatement,
    SearchStatement,
    SearchWhen,
    SetStatement,
    StartStatement,
    StopRunStatement,
    StringSending,
    StringStatement,
    TallyingFor,
    UnstringStatement,
    WhenOtherStatement,
    WhenStatement,
    WriteStatement,
    parse_statement,
)


class TestParseStatementDispatch:
    def test_move(self):
        stmt = parse_statement({"type": "MOVE", "operands": ["123", "WS-A"]})
        assert isinstance(stmt, MoveStatement)
        assert stmt.source == "123"
        assert stmt.target == "WS-A"

    def test_add(self):
        stmt = parse_statement({"type": "ADD", "operands": ["5", "WS-A"]})
        assert isinstance(stmt, ArithmeticStatement)
        assert stmt.op == "ADD"
        assert stmt.source == "5"
        assert stmt.target == "WS-A"

    def test_subtract(self):
        stmt = parse_statement({"type": "SUBTRACT", "operands": ["3", "WS-A"]})
        assert isinstance(stmt, ArithmeticStatement)
        assert stmt.op == "SUBTRACT"

    def test_multiply(self):
        stmt = parse_statement({"type": "MULTIPLY", "operands": ["2", "WS-A"]})
        assert isinstance(stmt, ArithmeticStatement)
        assert stmt.op == "MULTIPLY"

    def test_divide(self):
        stmt = parse_statement({"type": "DIVIDE", "operands": ["4", "WS-A"]})
        assert isinstance(stmt, ArithmeticStatement)
        assert stmt.op == "DIVIDE"

    def test_compute(self):
        stmt = parse_statement(
            {
                "type": "COMPUTE",
                "expression": "WS-A + WS-B * 2",
                "targets": ["WS-RESULT"],
            }
        )
        assert isinstance(stmt, ComputeStatement)
        assert stmt.expression == "WS-A + WS-B * 2"
        assert stmt.targets == ["WS-RESULT"]

    def test_compute_multiple_targets(self):
        stmt = parse_statement(
            {
                "type": "COMPUTE",
                "expression": "100 - WS-A",
                "targets": ["WS-C", "WS-D"],
            }
        )
        assert isinstance(stmt, ComputeStatement)
        assert len(stmt.targets) == 2

    def test_if(self):
        stmt = parse_statement(
            {
                "type": "IF",
                "condition": "WS-A > 0",
                "children": [{"type": "DISPLAY", "operands": ["POSITIVE"]}],
            }
        )
        assert isinstance(stmt, IfStatement)
        assert stmt.condition == "WS-A > 0"
        assert len(stmt.children) == 1
        assert isinstance(stmt.children[0], DisplayStatement)

    def test_if_with_else(self):
        stmt = parse_statement(
            {
                "type": "IF",
                "condition": "WS-A > 0",
                "children": [{"type": "DISPLAY", "operands": ["YES"]}],
                "else_children": [{"type": "DISPLAY", "operands": ["NO"]}],
            }
        )
        assert isinstance(stmt, IfStatement)
        assert len(stmt.children) == 1
        assert len(stmt.else_children) == 1
        assert isinstance(stmt.else_children[0], DisplayStatement)
        assert stmt.else_children[0].operand == "NO"

    def test_if_without_else_has_empty_else_children(self):
        stmt = parse_statement(
            {
                "type": "IF",
                "condition": "WS-A > 0",
                "children": [{"type": "DISPLAY", "operands": ["YES"]}],
            }
        )
        assert isinstance(stmt, IfStatement)
        assert stmt.else_children == []

    def test_evaluate(self):
        stmt = parse_statement(
            {
                "type": "EVALUATE",
                "children": [
                    {
                        "type": "WHEN",
                        "condition": "WS-A = 1",
                        "children": [{"type": "DISPLAY", "operands": ["ONE"]}],
                    },
                    {
                        "type": "WHEN_OTHER",
                        "children": [{"type": "DISPLAY", "operands": ["OTHER"]}],
                    },
                ],
            }
        )
        assert isinstance(stmt, EvaluateStatement)
        assert len(stmt.children) == 2
        assert isinstance(stmt.children[0], WhenStatement)
        assert isinstance(stmt.children[1], WhenOtherStatement)

    def test_display(self):
        stmt = parse_statement({"type": "DISPLAY", "operands": ["HELLO"]})
        assert isinstance(stmt, DisplayStatement)
        assert stmt.operand == "HELLO"

    def test_goto(self):
        stmt = parse_statement({"type": "GOTO", "operands": ["OTHER-PARA"]})
        assert isinstance(stmt, GotoStatement)
        assert stmt.target == "OTHER-PARA"

    def test_stop_run(self):
        stmt = parse_statement({"type": "STOP_RUN"})
        assert isinstance(stmt, StopRunStatement)

    def test_perform_procedure(self):
        stmt = parse_statement({"type": "PERFORM", "operands": ["WORK-PARA"]})
        assert isinstance(stmt, PerformStatement)
        assert stmt.target == "WORK-PARA"
        assert stmt.thru == ""
        assert stmt.spec is None

    def test_perform_thru(self):
        stmt = parse_statement(
            {"type": "PERFORM", "operands": ["FIRST-PARA"], "thru": "LAST-PARA"}
        )
        assert isinstance(stmt, PerformStatement)
        assert stmt.target == "FIRST-PARA"
        assert stmt.thru == "LAST-PARA"

    def test_perform_inline(self):
        stmt = parse_statement(
            {
                "type": "PERFORM",
                "children": [{"type": "DISPLAY", "operands": ["IN-LOOP"]}],
            }
        )
        assert isinstance(stmt, PerformStatement)
        assert stmt.target == ""
        assert len(stmt.children) == 1

    def test_continue(self):
        stmt = parse_statement({"type": "CONTINUE"})
        assert isinstance(stmt, ContinueStatement)

    def test_exit(self):
        stmt = parse_statement({"type": "EXIT"})
        assert isinstance(stmt, ExitStatement)

    def test_initialize(self):
        stmt = parse_statement({"type": "INITIALIZE", "operands": ["WS-A", "WS-B"]})
        assert isinstance(stmt, InitializeStatement)
        assert stmt.operands == ["WS-A", "WS-B"]

    def test_set_to(self):
        stmt = parse_statement(
            {"type": "SET", "set_type": "TO", "targets": ["WS-IDX"], "values": ["5"]}
        )
        assert isinstance(stmt, SetStatement)
        assert stmt.set_type == "TO"
        assert stmt.targets == ["WS-IDX"]
        assert stmt.values == ["5"]

    def test_set_by_up(self):
        stmt = parse_statement(
            {
                "type": "SET",
                "set_type": "BY",
                "by_type": "UP",
                "targets": ["WS-IDX"],
                "value": "1",
            }
        )
        assert isinstance(stmt, SetStatement)
        assert stmt.set_type == "BY"
        assert stmt.by_type == "UP"
        assert stmt.values == ["1"]

    def test_string(self):
        stmt = parse_statement(
            {
                "type": "STRING",
                "sendings": [
                    {"value": "WS-FIRST", "delimited_by": "SPACES"},
                    {"value": "WS-LAST", "delimited_by": "SIZE"},
                ],
                "into": "WS-RESULT",
            }
        )
        assert isinstance(stmt, StringStatement)
        assert len(stmt.sendings) == 2
        assert stmt.sendings[0].value == "WS-FIRST"
        assert stmt.sendings[0].delimited_by == "SPACES"
        assert stmt.into == "WS-RESULT"

    def test_unstring(self):
        stmt = parse_statement(
            {
                "type": "UNSTRING",
                "source": "WS-FULL",
                "delimited_by": "SPACES",
                "into": ["WS-FIRST", "WS-LAST"],
            }
        )
        assert isinstance(stmt, UnstringStatement)
        assert stmt.source == "WS-FULL"
        assert stmt.delimited_by == "SPACES"
        assert stmt.into == ["WS-FIRST", "WS-LAST"]

    def test_inspect_tallying(self):
        stmt = parse_statement(
            {
                "type": "INSPECT",
                "inspect_type": "TALLYING",
                "source": "WS-DATA",
                "tallying_target": "WS-COUNT",
                "tallying_for": [{"mode": "ALL", "pattern": "A"}],
            }
        )
        assert isinstance(stmt, InspectStatement)
        assert stmt.inspect_type == "TALLYING"
        assert stmt.tallying_target == "WS-COUNT"
        assert len(stmt.tallying_for) == 1
        assert stmt.tallying_for[0].mode == "ALL"

    def test_inspect_replacing(self):
        stmt = parse_statement(
            {
                "type": "INSPECT",
                "inspect_type": "REPLACING",
                "source": "WS-DATA",
                "replacings": [{"mode": "ALL", "from": "A", "to": "B"}],
            }
        )
        assert isinstance(stmt, InspectStatement)
        assert stmt.inspect_type == "REPLACING"
        assert len(stmt.replacings) == 1
        assert stmt.replacings[0].from_pattern == "A"
        assert stmt.replacings[0].to_pattern == "B"

    def test_search_basic(self):
        stmt = parse_statement(
            {
                "type": "SEARCH",
                "table": "WS-TABLE",
                "varying": "WS-IDX",
                "whens": [
                    {
                        "condition": "WS-IDX = 5",
                        "children": [{"type": "DISPLAY", "operands": ["FOUND"]}],
                    }
                ],
            }
        )
        assert isinstance(stmt, SearchStatement)
        assert stmt.table == "WS-TABLE"
        assert stmt.varying == "WS-IDX"
        assert len(stmt.whens) == 1
        assert stmt.whens[0].condition == "WS-IDX = 5"
        assert len(stmt.whens[0].children) == 1

    def test_search_with_at_end(self):
        stmt = parse_statement(
            {
                "type": "SEARCH",
                "table": "WS-TABLE",
                "whens": [{"condition": "WS-A = 1"}],
                "at_end": [{"type": "DISPLAY", "operands": ["NOT FOUND"]}],
            }
        )
        assert isinstance(stmt, SearchStatement)
        assert len(stmt.at_end) == 1

    def test_call_basic(self):
        stmt = parse_statement(
            {
                "type": "CALL",
                "program": "SUBPROG",
                "using": [{"name": "WS-A", "type": "REFERENCE"}],
            }
        )
        assert isinstance(stmt, CallStatement)
        assert stmt.program == "SUBPROG"
        assert len(stmt.using) == 1
        assert stmt.using[0].name == "WS-A"
        assert stmt.using[0].param_type == "REFERENCE"

    def test_call_with_giving(self):
        stmt = parse_statement(
            {
                "type": "CALL",
                "program": "CALC",
                "using": [
                    {"name": "WS-A", "type": "CONTENT"},
                    {"name": "WS-B", "type": "VALUE"},
                ],
                "giving": "WS-RESULT",
            }
        )
        assert isinstance(stmt, CallStatement)
        assert stmt.giving == "WS-RESULT"
        assert len(stmt.using) == 2

    def test_alter(self):
        stmt = parse_statement(
            {
                "type": "ALTER",
                "proceed_tos": [{"source": "PARA-1", "target": "PARA-2"}],
            }
        )
        assert isinstance(stmt, AlterStatement)
        assert len(stmt.proceed_tos) == 1
        assert stmt.proceed_tos[0].source == "PARA-1"
        assert stmt.proceed_tos[0].target == "PARA-2"

    def test_entry(self):
        stmt = parse_statement(
            {"type": "ENTRY", "entry_name": "ALT-ENTRY", "using": ["WS-A"]}
        )
        assert isinstance(stmt, EntryStatement)
        assert stmt.entry_name == "ALT-ENTRY"
        assert stmt.using == ["WS-A"]

    def test_cancel(self):
        stmt = parse_statement({"type": "CANCEL", "programs": ["SUBPROG"]})
        assert isinstance(stmt, CancelStatement)
        assert stmt.programs == ["SUBPROG"]

    def test_accept_basic(self):
        stmt = parse_statement({"type": "ACCEPT", "target": "WS-INPUT"})
        assert isinstance(stmt, AcceptStatement)
        assert stmt.target == "WS-INPUT"
        assert stmt.from_device == "CONSOLE"

    def test_accept_with_device(self):
        stmt = parse_statement(
            {"type": "ACCEPT", "target": "WS-DATE", "from_device": "DATE"}
        )
        assert isinstance(stmt, AcceptStatement)
        assert stmt.from_device == "DATE"

    def test_open(self):
        stmt = parse_statement(
            {"type": "OPEN", "mode": "INPUT", "files": ["CUST-FILE", "ORDER-FILE"]}
        )
        assert isinstance(stmt, OpenStatement)
        assert stmt.mode == "INPUT"
        assert stmt.files == ["CUST-FILE", "ORDER-FILE"]

    def test_close(self):
        stmt = parse_statement({"type": "CLOSE", "files": ["CUST-FILE", "ORDER-FILE"]})
        assert isinstance(stmt, CloseStatement)
        assert stmt.files == ["CUST-FILE", "ORDER-FILE"]

    def test_read_basic(self):
        stmt = parse_statement({"type": "READ", "file_name": "CUST-FILE"})
        assert isinstance(stmt, ReadStatement)
        assert stmt.file_name == "CUST-FILE"
        assert stmt.into == ""

    def test_read_with_into(self):
        stmt = parse_statement(
            {"type": "READ", "file_name": "CUST-FILE", "into": "WS-RECORD"}
        )
        assert isinstance(stmt, ReadStatement)
        assert stmt.into == "WS-RECORD"

    def test_write_basic(self):
        stmt = parse_statement({"type": "WRITE", "record_name": "CUST-REC"})
        assert isinstance(stmt, WriteStatement)
        assert stmt.record_name == "CUST-REC"
        assert stmt.from_field == ""

    def test_write_with_from(self):
        stmt = parse_statement(
            {"type": "WRITE", "record_name": "CUST-REC", "from_field": "WS-OUTPUT"}
        )
        assert isinstance(stmt, WriteStatement)
        assert stmt.from_field == "WS-OUTPUT"

    def test_rewrite_basic(self):
        stmt = parse_statement({"type": "REWRITE", "record_name": "CUST-REC"})
        assert isinstance(stmt, RewriteStatement)
        assert stmt.record_name == "CUST-REC"
        assert stmt.from_field == ""

    def test_rewrite_with_from(self):
        stmt = parse_statement(
            {"type": "REWRITE", "record_name": "CUST-REC", "from_field": "WS-OUTPUT"}
        )
        assert isinstance(stmt, RewriteStatement)
        assert stmt.from_field == "WS-OUTPUT"

    def test_start_basic(self):
        stmt = parse_statement({"type": "START", "file_name": "CUST-FILE"})
        assert isinstance(stmt, StartStatement)
        assert stmt.file_name == "CUST-FILE"
        assert stmt.key == ""

    def test_start_with_key(self):
        stmt = parse_statement(
            {"type": "START", "file_name": "CUST-FILE", "key": "CUST-ID"}
        )
        assert isinstance(stmt, StartStatement)
        assert stmt.key == "CUST-ID"

    def test_delete_basic(self):
        stmt = parse_statement({"type": "DELETE", "file_name": "CUST-FILE"})
        assert isinstance(stmt, DeleteStatement)
        assert stmt.file_name == "CUST-FILE"

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown COBOL statement type"):
            parse_statement({"type": "BOGUS"})


class TestPerformSpecs:
    def test_times_spec(self):
        stmt = parse_statement(
            {
                "type": "PERFORM",
                "operands": ["WORK-PARA"],
                "perform_type": "TIMES",
                "times": "5",
            }
        )
        assert isinstance(stmt, PerformStatement)
        assert isinstance(stmt.spec, PerformTimesSpec)
        assert stmt.spec.times == "5"

    def test_until_spec_test_before(self):
        stmt = parse_statement(
            {
                "type": "PERFORM",
                "operands": ["WORK-PARA"],
                "perform_type": "UNTIL",
                "until": "WS-A > 10",
                "test_before": True,
            }
        )
        assert isinstance(stmt.spec, PerformUntilSpec)
        assert stmt.spec.condition == "WS-A > 10"
        assert stmt.spec.test_before is True

    def test_until_spec_test_after(self):
        stmt = parse_statement(
            {
                "type": "PERFORM",
                "operands": ["WORK-PARA"],
                "perform_type": "UNTIL",
                "until": "WS-A > 10",
                "test_before": False,
            }
        )
        assert isinstance(stmt.spec, PerformUntilSpec)
        assert stmt.spec.test_before is False

    def test_varying_spec(self):
        stmt = parse_statement(
            {
                "type": "PERFORM",
                "children": [{"type": "DISPLAY", "operands": ["LOOP"]}],
                "perform_type": "VARYING",
                "varying_var": "WS-IDX",
                "varying_from": "1",
                "varying_by": "1",
                "until": "WS-IDX > 10",
                "test_before": True,
            }
        )
        assert isinstance(stmt.spec, PerformVaryingSpec)
        assert stmt.spec.varying_var == "WS-IDX"
        assert stmt.spec.varying_from == "1"
        assert stmt.spec.varying_by == "1"
        assert stmt.spec.condition == "WS-IDX > 10"

    def test_no_perform_type_gives_none_spec(self):
        stmt = parse_statement({"type": "PERFORM", "operands": ["WORK-PARA"]})
        assert stmt.spec is None


class TestRoundTrip:
    """Each statement type round-trips through to_dict / parse_statement."""

    def _round_trip(self, data: dict) -> dict:
        stmt = parse_statement(data)
        return stmt.to_dict()

    def test_move_round_trip(self):
        data = {"type": "MOVE", "operands": ["123", "WS-A"]}
        assert self._round_trip(data) == data

    def test_add_round_trip(self):
        data = {"type": "ADD", "operands": ["5", "WS-A"]}
        assert self._round_trip(data) == data

    def test_display_round_trip(self):
        data = {"type": "DISPLAY", "operands": ["HELLO"]}
        assert self._round_trip(data) == data

    def test_goto_round_trip(self):
        data = {"type": "GOTO", "operands": ["PARA-X"]}
        assert self._round_trip(data) == data

    def test_stop_run_round_trip(self):
        data = {"type": "STOP_RUN"}
        assert self._round_trip(data) == data

    def test_if_round_trip(self):
        data = {
            "type": "IF",
            "condition": "WS-A > 0",
            "children": [{"type": "DISPLAY", "operands": ["YES"]}],
        }
        assert self._round_trip(data) == data

    def test_if_else_round_trip(self):
        data = {
            "type": "IF",
            "condition": "WS-A > 0",
            "children": [{"type": "DISPLAY", "operands": ["YES"]}],
            "else_children": [{"type": "DISPLAY", "operands": ["NO"]}],
        }
        assert self._round_trip(data) == data

    def test_compute_round_trip(self):
        data = {
            "type": "COMPUTE",
            "expression": "WS-A + WS-B * 2",
            "targets": ["WS-RESULT"],
        }
        assert self._round_trip(data) == data

    def test_compute_multiple_targets_round_trip(self):
        data = {
            "type": "COMPUTE",
            "expression": "(WS-A + WS-B) * 100",
            "targets": ["WS-C", "WS-D"],
        }
        assert self._round_trip(data) == data

    def test_perform_procedure_round_trip(self):
        data = {"type": "PERFORM", "operands": ["WORK-PARA"]}
        assert self._round_trip(data) == data

    def test_perform_thru_round_trip(self):
        data = {"type": "PERFORM", "operands": ["FIRST"], "thru": "LAST"}
        assert self._round_trip(data) == data

    def test_perform_times_round_trip(self):
        data = {
            "type": "PERFORM",
            "operands": ["WORK"],
            "perform_type": "TIMES",
            "times": "5",
        }
        assert self._round_trip(data) == data

    def test_perform_until_round_trip(self):
        data = {
            "type": "PERFORM",
            "operands": ["WORK"],
            "perform_type": "UNTIL",
            "until": "WS-A > 10",
            "test_before": True,
        }
        assert self._round_trip(data) == data

    def test_perform_varying_round_trip(self):
        data = {
            "type": "PERFORM",
            "operands": ["WORK"],
            "perform_type": "VARYING",
            "varying_var": "WS-IDX",
            "varying_from": "1",
            "varying_by": "1",
            "until": "WS-IDX > 10",
            "test_before": True,
        }
        assert self._round_trip(data) == data

    def test_evaluate_round_trip(self):
        data = {
            "type": "EVALUATE",
            "children": [
                {
                    "type": "WHEN",
                    "condition": "WS-A = 1",
                    "children": [{"type": "DISPLAY", "operands": ["ONE"]}],
                },
                {
                    "type": "WHEN_OTHER",
                    "children": [{"type": "DISPLAY", "operands": ["OTHER"]}],
                },
            ],
        }
        assert self._round_trip(data) == data

    def test_continue_round_trip(self):
        data = {"type": "CONTINUE"}
        assert self._round_trip(data) == data

    def test_exit_round_trip(self):
        data = {"type": "EXIT"}
        assert self._round_trip(data) == data

    def test_initialize_round_trip(self):
        data = {"type": "INITIALIZE", "operands": ["WS-A", "WS-B"]}
        assert self._round_trip(data) == data

    def test_set_to_round_trip(self):
        data = {"type": "SET", "set_type": "TO", "targets": ["WS-IDX"], "values": ["5"]}
        assert self._round_trip(data) == data

    def test_set_by_round_trip(self):
        data = {
            "type": "SET",
            "set_type": "BY",
            "targets": ["WS-IDX"],
            "by_type": "UP",
            "value": "1",
        }
        assert self._round_trip(data) == data

    def test_string_round_trip(self):
        data = {
            "type": "STRING",
            "sendings": [
                {"value": "WS-FIRST", "delimited_by": "SPACES"},
                {"value": "WS-LAST", "delimited_by": "SIZE"},
            ],
            "into": "WS-RESULT",
        }
        assert self._round_trip(data) == data

    def test_unstring_round_trip(self):
        data = {
            "type": "UNSTRING",
            "source": "WS-FULL",
            "delimited_by": " ",
            "into": ["WS-FIRST", "WS-LAST"],
        }
        assert self._round_trip(data) == data

    def test_inspect_tallying_round_trip(self):
        data = {
            "type": "INSPECT",
            "inspect_type": "TALLYING",
            "source": "WS-DATA",
            "tallying_target": "WS-COUNT",
            "tallying_for": [{"mode": "ALL", "pattern": "A"}],
        }
        assert self._round_trip(data) == data

    def test_inspect_replacing_round_trip(self):
        data = {
            "type": "INSPECT",
            "inspect_type": "REPLACING",
            "source": "WS-DATA",
            "replacings": [{"mode": "ALL", "from": "A", "to": "B"}],
        }
        assert self._round_trip(data) == data

    def test_search_round_trip(self):
        data = {
            "type": "SEARCH",
            "table": "WS-TABLE",
            "varying": "WS-IDX",
            "whens": [
                {
                    "condition": "WS-IDX = 5",
                    "children": [{"type": "DISPLAY", "operands": ["FOUND"]}],
                }
            ],
        }
        assert self._round_trip(data) == data

    def test_search_with_at_end_round_trip(self):
        data = {
            "type": "SEARCH",
            "table": "WS-TABLE",
            "whens": [{"condition": "WS-A = 1"}],
            "at_end": [{"type": "DISPLAY", "operands": ["NOT FOUND"]}],
        }
        assert self._round_trip(data) == data

    def test_call_round_trip(self):
        data = {
            "type": "CALL",
            "program": "SUBPROG",
            "using": [{"name": "WS-A", "type": "REFERENCE"}],
            "giving": "WS-RESULT",
        }
        assert self._round_trip(data) == data

    def test_alter_round_trip(self):
        data = {
            "type": "ALTER",
            "proceed_tos": [{"source": "PARA-1", "target": "PARA-2"}],
        }
        assert self._round_trip(data) == data

    def test_entry_round_trip(self):
        data = {"type": "ENTRY", "entry_name": "ALT-ENTRY", "using": ["WS-A"]}
        assert self._round_trip(data) == data

    def test_cancel_round_trip(self):
        data = {"type": "CANCEL", "programs": ["SUBPROG"]}
        assert self._round_trip(data) == data

    def test_accept_round_trip(self):
        data = {"type": "ACCEPT", "target": "WS-INPUT"}
        assert self._round_trip(data) == data

    def test_accept_with_device_round_trip(self):
        data = {"type": "ACCEPT", "target": "WS-DATE", "from_device": "DATE"}
        assert self._round_trip(data) == data

    def test_open_round_trip(self):
        data = {"type": "OPEN", "mode": "INPUT", "files": ["CUST-FILE"]}
        assert self._round_trip(data) == data

    def test_close_round_trip(self):
        data = {"type": "CLOSE", "files": ["CUST-FILE", "ORDER-FILE"]}
        assert self._round_trip(data) == data

    def test_read_round_trip(self):
        data = {"type": "READ", "file_name": "CUST-FILE"}
        assert self._round_trip(data) == data

    def test_read_with_into_round_trip(self):
        data = {"type": "READ", "file_name": "CUST-FILE", "into": "WS-RECORD"}
        assert self._round_trip(data) == data

    def test_write_round_trip(self):
        data = {"type": "WRITE", "record_name": "CUST-REC"}
        assert self._round_trip(data) == data

    def test_write_with_from_round_trip(self):
        data = {"type": "WRITE", "record_name": "CUST-REC", "from_field": "WS-OUTPUT"}
        assert self._round_trip(data) == data

    def test_rewrite_round_trip(self):
        data = {"type": "REWRITE", "record_name": "CUST-REC"}
        assert self._round_trip(data) == data

    def test_rewrite_with_from_round_trip(self):
        data = {"type": "REWRITE", "record_name": "CUST-REC", "from_field": "WS-OUTPUT"}
        assert self._round_trip(data) == data

    def test_start_round_trip(self):
        data = {"type": "START", "file_name": "CUST-FILE"}
        assert self._round_trip(data) == data

    def test_start_with_key_round_trip(self):
        data = {"type": "START", "file_name": "CUST-FILE", "key": "CUST-ID"}
        assert self._round_trip(data) == data

    def test_delete_round_trip(self):
        data = {"type": "DELETE", "file_name": "CUST-FILE"}
        assert self._round_trip(data) == data
