"""Tests for COBOL ASG type round-trip serialization."""

from interpreter.cobol.asg_types import (
    CobolASG,
    CobolField,
    CobolParagraph,
    CobolSection,
    CobolStatement,
)


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


class TestCobolStatement:
    def test_move_statement(self):
        data = {"type": "MOVE", "operands": ["WS-A", "WS-B"]}
        stmt = CobolStatement.from_dict(data)
        assert stmt.type == "MOVE"
        assert stmt.operands == ["WS-A", "WS-B"]
        assert CobolStatement.from_dict(stmt.to_dict()) == stmt

    def test_if_statement_with_children(self):
        data = {
            "type": "IF",
            "condition": "WS-A > 0",
            "children": [
                {"type": "DISPLAY", "operands": ["POSITIVE"]},
            ],
        }
        stmt = CobolStatement.from_dict(data)
        assert stmt.condition == "WS-A > 0"
        assert len(stmt.children) == 1
        assert stmt.children[0].type == "DISPLAY"
        assert CobolStatement.from_dict(stmt.to_dict()) == stmt

    def test_add_statement(self):
        data = {"type": "ADD", "operands": ["WS-X", "WS-Y"]}
        stmt = CobolStatement.from_dict(data)
        assert stmt.type == "ADD"
        assert CobolStatement.from_dict(stmt.to_dict()) == stmt


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
