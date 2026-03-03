"""Tests for COBOL ASG type round-trip serialization."""

from interpreter.cobol.asg_types import (
    CobolASG,
    CobolField,
    CobolParagraph,
    CobolSection,
)
from interpreter.cobol.cobol_statements import (
    ArithmeticStatement,
    DisplayStatement,
    IfStatement,
    MoveStatement,
    StopRunStatement,
    parse_statement,
)
from interpreter.cobol.condition_name import ConditionName, ConditionValue


class TestCobolField:
    def test_elementary_field_round_trip(self):
        data = {
            "name": "WS-AMOUNT",
            "level": 5,
            "pic": "S9(5)V99",
            "usage": "DISPLAY",
            "offset": 0,
        }
        field = CobolField.from_dict(data)
        assert field.name == "WS-AMOUNT"
        assert field.level == 5
        assert field.pic == "S9(5)V99"
        assert field.usage == "DISPLAY"
        assert field.offset == 0
        assert field.redefines == ""
        assert field.children == []
        assert CobolField.from_dict(field.to_dict()) == field

    def test_group_field_with_children(self):
        data = {
            "name": "WS-DATE",
            "level": 1,
            "pic": "",
            "usage": "DISPLAY",
            "offset": 0,
            "children": [
                {"name": "WS-YEAR", "level": 5, "pic": "9(4)", "offset": 0},
                {"name": "WS-MONTH", "level": 5, "pic": "99", "offset": 4},
                {"name": "WS-DAY", "level": 5, "pic": "99", "offset": 6},
            ],
        }
        field = CobolField.from_dict(data)
        assert len(field.children) == 3
        assert field.children[0].name == "WS-YEAR"
        assert field.children[1].offset == 4
        assert CobolField.from_dict(field.to_dict()) == field

    def test_redefines_field(self):
        data = {
            "name": "WS-DATE-NUM",
            "level": 1,
            "pic": "9(8)",
            "usage": "DISPLAY",
            "offset": 0,
            "redefines": "WS-DATE",
        }
        field = CobolField.from_dict(data)
        assert field.redefines == "WS-DATE"
        assert CobolField.from_dict(field.to_dict()) == field

    def test_field_with_value(self):
        data = {
            "name": "WS-COUNTER",
            "level": 77,
            "pic": "9(3)",
            "usage": "DISPLAY",
            "offset": 0,
            "value": "0",
        }
        field = CobolField.from_dict(data)
        assert field.value == "0"
        assert CobolField.from_dict(field.to_dict()) == field

    def test_field_with_conditions(self):
        data = {
            "name": "WS-STATUS",
            "level": 5,
            "pic": "X(1)",
            "usage": "DISPLAY",
            "offset": 0,
            "conditions": [
                {
                    "name": "STATUS-ACTIVE",
                    "values": [{"from": "A", "to": ""}],
                },
                {
                    "name": "STATUS-VALID",
                    "values": [
                        {"from": "A", "to": ""},
                        {"from": "B", "to": ""},
                        {"from": "C", "to": ""},
                    ],
                },
            ],
        }
        field = CobolField.from_dict(data)
        assert len(field.conditions) == 2
        assert field.conditions[0].name == "STATUS-ACTIVE"
        assert len(field.conditions[0].values) == 1
        assert field.conditions[1].name == "STATUS-VALID"
        assert len(field.conditions[1].values) == 3
        assert CobolField.from_dict(field.to_dict()) == field

    def test_field_with_multi_values(self):
        data = {
            "name": "WS-CODE",
            "level": 5,
            "pic": "X(1)",
            "usage": "DISPLAY",
            "offset": 0,
            "value": "A",
            "values": [
                {"from": "A", "to": ""},
                {"from": "X", "to": "Z"},
            ],
        }
        field = CobolField.from_dict(data)
        assert field.value == "A"
        assert len(field.values) == 2
        assert field.values[0].from_val == "A"
        assert not field.values[0].is_range
        assert field.values[1].from_val == "X"
        assert field.values[1].to_val == "Z"
        assert field.values[1].is_range
        assert CobolField.from_dict(field.to_dict()) == field

    def test_field_defaults_empty_conditions_and_values(self):
        data = {
            "name": "WS-SIMPLE",
            "level": 77,
            "pic": "9(5)",
            "offset": 0,
        }
        field = CobolField.from_dict(data)
        assert field.conditions == []
        assert field.values == []

    def test_field_with_sign_leading_separate(self):
        data = {
            "name": "WS-SIGNED",
            "level": 5,
            "pic": "S9(5)V99",
            "usage": "DISPLAY",
            "offset": 0,
            "sign": {"position": "LEADING", "separate": True},
        }
        field = CobolField.from_dict(data)
        assert field.sign_leading is True
        assert field.sign_separate is True
        assert CobolField.from_dict(field.to_dict()) == field

    def test_field_with_sign_trailing_embedded(self):
        data = {
            "name": "WS-SIGNED2",
            "level": 5,
            "pic": "S9(5)",
            "usage": "DISPLAY",
            "offset": 0,
            "sign": {"position": "TRAILING", "separate": False},
        }
        field = CobolField.from_dict(data)
        assert field.sign_leading is False
        assert field.sign_separate is False
        # Trailing embedded is the default, so to_dict should not emit sign
        # since both are False
        assert "sign" not in field.to_dict()

    def test_field_with_justified_right(self):
        data = {
            "name": "WS-JUST",
            "level": 5,
            "pic": "X(10)",
            "usage": "DISPLAY",
            "offset": 0,
            "justified_right": True,
        }
        field = CobolField.from_dict(data)
        assert field.justified_right is True
        assert CobolField.from_dict(field.to_dict()) == field

    def test_field_without_justified_defaults(self):
        data = {
            "name": "WS-NOJUST",
            "level": 5,
            "pic": "X(10)",
            "offset": 0,
        }
        field = CobolField.from_dict(data)
        assert field.justified_right is False
        assert "justified_right" not in field.to_dict()

    def test_field_with_synchronized(self):
        data = {
            "name": "WS-SYNC",
            "level": 5,
            "pic": "9(5)",
            "usage": "COMP",
            "offset": 0,
            "synchronized": True,
        }
        field = CobolField.from_dict(data)
        assert field.synchronized is True
        assert CobolField.from_dict(field.to_dict()) == field

    def test_field_without_synchronized_defaults(self):
        data = {
            "name": "WS-NOSYNC",
            "level": 5,
            "pic": "9(5)",
            "offset": 0,
        }
        field = CobolField.from_dict(data)
        assert field.synchronized is False
        assert "synchronized" not in field.to_dict()

    def test_field_with_occurs_depending_on(self):
        data = {
            "name": "WS-TABLE",
            "level": 5,
            "pic": "X(10)",
            "usage": "DISPLAY",
            "offset": 0,
            "occurs": 100,
            "element_size": 10,
            "occurs_depending_on": "WS-COUNT",
            "occurs_min": 1,
        }
        field = CobolField.from_dict(data)
        assert field.occurs == 100
        assert field.occurs_depending_on == "WS-COUNT"
        assert field.occurs_min == 1
        assert CobolField.from_dict(field.to_dict()) == field

    def test_field_without_occurs_depending_on_defaults(self):
        data = {
            "name": "WS-FIXED",
            "level": 5,
            "pic": "X(10)",
            "offset": 0,
            "occurs": 5,
            "element_size": 10,
        }
        field = CobolField.from_dict(data)
        assert field.occurs_depending_on == ""
        assert field.occurs_min == 0
        assert "occurs_depending_on" not in field.to_dict()
        assert "occurs_min" not in field.to_dict()

    def test_field_without_sign_defaults(self):
        data = {
            "name": "WS-NOSIGN",
            "level": 77,
            "pic": "9(5)",
            "offset": 0,
        }
        field = CobolField.from_dict(data)
        assert field.sign_leading is False
        assert field.sign_separate is False

    def test_field_with_renames_from(self):
        data = {
            "name": "WS-ALIAS",
            "level": 66,
            "pic": "",
            "usage": "DISPLAY",
            "offset": 0,
            "renames_from": "WS-FIRST",
        }
        field = CobolField.from_dict(data)
        assert field.renames_from == "WS-FIRST"
        assert field.renames_thru == ""
        assert CobolField.from_dict(field.to_dict()) == field

    def test_field_with_renames_thru(self):
        data = {
            "name": "WS-FULL-NAME",
            "level": 66,
            "pic": "",
            "usage": "DISPLAY",
            "offset": 0,
            "renames_from": "WS-FIRST",
            "renames_thru": "WS-LAST",
        }
        field = CobolField.from_dict(data)
        assert field.renames_from == "WS-FIRST"
        assert field.renames_thru == "WS-LAST"
        assert CobolField.from_dict(field.to_dict()) == field

    def test_field_without_renames_defaults(self):
        data = {
            "name": "WS-NORMAL",
            "level": 5,
            "pic": "X(10)",
            "offset": 0,
        }
        field = CobolField.from_dict(data)
        assert field.renames_from == ""
        assert field.renames_thru == ""
        assert "renames_from" not in field.to_dict()
        assert "renames_thru" not in field.to_dict()


class TestCobolStatement:
    def test_move_statement(self):
        data = {"type": "MOVE", "operands": ["WS-A", "WS-B"]}
        stmt = parse_statement(data)
        assert isinstance(stmt, MoveStatement)
        assert stmt.source == "WS-A"
        assert stmt.target == "WS-B"
        assert parse_statement(stmt.to_dict()) == stmt

    def test_if_statement_with_children(self):
        data = {
            "type": "IF",
            "condition": "WS-A > 0",
            "children": [
                {"type": "DISPLAY", "operands": ["POSITIVE"]},
            ],
        }
        stmt = parse_statement(data)
        assert isinstance(stmt, IfStatement)
        assert stmt.condition == "WS-A > 0"
        assert len(stmt.children) == 1
        assert isinstance(stmt.children[0], DisplayStatement)
        assert parse_statement(stmt.to_dict()) == stmt

    def test_add_statement(self):
        data = {"type": "ADD", "operands": ["WS-X", "WS-Y"]}
        stmt = parse_statement(data)
        assert isinstance(stmt, ArithmeticStatement)
        assert stmt.op == "ADD"
        assert parse_statement(stmt.to_dict()) == stmt


class TestCobolParagraph:
    def test_paragraph_round_trip(self):
        data = {
            "name": "MAIN-LOGIC",
            "statements": [
                {"type": "DISPLAY", "operands": ["HELLO"]},
                {"type": "STOP_RUN"},
            ],
        }
        para = CobolParagraph.from_dict(data)
        assert para.name == "MAIN-LOGIC"
        assert len(para.statements) == 2
        assert CobolParagraph.from_dict(para.to_dict()) == para


class TestCobolSection:
    def test_section_round_trip(self):
        data = {
            "name": "MAIN-SECTION",
            "paragraphs": [
                {
                    "name": "INIT-PARA",
                    "statements": [{"type": "MOVE", "operands": ["0", "WS-X"]}],
                },
            ],
        }
        section = CobolSection.from_dict(data)
        assert section.name == "MAIN-SECTION"
        assert len(section.paragraphs) == 1
        assert CobolSection.from_dict(section.to_dict()) == section


class TestCobolASG:
    def test_full_asg_round_trip(self):
        data = {
            "data_fields": [
                {"name": "WS-A", "level": 77, "pic": "9(5)", "offset": 0},
                {"name": "WS-B", "level": 77, "pic": "X(10)", "offset": 5},
            ],
            "sections": [
                {
                    "name": "MAIN-SECTION",
                    "paragraphs": [
                        {
                            "name": "MAIN-PARA",
                            "statements": [
                                {
                                    "type": "MOVE",
                                    "operands": ["12345", "WS-A"],
                                },
                                {
                                    "type": "DISPLAY",
                                    "operands": ["WS-A"],
                                },
                            ],
                        },
                    ],
                },
            ],
            "paragraphs": [
                {
                    "name": "CLEANUP",
                    "statements": [{"type": "STOP_RUN"}],
                },
            ],
        }
        asg = CobolASG.from_dict(data)
        assert len(asg.data_fields) == 2
        assert len(asg.sections) == 1
        assert len(asg.paragraphs) == 1
        assert CobolASG.from_dict(asg.to_dict()) == asg

    def test_empty_asg(self):
        asg = CobolASG.from_dict({})
        assert asg.data_fields == []
        assert asg.sections == []
        assert asg.paragraphs == []
        assert asg.to_dict() == {}
